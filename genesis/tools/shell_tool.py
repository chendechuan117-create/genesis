"""
Shell 执行工具
"""

import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from genesis.core.base import Tool
from genesis.core.sandbox import SandboxManager
from genesis.core.artifacts import is_project_debris


logger = logging.getLogger(__name__)


class ShellTool(Tool):
    """Shell 命令执行工具 (支持沙箱)"""
    
    def __init__(
        self, 
        timeout: int = 600, 
        use_sandbox: bool = False,
        workspace_path: str = None,
        job_manager = None
    ):
        """
        初始化
        
        Args:
            timeout: 命令超时时间（秒），默认 600s
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
        
        - execute(cmd): Run and wait for result (up to 600s). Use for most commands.
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
        if not self.job_manager:
            return "No JobManager"

        import json

        def _format_health_check_item(value):
            if value is None:
                return None
            if isinstance(value, bytearray):
                value = bytes(value)
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            if isinstance(value, tuple):
                value = list(value)
            if isinstance(value, list):
                formatted_items = []
                for item in value:
                    if isinstance(item, tuple):
                        item = list(item)
                    if isinstance(item, list):
                        normalized = []
                        for nested in item:
                            if isinstance(nested, tuple):
                                nested = list(nested)
                            normalized.append(nested)
                        formatted_items.append(json.dumps(normalized, ensure_ascii=False, sort_keys=True))
                    elif isinstance(item, dict):
                        formatted_items.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
                    else:
                        formatted = _format_health_check_item(item)
                        if formatted is not None:
                            formatted_items.append(formatted)
                return "; ".join(formatted_items)
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False, sort_keys=True)
            return str(value)

        report = self.job_manager.health_check()
        self.job_manager.cleanup_stale()

        lines = ["=== Genesis Health Check ==="]
        if not isinstance(report, dict):
            lines.append("Report: invalid health report")
            return "\n".join(lines)

        lines.append(f"Jobs: {report.get('jobs_running', 0)} running / {report.get('jobs_total', 0)} total")

        for key, label in (("status", "Status"), ("overall", "Overall"), ("summary", "Summary")):
            value = _format_health_check_item(report.get(key))
            if value:
                lines.append(f"{label}: {value}")

        for key, label in (("warnings", "Warnings"), ("issues", "Issues")):
            value = _format_health_check_item(report.get(key))
            if value:
                lines.append(f"{label}: {value}")

        sys_info = report.get("system", {})
        if isinstance(sys_info, dict):
            if sys_info.get("mem_usage_pct") is not None:
                lines.append(
                    f"Memory: {sys_info['mem_usage_pct']}% used ({sys_info.get('mem_available_mb', '?')} MB free)"
                )
            if sys_info.get("disk_usage_pct") is not None:
                lines.append(
                    f"Disk: {sys_info['disk_usage_pct']}% used ({sys_info.get('disk_free_gb', '?')} GB free)"
                )
            load_values = [sys_info.get("load_1m"), sys_info.get("load_5m"), sys_info.get("load_15m")]
            load_values = [str(v) for v in load_values if v is not None]
            if load_values:
                lines.append(f"Load: {' / '.join(load_values)}")
        else:
            rendered = _format_health_check_item(sys_info)
            if rendered:
                lines.append(f"System: {rendered}")

        network_probe = report.get("network_probe")
        if isinstance(network_probe, dict):
            probe_status = network_probe.get("status")
            if not probe_status and network_probe.get("ok") is True:
                probe_status = "ok"
            elif not probe_status:
                probe_status = "unknown"
            lines.append(f"Network probe: {probe_status}")
            for key, label in (("summary", "Summary"), ("error", "Error"), ("http_status", "HTTP status"), ("url", "URL")):
                value = _format_health_check_item(network_probe.get(key))
                if value:
                    lines.append(f"{label}: {value}")
        elif network_probe is not None:
            rendered = _format_health_check_item(network_probe)
            lines.append(f"Network probe: {rendered or 'unknown'}")

        zombie = report.get("zombie_check", {})
        if isinstance(zombie, dict):
            genesis_procs = zombie.get("genesis_processes")
            if not isinstance(genesis_procs, list):
                genesis_procs = []
            lines.append(f"Genesis instances: {len(genesis_procs)}")
            for p in genesis_procs:
                if isinstance(p, dict):
                    lines.append(f"  PID {p.get('pid', '?')} | CPU {p.get('cpu', '?')}% | MEM {p.get('mem', '?')}%")
                else:
                    rendered = _format_health_check_item(p)
                    if rendered:
                        lines.append(f"  {rendered}")
            zombie_count = zombie.get("zombie_count", 0)
            if isinstance(zombie_count, int) and zombie_count > 0:
                lines.append(f"⚠️ Zombie processes: {zombie_count}")
        else:
            rendered = _format_health_check_item(zombie)
            lines.append("Genesis instances: 0")
            if rendered:
                lines.append(f"Zombie check: {rendered}")

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
                        process.communicate(), timeout=1800  # 长命令最多 30 分钟
                    )
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    return f"[TIMEOUT] 命令执行超过 30 分钟，已终止。"

            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')
            return self._format_result(command, cwd, process.returncode, stdout_text, stderr_text)

        except Exception as e:
            logger.error(f"执行命令失败: {command}, error: {e}")
            return f"Error: 执行命令失败 - {str(e)}"

    @staticmethod
    def _format_result(command: str, cwd, code: int, stdout: str, stderr: str) -> str:
        """统一格式化命令执行结果"""
        
        # 安全网：限制输出总长度，防止单次工具输出撑爆上下文
        MAX_OUTPUT_CHARS = 30000  # ~7500 tokens，足以容纳绝大多数有意义输出
        
        result = []
        if cwd and is_project_debris(Path(str(cwd))):
            result.append("⚠️ [debris] 工作目录位于 Genesis 自生成碎片区，输出可能包含非正式源码")
        result.append(f"命令: {command}")
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
        
        output = "\n".join(result)
        
        # 截断处理：保留首尾，中间用省略标记
        if len(output) > MAX_OUTPUT_CHARS:
            half = MAX_OUTPUT_CHARS // 2
            output = output[:half] + f"\n\n... [输出过长，已截断 {len(output) - MAX_OUTPUT_CHARS} 字符] ...\n\n" + output[-half:]
        
        return output
