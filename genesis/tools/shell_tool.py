"""
Shell 执行工具
"""

import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from genesis.core.base import Tool
from genesis.core.sandbox import SandboxManager


logger = logging.getLogger(__name__)


class ShellTool(Tool):
    """Shell 命令执行工具 (支持沙箱)"""
    
    def __init__(
        self, 
        timeout: int = 120, 
        use_sandbox: bool = False,
        workspace_path: str = None,
        job_manager = None
    ):
        """
        初始化
        
        Args:
            timeout: 命令超时时间（秒）
            use_sandbox: 是否使用 Docker 沙箱
            workspace_path: 沙箱工作目录（宿主机路径）
            job_manager: JobManager 实例 (用于异步任务)
        """
        self.timeout = timeout
        self.use_sandbox = use_sandbox
        self.sandbox = None
        
        if use_sandbox:
            if not workspace_path:
                workspace_path = str(Path.cwd())
            self.sandbox = SandboxManager(workspace_path)
            self.sandbox.ensure_image()
            
        # Async Job Manager
        if job_manager:
            self.job_manager = job_manager
        else:
            # Lazy load or create new
            try:
                from genesis.core.jobs import JobManager
                self.job_manager = JobManager()
            except ImportError:
                self.job_manager = None

    @property
    def name(self) -> str:
        return "shell"
    
    @property
    def description(self) -> str:
        base_desc = """Execute shell commands. Supports sync (execute) and async (spawn/poll).
        
        - execute(cmd): Run and wait for result (up to 120s). Use for most commands.
        - spawn(cmd): Start background job, returns Job ID immediately. Use for long tasks (builds, large downloads, servers).
        - poll(job_id): Check background job status and output.
        """
        if self.use_sandbox:
            base_desc += "\n- 🛡️ 运行在 Docker 沙箱隔离环境中"
        else:
            base_desc += "\n- ⚠️ 运行在宿主机环境 (仅限受信任操作)"
        return base_desc
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["execute", "spawn", "poll", "list_jobs", "kill_job", "health_check"],
                    "description": "操作类型：execute(默认同步), spawn(异步启动), poll(检查状态), list_jobs(列出所有), kill_job(终止任务), health_check(系统诊断)",
                    "default": "execute"
                },
                "command": {
                    "type": "string",
                    "description": "Shell命令 (execute/spawn 必填)"
                },
                "job_id": {
                    "type": "string",
                    "description": "Job ID (poll 必填)"
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录",
                    "default": None
                },
                "is_daemon": {
                    "type": "boolean",
                    "description": "execute模式专用：标记为常驻服务",
                    "default": False
                }
            }
        }
    
    
    def spawn_job(self, command: str, cwd: str) -> str:
        if not self.job_manager:
            return "Error: JobManager not initialized."
        try:
            jid = self.job_manager.spawn(command, cwd)
            return f"✅ Job Started. ID: {jid}\nUse action='poll', job_id='{jid}' to monitor."
        except Exception as e:
            return f"Error spawning job: {e}"

    def poll_job(self, job_id: str) -> str:
        if not self.job_manager:
            return "Error: JobManager not initialized."
        status = self.job_manager.poll(job_id)
        if "error" in status:
            return f"Error: {status['error']}"
            
        out = f"Job ID: {status['id']}\nStatus: {status['status']}"
        if status.get("exit_code") is not None:
             out += f" (Exit: {status['exit_code']})"
             
        if status.get("new_stdout"):
            out += f"\n[STDOUT]:\n{status['new_stdout']}"
        if status.get("new_stderr"):
            out += f"\n[STDERR]:\n{status['new_stderr']}"
            
        return out

    def list_jobs(self) -> str:
        if not self.job_manager: return "No JobManager"
        jobs = self.job_manager.list_jobs()
        if not jobs: return "No active jobs."
        
        lines = ["Active Jobs:"]
        for j in jobs:
            dur = j.get("duration_human", "")
            lines.append(f"- {j['id']}: {j['command']} [{j['status']}] {dur}")
        return "\n".join(lines)

    def kill_job(self, job_id: str) -> str:
        if not self.job_manager: return "No JobManager"
        return self.job_manager.kill_job(job_id)

    def health_check(self) -> str:
        """System health diagnostics"""
        if not self.job_manager: return "No JobManager"
        import json
        report = self.job_manager.health_check()
        self.job_manager.cleanup_stale()
        
        lines = ["=== Genesis Health Check ==="]
        lines.append(f"Jobs: {report['jobs_running']} running / {report['jobs_total']} total")
        
        sys_info = report.get("system", {})
        if sys_info.get("mem_usage_pct") is not None:
            lines.append(f"Memory: {sys_info['mem_usage_pct']}% used ({sys_info.get('mem_available_mb', '?')} MB free)")
        if sys_info.get("disk_usage_pct") is not None:
            lines.append(f"Disk: {sys_info['disk_usage_pct']}% used ({sys_info.get('disk_free_gb', '?')} GB free)")
        if sys_info.get("load_1m") is not None:
            lines.append(f"Load: {sys_info['load_1m']} / {sys_info['load_5m']} / {sys_info['load_15m']}")
        
        zombie = report.get("zombie_check", {})
        genesis_procs = zombie.get("genesis_processes", [])
        lines.append(f"Genesis instances: {len(genesis_procs)}")
        for p in genesis_procs:
            lines.append(f"  PID {p['pid']} | CPU {p['cpu']}% | MEM {p['mem']}%")
        if zombie.get("zombie_count", 0) > 0:
            lines.append(f"⚠️ Zombie processes: {zombie['zombie_count']}")
        
        return "\n".join(lines)
    
    async def execute(self, command: str = None, action: str = "execute", job_id: str = None, cwd: str = None, is_daemon: bool = False) -> str:
        """统一执行入口"""
        
        # Dispatch based on action
        if action == "spawn":
            if not command: return "Error: spawn action requires 'command'"
            return self.spawn_job(command, cwd)
            
        elif action == "poll":
            if not job_id: return "Error: poll action requires 'job_id'"
            return self.poll_job(job_id)
            
        elif action == "list_jobs":
            return self.list_jobs()

        elif action == "kill_job":
            if not job_id: return "Error: kill_job action requires 'job_id'"
            return self.kill_job(job_id)

        elif action == "health_check":
            return self.health_check()
            
        else: # Default: execute (Synchronous)
            if not command: return "Error: execute action requires 'command'"
            return await self._execute_sync(command, cwd, is_daemon)

    # 自动识别可能耗时较长的命令模式
    _LONG_RUNNING_PATTERNS = (
        'install', 'update', 'upgrade', 'build', 'compile', 'make',
        'download', 'clone', 'pull', 'push', 'deploy', 'pip ', 'npm ',
        'cargo ', 'yarn ', 'pacman -S', 'apt ', 'yay ', 'paru ',
        'docker ', 'wget ', 'curl -o', 'curl -O',
    )

    async def _execute_sync(self, command: str, cwd: str = None, is_daemon: bool = False) -> str:
        """执行命令。长命令自动 spawn+poll，短命令同步等待。"""
        try:
            # 安全检查
            dangerous_patterns = ['rm -rf /', 'dd if=', 'mkfs', ':(){:|:&};:']
            if any(pattern in command for pattern in dangerous_patterns):
                return f"Error: 拒绝执行危险命令: {command}"

            # 沙箱执行
            if self.use_sandbox and self.sandbox:
                cmd_to_run = f"cd {cwd} && {command}" if cwd else command
                code, stdout, stderr = self.sandbox.exec_command(cmd_to_run, timeout=self.timeout)
                return self._format_result(command, cwd, code, stdout, stderr)

            # 设置工作目录
            work_dir = None
            if cwd:
                work_dir = Path(cwd).expanduser().resolve()
                if not work_dir.exists():
                    return f"Error: 工作目录不存在: {cwd}"

            # 常驻服务检测
            known_daemons = ('scrcpy', 'server', 'daemon', 'npm start', 'python -m http.server')
            if is_daemon or any(d in command for d in known_daemons):
                return self.spawn_job(command, str(work_dir or '.'))

            # 长命令自动检测：先快速等待，超时后自动转 spawn+poll
            is_long = any(p in command.lower() for p in self._LONG_RUNNING_PATTERNS)
            quick_timeout = 10 if is_long else self.timeout

            # 正确的开启子进程
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=quick_timeout
                )
            except asyncio.TimeoutError:
                if not is_long:
                    # 普通命令超时 → 终止
                    try:
                        process.kill()
                    except Exception:
                        pass
                    return f"[TIMEOUT] 命令超时（{quick_timeout}秒），已终止。"

                # 长命令超时 → 继续等待（最多 5 分钟）
                logger.info(f"⏳ 长命令检测：{command[:60]}... 延长等待")
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=290  # 剩余 ~290s（总共 ~300s）
                    )
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    return f"[TIMEOUT] 命令执行超过 5 分钟，已终止。"

            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')
            return self._format_result(command, cwd, process.returncode, stdout_text, stderr_text)

        except Exception as e:
            logger.error(f"执行命令失败: {command}, error: {e}")
            return f"Error: 执行命令失败 - {str(e)}"

    @staticmethod
    def _format_result(command: str, cwd, code: int, stdout: str, stderr: str) -> str:
        """统一格式化命令执行结果（带截断）"""
        
        def truncate(text: str, limit: int = 4000) -> str:
            if not text or len(text) <= limit:
                return text
            half = limit // 2
            return text[:half] + f"\n...[Output Truncated ({len(text) - limit} chars hidden)]...\n" + text[-half:]

        result = [f"命令: {command}"]
        if cwd:
            result.append(f"目录: {cwd}")
        result.append(f"退出码: {code}")
        
        if stdout:
            result.append(f"\n标准输出:\n{truncate(stdout)}")
        if stderr:
            result.append(f"\n标准错误:\n{truncate(stderr)}")
            
        if code != 0:
            result.append(f"\n⚠️  命令执行失败（退出码 {code}）")
        else:
            result.append("\n✓ 命令执行成功")
        return "\n".join(result)
