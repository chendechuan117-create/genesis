"""
Shell 执行工具
"""

import sys
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base import Tool
from core.sandbox import SandboxManager


logger = logging.getLogger(__name__)


class ShellTool(Tool):
    """Shell 命令执行工具 (支持沙箱)"""
    
    def __init__(
        self, 
        timeout: int = 30, 
        use_sandbox: bool = False,
        workspace_path: str = None
    ):
        """
        初始化
        
        Args:
            timeout: 命令超时时间（秒）
            use_sandbox: 是否使用 Docker 沙箱
            workspace_path: 沙箱工作目录（宿主机路径）
        """
        self.timeout = timeout
        self.use_sandbox = use_sandbox
        self.sandbox = None
        
        if use_sandbox:
            if not workspace_path:
                workspace_path = str(Path.cwd())
            self.sandbox = SandboxManager(workspace_path)
            # 预热沙箱
            self.sandbox.ensure_image()
    
    @property
    def name(self) -> str:
        return "shell"
    
    @property
    def description(self) -> str:
        desc = """执行 Shell 命令。
        
        注意：
        - 有超时限制（默认 30 秒）
        - 返回标准输出和标准错误"""
        
        if self.use_sandbox:
            desc += "\n- 🛡️ 运行在 Docker 沙箱隔离环境中"
        else:
            desc += "\n- ⚠️ 运行在宿主机环境 (仅限受信任操作)"
            
        return desc
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 Shell 命令"
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（相对路径）",
                    "default": None
                }
            },
            "required": ["command"]
        }
    
    async def execute(self, command: str, cwd: str = None) -> str:
        """执行 Shell 命令"""
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
                try:
                    process.kill()
                except:
                    pass
                return f"Error: 命令超时（{self.timeout}秒）: {command}"
            
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
