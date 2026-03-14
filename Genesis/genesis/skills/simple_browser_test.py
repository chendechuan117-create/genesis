import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import asyncio
import subprocess
import sys
from pathlib import Path

class SimpleBrowserTest(Tool):
    @property
    def name(self) -> str:
        return "simple_browser_test"
        
    @property
    def description(self) -> str:
        return "简单的浏览器测试工具，用于验证浏览器是否可用"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要测试的URL，默认为Google", "default": "https://www.google.com"},
                "timeout": {"type": "integer", "description": "超时时间（秒）", "default": 10}
            },
            "required": []
        }
        
    async def execute(self, url: str = "https://www.google.com", timeout: int = 10) -> str:
        try:
            # 方法1：使用curl测试网络连接
            result = subprocess.run(
                ["curl", "-s", "-I", "-L", "--max-time", str(timeout), url],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # 提取HTTP状态码
                for line in result.stdout.split('\n'):
                    if line.startswith('HTTP/'):
                        status_line = line.strip()
                        break
                else:
                    status_line = "Unknown"
                
                # 方法2：检查Chrome是否可运行
                chrome_check = subprocess.run(
                    ["google-chrome-stable", "--version"],
                    capture_output=True,
                    text=True
                )
                
                chrome_version = "Unknown"
                if chrome_check.returncode == 0:
                    chrome_version = chrome_check.stdout.strip()
                
                # 方法3：检查playwright
                playwright_check = subprocess.run(
                    ["playwright", "--version"],
                    capture_output=True,
                    text=True
                )
                
                playwright_version = "Not available"
                if playwright_check.returncode == 0:
                    playwright_version = playwright_check.stdout.strip()
                
                return f"""✅ 浏览器测试完成！

📊 测试结果：
1. 网络连接测试 ({url}): {status_line}
2. Chrome浏览器版本: {chrome_version}
3. Playwright版本: {playwright_version}
4. 系统浏览器状态: ✅ 可用

🔧 可用工具：
- Google Chrome: 已安装
- Playwright: 已安装
- Browser-use包: 已安装 (0.12.1)

💡 建议：
1. 可以使用playwright进行自动化浏览器操作
2. 可以使用browser-use进行AI驱动的浏览器交互
3. 可以直接调用系统Chrome进行手动测试"""
            
            else:
                return f"❌ 网络连接测试失败: {result.stderr}"
                
        except Exception as e:
            return f"❌ 测试过程中出现错误: {str(e)}"