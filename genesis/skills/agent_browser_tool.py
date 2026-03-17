import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import asyncio
import tempfile
import json
from pathlib import Path
import os

class AgentBrowserTool(Tool):
    """
    agent-browser集成工具
    基于Rust编写的agent-browser CLI工具，提供浏览器自动化功能
    """
    
    @property
    def name(self) -> str:
        return "agent_browser_tool"
        
    @property
    def description(self) -> str:
        return """agent-browser浏览器自动化工具，基于Rust编写的高性能浏览器自动化CLI。
        支持：打开网页、截图、获取内容、点击元素、填写表单等操作。
        特点：daemon模式减少启动开销，支持交互式元素引用。"""
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string", 
                    "description": "要执行的命令类型",
                    "enum": [
                        "open", "screenshot", "get_title", "get_url", 
                        "get_text", "get_html", "snapshot", "click",
                        "type", "fill", "scroll", "wait", "close",
                        "eval", "check_status", "run_script"
                    ],
                    "default": "check_status"
                },
                "url": {"type": "string", "description": "要打开的URL"},
                "selector": {"type": "string", "description": "CSS选择器或元素引用（如@e1）"},
                "text": {"type": "string", "description": "要输入的文本"},
                "output_path": {"type": "string", "description": "输出文件路径"},
                "timeout": {"type": "integer", "description": "超时时间（秒）", "default": 30},
                "wait_for": {
                    "type": "string", 
                    "description": "等待条件：load, domcontentloaded, networkidle",
                    "default": "networkidle"
                },
                "full_page": {"type": "boolean", "description": "是否截取完整页面", "default": True},
                "interactive_only": {"type": "boolean", "description": "是否只获取交互元素", "default": False}
            },
            "required": ["command"]
        }
        
    async def execute(self, command: str, **kwargs) -> str:
        try:
            # 确保PATH包含cargo bin目录
            env = os.environ.copy()
            env['PATH'] = f"{os.environ.get('HOME', '')}/.cargo/bin:{env.get('PATH', '')}"
            
            if command == "check_status":
                return await self._check_status(env)
            elif command == "open":
                return await self._open_url(kwargs.get("url"), env, kwargs.get("wait_for"))
            elif command == "screenshot":
                return await self._screenshot(
                    kwargs.get("url"), 
                    kwargs.get("output_path", "/tmp/agent_browser_screenshot.png"),
                    env,
                    kwargs.get("full_page", True)
                )
            elif command == "get_title":
                return await self._get_title(kwargs.get("url"), env)
            elif command == "get_text":
                return await self._get_text(kwargs.get("url"), kwargs.get("selector"), env)
            elif command == "snapshot":
                return await self._get_snapshot(kwargs.get("url"), env, kwargs.get("interactive_only", False))
            elif command == "close":
                return await self._close_browser(env)
            elif command == "run_script":
                return await self._run_script(kwargs.get("script", ""), env)
            else:
                return f"❌ 暂不支持的命令: {command}\n支持的命令: open, screenshot, get_title, get_text, snapshot, close"
                
        except Exception as e:
            return f"❌ agent-browser执行失败: {str(e)}\n请确保已安装agent-browser: cargo install agent-browser"
    
    async def _check_status(self, env) -> str:
        """检查agent-browser状态"""
        results = []
        
        # 检查agent-browser是否安装
        check = subprocess.run(
            ["agent-browser", "--version"],
            capture_output=True,
            text=True,
            env=env
        )
        
        if check.returncode == 0:
            version = check.stdout.strip()
            results.append(f"✅ agent-browser已安装: {version}")
        else:
            results.append("❌ agent-browser未安装或不在PATH中")
            results.append("安装命令: cargo install agent-browser")
            return "\n".join(results)
        
        # 检查浏览器daemon状态
        daemon_check = subprocess.run(
            "agent-browser get url",
            shell=True,
            capture_output=True,
            text=True,
            env=env
        )
        
        if daemon_check.returncode == 0:
            results.append("✅ 浏览器daemon正在运行")
            if daemon_check.stdout.strip():
                results.append(f"当前页面: {daemon_check.stdout.strip()}")
        else:
            results.append("ℹ️ 浏览器daemon未运行（首次使用时会自动启动）")
        
        # 测试基本功能
        test_result = subprocess.run(
            'agent-browser open "https://httpbin.org/get" && agent-browser get title',
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
            env=env
        )
        
        if test_result.returncode == 0:
            results.append("✅ 基本功能测试通过")
        else:
            results.append("⚠️ 基本功能测试失败")
            if test_result.stderr:
                results.append(f"错误: {test_result.stderr[:200]}")
        
        return "📊 agent-browser状态检查:\n\n" + "\n".join(results)
    
    async def _open_url(self, url: str, env, wait_for: str = "networkidle") -> str:
        """打开URL"""
        if not url:
            return "❌ 需要提供URL参数"
        
        cmd = f'agent-browser open "{url}" && agent-browser wait --load {wait_for}'
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            if result.returncode == 0:
                # 获取实际打开的URL和标题
                url_result = subprocess.run(
                    "agent-browser get url",
                    shell=True,
                    capture_output=True,
                    text=True,
                    env=env
                )
                
                title_result = subprocess.run(
                    "agent-browser get title",
                    shell=True,
                    capture_output=True,
                    text=True,
                    env=env
                )
                
                current_url = url_result.stdout.strip() if url_result.returncode == 0 else "未知"
                title = title_result.stdout.strip() if title_result.returncode == 0 else "未知"
                
                return f"""✅ 成功打开URL
目标URL: {url}
实际URL: {current_url}
页面标题: {title}

输出: {result.stdout[:500]}{'...' if len(result.stdout) > 500 else ''}"""
            else:
                return f"❌ 打开URL失败:\n{result.stderr or result.stdout}"
                
        except subprocess.TimeoutExpired:
            return f"❌ 打开URL超时 (30秒)"
    
    async def _screenshot(self, url: str, output_path: str, env, full_page: bool = True) -> str:
        """截图页面"""
        if not url:
            return "❌ 需要提供URL参数"
        
        # 确保输出目录存在
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        full_flag = "--full" if full_page else ""
        cmd = f'agent-browser open "{url}" && agent-browser wait --load networkidle && agent-browser screenshot "{output_path}" {full_flag}'
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=45,
                env=env
            )
            
            if result.returncode == 0:
                if Path(output_path).exists():
                    size = Path(output_path).stat().st_size
                    return f"✅ 截图成功保存到: {output_path}\n文件大小: {size} bytes\n{result.stdout}"
                else:
                    return f"❌ 截图文件未生成:\n{result.stderr}"
            else:
                return f"❌ 截图失败:\n{result.stderr or result.stdout}"
                
        except subprocess.TimeoutExpired:
            return f"❌ 截图超时 (45秒)"
    
    async def _get_title(self, url: str, env) -> str:
        """获取页面标题"""
        if url:
            cmd = f'agent-browser open "{url}" && agent-browser wait --load networkidle && agent-browser get title'
        else:
            cmd = 'agent-browser get title'
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            if result.returncode == 0:
                title = result.stdout.strip()
                if url:
                    return f"✅ 页面标题: {title}\nURL: {url}"
                else:
                    return f"✅ 当前页面标题: {title}"
            else:
                return f"❌ 获取标题失败:\n{result.stderr or result.stdout}"
                
        except subprocess.TimeoutExpired:
            return f"❌ 获取标题超时"
    
    async def _get_text(self, url: str, selector: str, env) -> str:
        """获取元素文本"""
        if not selector:
            return "❌ 需要提供选择器参数"
        
        if url:
            cmd = f'agent-browser open "{url}" && agent-browser wait --load networkidle && agent-browser get text "{selector}"'
        else:
            cmd = f'agent-browser get text "{selector}"'
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            if result.returncode == 0:
                text = result.stdout.strip()
                return f"✅ 元素文本内容:\n{text}"
            else:
                return f"❌ 获取文本失败:\n{result.stderr or result.stdout}"
                
        except subprocess.TimeoutExpired:
            return f"❌ 获取文本超时"
    
    async def _get_snapshot(self, url: str, env, interactive_only: bool = False) -> str:
        """获取页面快照（accessibility tree）"""
        if url:
            cmd = f'agent-browser open "{url}" && agent-browser wait --load networkidle && agent-browser snapshot'
        else:
            cmd = 'agent-browser snapshot'
        
        if interactive_only:
            cmd += " -i"
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            if result.returncode == 0:
                snapshot = result.stdout
                lines = snapshot.split('\n')
                element_count = len([l for l in lines if l.startswith('@e')])
                
                return f"""✅ 页面快照获取成功
元素数量: {element_count}个
交互模式: {'仅交互元素' if interactive_only else '全部元素'}

快照预览（前20行）:
{chr(10).join(lines[:20])}
{'...' if len(lines) > 20 else ''}

提示: 使用元素引用（如@e1）可以在后续命令中操作特定元素"""
            else:
                return f"❌ 获取快照失败:\n{result.stderr or result.stdout}"
                
        except subprocess.TimeoutExpired:
            return f"❌ 获取快照超时"
    
    async def _close_browser(self, env) -> str:
        """关闭浏览器daemon"""
        result = subprocess.run(
            "agent-browser close",
            shell=True,
            capture_output=True,
            text=True,
            env=env
        )
        
        if result.returncode == 0:
            return "✅ 浏览器daemon已关闭"
        else:
            return f"❌ 关闭浏览器失败:\n{result.stderr or result.stdout}"
    
    async def _run_script(self, script: str, env) -> str:
        """运行自定义脚本"""
        if not script:
            return "❌ 需要提供脚本内容"
        
        # 创建临时脚本文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write("#!/bin/bash\n")
            f.write(f"export PATH=\"$HOME/.cargo/bin:$PATH\"\n")
            f.write(script)
            script_path = f.name
        
        try:
            os.chmod(script_path, 0o755)
            result = subprocess.run(
                f"bash {script_path}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )
            
            output = f"脚本执行结果 (退出码: {result.returncode}):\n"
            if result.stdout:
                output += f"\n标准输出:\n{result.stdout[:2000]}{'...' if len(result.stdout) > 2000 else ''}"
            if result.stderr:
                output += f"\n标准错误:\n{result.stderr[:1000]}{'...' if len(result.stderr) > 1000 else ''}"
            
            return output
            
        except subprocess.TimeoutExpired:
            return "❌ 脚本执行超时 (60秒)"
        finally:
            if Path(script_path).exists():
                Path(script_path).unlink()