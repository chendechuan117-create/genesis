import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class SafeAiBrowser(Tool):
    @property
    def name(self) -> str:
        return "safe_ai_browser"
        
    @property
    def description(self) -> str:
        return "安全的内存友好型AI浏览器自动化工具。使用browser-use进行网页自动化，但避免启动Web UI和长时间运行进程。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "要执行的浏览器任务，如'打开百度搜索AI技术'"},
                "timeout_seconds": {"type": "integer", "description": "任务超时时间（秒），默认60", "default": 60},
                "headless": {"type": "boolean", "description": "是否使用无头模式（不显示浏览器窗口），默认true", "default": True}
            },
            "required": ["task"]
        }
        
    async def execute(self, task: str, timeout_seconds: int = 60, headless: bool = True) -> str:
        import asyncio
        import subprocess
        import sys
        from pathlib import Path
        
        try:
            # 检查browser-use是否安装
            try:
                from browser_use import Agent
                from browser_use.browser.context import BrowserContextConfig
            except ImportError as e:
                return f"❌ 需要安装browser-use: {e}\n请运行: pip install browser-use"
            
            # 检查Playwright浏览器
            playwright_check = subprocess.run(['playwright', '--version'], capture_output=True, text=True)
            if playwright_check.returncode != 0:
                return "❌ Playwright未安装。请运行: playwright install"
            
            # 创建临时日志文件
            log_file = Path.home() / ".genesis" / "logs" / "browser_use.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 使用subprocess在后台运行，避免阻塞主线程
            script_content = f'''
import asyncio
import sys
from browser_use import Agent
from browser_use.browser.context import BrowserContextConfig

async def run_task():
    try:
        print(f"🚀 开始执行任务: {{sys.argv[1]}}")
        
        # 配置浏览器上下文（内存友好）
        config = BrowserContextConfig(
            headless={str(headless).lower()},
            viewport={{'width': 1280, 'height': 720}},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        # 创建Agent（使用本地LLM或模拟）
        agent = Agent(
            task=sys.argv[1],
            llm=None,  # 暂时不连接LLM，只测试浏览器功能
            browser_context_config=config
        )
        
        # 执行任务（带超时）
        try:
            result = await asyncio.wait_for(agent.run(), timeout={timeout_seconds})
            print(f"✅ 任务完成: {{result}}")
            return str(result)
        except asyncio.TimeoutError:
            print(f"⏰ 任务超时 ({timeout_seconds}秒)")
            return "任务超时"
            
    except Exception as e:
        print(f"❌ 执行出错: {{e}}")
        return f"错误: {{e}}"

if __name__ == "__main__":
    result = asyncio.run(run_task())
    print(result)
'''
            
            # 写入临时脚本
            temp_script = Path.home() / ".genesis" / "temp_browser_task.py"
            temp_script.write_text(script_content)
            
            # 在后台运行
            process = subprocess.Popen(
                [sys.executable, str(temp_script), task],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # 等待一段时间获取输出
            try:
                stdout, stderr = process.communicate(timeout=10)
                output = stdout if stdout else stderr
                
                # 清理临时文件
                temp_script.unlink(missing_ok=True)
                
                return f"✅ 任务已启动（后台运行）\n输出:\n{output}"
                
            except subprocess.TimeoutExpired:
                # 进程仍在运行，返回状态
                return f"🔄 任务正在后台执行（PID: {process.pid}）\n任务: {task}\n将在最多{timeout_seconds}秒内完成"
                
        except Exception as e:
            return f"❌ 执行失败: {e}"
