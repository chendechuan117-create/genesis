
import subprocess
import uuid
import time
import logging
import fcntl
import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class Job:
    id: str
    command: str
    process: subprocess.Popen
    start_time: float
    cwd: str
    status: str = "RUNNING" # RUNNING, COMPLETED, FAILED, TERMINATED
    exit_code: Optional[int] = None
    stdout_buffer: str = ""
    stderr_buffer: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "pid": self.process.pid,
            "status": self.status,
            "start_time": self.start_time,
            "duration": time.time() - self.start_time if self.status == "RUNNING" else None,
            "exit_code": self.exit_code
        }

class JobManager:
    """
    Manages asynchronous background processes (Jobs).
    Decouples 'ordering' from 'execution'.
    """
    
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        # Ensure output directory for logs if needed, 
        # but for now we keep buffers in memory or simple files.
        
    def spawn(self, command: str, cwd: str = None) -> str:
        """Start a background process"""
        job_id = f"job_{str(uuid.uuid4())[:8]}"
        
        # Prepare CWD
        work_dir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
        if not work_dir.exists():
            raise FileNotFoundError(f"Working directory not found: {work_dir}")

        logger.info(f"🚀 Spawning Job {job_id}: {command} (in {work_dir})")
        
        # Start Popen independent of shell if possible, but command is string so shell=True
        # We use setsid to ensure it has its own process group (useful for killing whole tree)
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid, 
            text=True,
            bufsize=1 # Line buffered
        )
        
        # Set non-blocking I/O for stdout/stderr
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
            
        # 1. Read Output (Non-blocking)
        new_stdout = self._read_stream(job.process.stdout)
        new_stderr = self._read_stream(job.process.stderr)
        
        job.stdout_buffer += new_stdout
        if new_stderr:
            job.stderr_buffer += new_stderr
            
        # 2. Check Exit Status
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

    def list_jobs(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List jobs summary"""
        # Auto-poll all running jobs to update status
        for jid, job in self.jobs.items():
            if job.status == "RUNNING":
                self.poll(jid)
                
        results = []
        for job in self.jobs.values():
            if active_only and job.status not in ["RUNNING"]:
                continue
            results.append(job.to_dict())
        return results

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
