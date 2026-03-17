
import signal
import subprocess
import uuid
import time
import logging
import fcntl
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

# psutil is optional — graceful fallback
try:
    import psutil as _psutil
    HAS_PSUTIL = True
except ImportError:
    _psutil = None
    HAS_PSUTIL = False


@dataclass
class Job:
    id: str
    command: str
    process: subprocess.Popen
    start_time: float
    cwd: str
    status: str = "RUNNING"  # RUNNING, COMPLETED, FAILED, TERMINATED
    exit_code: Optional[int] = None
    stdout_buffer: str = ""
    stderr_buffer: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        duration = time.time() - self.start_time if self.status == "RUNNING" else None
        return {
            "id": self.id,
            "command": self.command,
            "pid": self.process.pid,
            "status": self.status,
            "start_time": self.start_time,
            "duration": duration,
            "duration_human": f"{duration:.1f}s" if duration else None,
            "exit_code": self.exit_code
        }


class JobManager:
    """
    Manages asynchronous background processes (Jobs).
    Decouples 'ordering' from 'execution'.
    """
    
    STALE_THRESHOLD = 3600  # 1 hour — auto-clean finished jobs older than this
    
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        
    def spawn(self, command: str, cwd: str = None) -> str:
        """Start a background process"""
        job_id = f"job_{str(uuid.uuid4())[:8]}"
        
        work_dir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
        if not work_dir.exists():
            raise FileNotFoundError(f"Working directory not found: {work_dir}")

        logger.info(f"🚀 Spawning Job {job_id}: {command} (in {work_dir})")
        
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid, 
            text=True,
            bufsize=1
        )
        
        self._set_nonblocking(process.stdout)
        self._set_nonblocking(process.stderr)
        
        job = Job(
            id=job_id,
            command=command,
            process=process,
            start_time=time.time(),
            cwd=str(work_dir)
        )
        self.jobs[job_id] = job
        return job_id

    def poll(self, job_id: str) -> Dict[str, Any]:
        """Check status and read latest output"""
        job = self.jobs.get(job_id)
        if not job:
            return {"error": "Job not found", "status": "UNKNOWN"}
            
        new_stdout = self._read_stream(job.process.stdout)
        new_stderr = self._read_stream(job.process.stderr)
        
        job.stdout_buffer += new_stdout
        if new_stderr:
            job.stderr_buffer += new_stderr
            
        return_code = job.process.poll()
        if return_code is not None:
            if job.status == "RUNNING":
                job.status = "COMPLETED" if return_code == 0 else "FAILED"
                job.exit_code = return_code
                logger.info(f"🏁 Job {job_id} finished with code {return_code}")
        
        return {
            "id": job.id,
            "status": job.status,
            "new_stdout": new_stdout,
            "new_stderr": new_stderr,
            "exit_code": job.exit_code
        }

    def kill_job(self, job_id: str, force: bool = False) -> str:
        """Terminate or kill a running job and its entire process group"""
        job = self.jobs.get(job_id)
        if not job:
            return f"Job {job_id} not found"
        if job.status != "RUNNING":
            return f"Job {job_id} is already {job.status}"
        
        try:
            pgid = os.getpgid(job.process.pid)
            if force:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.killpg(pgid, signal.SIGTERM)
            job.status = "TERMINATED"
            job.exit_code = -9 if force else -15
            logger.info(f"🛑 Job {job_id} (pid {job.process.pid}) {'killed' if force else 'terminated'}")
            return f"Job {job_id} {'killed (SIGKILL)' if force else 'terminated (SIGTERM)'}"
        except ProcessLookupError:
            job.status = "TERMINATED"
            return f"Job {job_id} process already gone"
        except Exception as e:
            return f"Failed to kill job {job_id}: {e}"

    def list_jobs(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List jobs summary"""
        for jid, job in list(self.jobs.items()):
            if job.status == "RUNNING":
                self.poll(jid)
                
        results = []
        for job in self.jobs.values():
            if active_only and job.status not in ["RUNNING"]:
                continue
            results.append(job.to_dict())
        return results

    def cleanup_stale(self) -> int:
        """Remove finished jobs older than STALE_THRESHOLD"""
        now = time.time()
        stale_ids = []
        for jid, job in self.jobs.items():
            if job.status in ("COMPLETED", "FAILED", "TERMINATED"):
                age = now - job.start_time
                if age > self.STALE_THRESHOLD:
                    stale_ids.append(jid)
        for jid in stale_ids:
            del self.jobs[jid]
        if stale_ids:
            logger.info(f"🧹 Cleaned {len(stale_ids)} stale jobs")
        return len(stale_ids)

    def health_check(self) -> Dict[str, Any]:
        """System-level health diagnostics"""
        report: Dict[str, Any] = {
            "jobs_running": 0,
            "jobs_total": len(self.jobs),
        }
        
        # Job stats
        for job in self.jobs.values():
            if job.status == "RUNNING":
                self.poll(job.id)
                if job.status == "RUNNING":
                    report["jobs_running"] += 1
        
        # System resources
        report["system"] = self._get_system_info()
        
        # Zombie processes check
        report["zombie_check"] = self._check_zombies()
        
        return report

    @staticmethod
    def _get_system_info() -> Dict[str, Any]:
        """Gather basic system resource info"""
        info: Dict[str, Any] = {}
        
        # Memory
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    info["mem_total_mb"] = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):
                    info["mem_available_mb"] = int(line.split()[1]) // 1024
            if "mem_total_mb" in info and "mem_available_mb" in info:
                info["mem_usage_pct"] = round(
                    (1 - info["mem_available_mb"] / info["mem_total_mb"]) * 100, 1
                )
        except Exception:
            pass
        
        # Disk
        try:
            usage = shutil.disk_usage(Path.home())
            info["disk_total_gb"] = round(usage.total / (1024**3), 1)
            info["disk_free_gb"] = round(usage.free / (1024**3), 1)
            info["disk_usage_pct"] = round((usage.used / usage.total) * 100, 1)
        except Exception:
            pass
        
        # Load average
        try:
            load1, load5, load15 = os.getloadavg()
            info["load_1m"] = round(load1, 2)
            info["load_5m"] = round(load5, 2)
            info["load_15m"] = round(load15, 2)
        except Exception:
            pass
        
        return info

    @staticmethod
    def _check_zombies() -> Dict[str, Any]:
        """Check for zombie/orphan Python processes"""
        result: Dict[str, Any] = {"genesis_processes": [], "zombie_count": 0}
        try:
            import subprocess as sp
            out = sp.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5
            )
            for line in out.stdout.splitlines():
                if "discord_bot" in line and "grep" not in line:
                    parts = line.split(None, 10)
                    result["genesis_processes"].append({
                        "pid": parts[1] if len(parts) > 1 else "?",
                        "cpu": parts[2] if len(parts) > 2 else "?",
                        "mem": parts[3] if len(parts) > 3 else "?",
                        "cmd": parts[10] if len(parts) > 10 else line
                    })
                if " Z " in line or "<defunct>" in line:
                    result["zombie_count"] += 1
        except Exception:
            pass
        return result

    def _set_nonblocking(self, f):
        """Set a file descriptor to be non-blocking"""
        if not f: return
        fd = f.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    def _read_stream(self, stream) -> str:
        """Read available data from stream without blocking"""
        if not stream: return ""
        try:
            return stream.read() or ""
        except (IOError, TypeError):
            return ""

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)
