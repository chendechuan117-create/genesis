"""
Shell 执行工具
"""

import sys
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.core.base import Tool
from genesis.core.sandbox import SandboxManager


logger = logging.getLogger(__name__)


class ShellTool(Tool):
    """Shell 命令执行工具 (支持沙箱)"""
    
    def __init__(
        self, 
        timeout: int = 30, 
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
        base_desc = """执行 Shell 命令。支持同步执行 (execute) 和异步任务 (spawn/poll)。
        
        Capabilities:
        1. execute(cmd): 同步阻塞执行，等待结果。
        2. spawn(cmd): 异步启动后台任务，立即返回 Job ID。
        3. poll(job_id): 检查异步任务状态和输出。
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
                    "enum": ["execute", "spawn", "poll", "list_jobs"],
                    "description": "操作类型：execute(默认同步), spawn(异步启动), poll(检查状态), list_jobs(列出所有)",
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
            lines.append(f"- {j['id']}: {j['command']} [{j['status']}]")
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
            
        else: # Default: execute (Synchronous)
            if not command: return "Error: execute action requires 'command'"
            return await self._execute_sync(command, cwd, is_daemon)

    async def _execute_sync(self, command: str, cwd: str = None, is_daemon: bool = False) -> str:
        """原有同步执行逻辑 (Internal)"""
        try:
            # 沙箱执行
            if self.use_sandbox and self.sandbox:
                cmd_to_run = command
                if cwd:
                    # 在沙箱中切换目录
                    cmd_to_run = f"cd {cwd} && {command}"
                
                code, stdout, stderr = self.sandbox.exec_command(cmd_to_run, timeout=self.timeout)
                
                # 格式化结果
                result = [f"命令(Sandbox): {command}"]
                if cwd:
                    result.append(f"目录: {cwd}")
                result.append(f"退出码: {code}")
                
                if stdout:
                    result.append(f"\n标准输出:\n{stdout}")
                if stderr:
                    result.append(f"\n标准错误:\n{stderr}")
                
                if code != 0:
                    result.append(f"\n⚠️  命令执行失败（退出码 {code}）")
                else:
                    result.append("\n✓ 命令执行成功")
                
                return "\n".join(result)

            # 宿主机执行 (原有逻辑)
            # 安全检查
            dangerous_patterns = ['rm -rf /', 'dd if=', 'mkfs', ':(){:|:&};:']
            if any(pattern in command for pattern in dangerous_patterns):
                return f"Error: 拒绝执行危险命令: {command}"
            
            # 设置工作目录
            work_dir = None
            if cwd:
                work_dir = Path(cwd).expanduser().resolve()
                if not work_dir.exists():
                    return f"Error: 工作目录不存在: {cwd}"
            
            # 执行命令
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir
            )
            
            # 等待完成（带超时）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                # Daemon Mercy Logic: Don't kill if explicitly marked OR matches known pattern
                known_daemons = ['scrcpy', 'server', 'daemon', 'npm start', 'python -m http.server']
                detected_daemon = any(d in command for d in known_daemons)
                
                if not is_daemon and not detected_daemon:
                    try:
                        process.kill()
                    except:
                        pass
                    return f"[TIMEOUT_WARNING] 命令超时（{self.timeout}秒）。进程已被终止。如果这是常驻服务，请设置 is_daemon=True。"
                else:
                    # Detach and let it run
                    reason = "参数指定" if is_daemon else "自动检测"
                    return f"[TIMEOUT_GUARD] [{reason}] 检测到常驻服务 ({command})。命令超时但**未终止进程**。它应在后台继续运行。"
            
            # 解码输出
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')
            
            # 格式化结果
            result = [f"命令: {command}"]
            if work_dir:
                result.append(f"目录: {work_dir}")
            result.append(f"退出码: {process.returncode}")
            
            if stdout_text:
                result.append(f"\n标准输出:\n{stdout_text}")
            
            if stderr_text:
                result.append(f"\n标准错误:\n{stderr_text}")
            
            if process.returncode != 0:
                result.append(f"\n⚠️  命令执行失败（退出码 {process.returncode}）")
            else:
                result.append("\n✓ 命令执行成功")
            
            return "\n".join(result)
        
        except Exception as e:
            logger.error(f"执行命令失败: {command}, error: {e}")
            return f"Error: 执行命令失败 - {str(e)}"
