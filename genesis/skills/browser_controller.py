import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import sys
from pathlib import Path

class BrowserController(Tool):
    @property
    def name(self) -> str:
        return "browser_controller"
        
    @property
    def description(self) -> str:
        return "浏览器控制器，可以打开网页、截图、获取页面内容等"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string", 
                    "description": "要执行的命令",
                    "enum": ["open_url", "screenshot", "get_content", "check_status", "test_playwright"],
                    "default": "check_status"
                },
                "url": {"type": "string", "description": "要打开的URL"},
                "output_file": {"type": "string", "description": "输出文件路径"},
                "timeout": {"type": "integer", "description": "超时时间（秒）", "default": 30}
            },
            "required": ["command"]
        }
        
    async def execute(self, command: str, **kwargs) -> str:
        try:
            if command == "check_status":
                return await self._check_status()
            elif command == "open_url":
                return await self._open_url(kwargs.get("url", "https://www.google.com"))
            elif command == "screenshot":
                return await self._screenshot(
                    kwargs.get("url", "https://www.google.com"),
                    kwargs.get("output_file", "/tmp/browser_screenshot.png")
                )
            elif command == "get_content":
                return await self._get_content(kwargs.get("url", "https://www.google.com"))
            elif command == "test_playwright":
                return await self._test_playwright()
            else:
                return f"❌ 不支持的命令: {command}"
                
        except Exception as e:
            return f"❌ 执行失败: {str(e)}"
    
    async def _check_status(self) -> str:
        """检查浏览器状态"""
        results = []
        
        # 1. 检查Chrome
        chrome_check = subprocess.run(
            ["google-chrome-stable", "--version"],
            capture_output=True,
            text=True
        )
        if chrome_check.returncode == 0:
            results.append(f"✅ Chrome: {chrome_check.stdout.strip()}")
        else:
            results.append("❌ Chrome: 不可用")
        
        # 2. 检查Playwright
        playwright_check = subprocess.run(
            ["playwright", "--version"],
            capture_output=True,
            text=True
        )
        if playwright_check.returncode == 0:
            results.append(f"✅ Playwright: {playwright_check.stdout.strip()}")
        else:
            results.append("❌ Playwright: 不可用")
        
        # 3. 检查browser-use包
        pip_check = subprocess.run(
            [sys.executable, "-m", "pip", "show", "browser-use"],
            capture_output=True,
            text=True
        )
        if pip_check.returncode == 0:
            # 提取版本信息
            for line in pip_check.stdout.split('\n'):
                if line.startswith('Version:'):
                    version = line.split(':')[1].strip()
                    results.append(f"✅ Browser-use: {version}")
                    break
        else:
            results.append("❌ Browser-use: 未安装")
        
        # 4. 测试网络连接
        network_check = subprocess.run(
            ["curl", "-s", "-I", "-L", "--max-time", "10", "https://www.google.com"],
            capture_output=True,
            text=True
        )
        if network_check.returncode == 0:
            for line in network_check.stdout.split('\n'):
                if line.startswith('HTTP/'):
                    results.append(f"✅ 网络连接: {line.strip()}")
                    break
        else:
            results.append("❌ 网络连接: 失败")
        
        return "📊 浏览器状态检查:\n\n" + "\n".join(results)
    
    async def _open_url(self, url: str) -> str:
        """使用系统浏览器打开URL"""
        try:
            # 使用xdg-open打开URL（使用默认浏览器）
            result = subprocess.run(
                ["xdg-open", url],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return f"✅ 已尝试打开URL: {url}\n\n💡 提示：浏览器窗口应该已经弹出。如果没有，请检查桌面环境。"
            else:
                # 尝试直接使用Chrome
                chrome_result = subprocess.Popen(
                    ["google-chrome-stable", url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                return f"✅ 已启动Chrome打开URL: {url}\n\n💡 Chrome已在后台运行。"
                
        except Exception as e:
            return f"❌ 打开URL失败: {str(e)}"
    
    async def _screenshot(self, url: str, output_file: str) -> str:
        """使用playwright截图"""
        script = f'''
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("{url}", timeout=30000)
            await page.screenshot(path="{output_file}", full_page=True)
            print("SUCCESS")
        except Exception as e:
            print(f"ERROR: {{e}}")
        finally:
            await browser.close()

asyncio.run(main())
'''
        
        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=35
            )
            
            if "SUCCESS" in result.stdout:
                if Path(output_file).exists():
                    size = Path(output_file).stat().st_size
                    return f"✅ 截图成功！\n文件: {output_file}\n大小: {size} bytes"
                else:
                    return f"❌ 截图文件未生成"
            else:
                return f"❌ 截图失败: {result.stderr or result.stdout}"
                
        except subprocess.TimeoutExpired:
            return "❌ 截图超时"
        except Exception as e:
            return f"❌ 截图错误: {str(e)}"
    
    async def _get_content(self, url: str) -> str:
        """获取页面内容"""
        script = f'''
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("{url}", timeout=30000)
            title = await page.title()
            content = await page.content()
            text = await page.evaluate('() => document.body.innerText')
            
            print("=== PAGE INFO ===")
            print(f"URL: {{page.url}}")
            print(f"Title: {{title}}")
            print(f"Content length: {{len(content)}} chars")
            print("\\n=== TEXT PREVIEW ===")
            print(text[:1500])
            if len(text) > 1500:
                print("... [truncated]")
        except Exception as e:
            print(f"ERROR: {{e}}")
        finally:
            await browser.close()

asyncio.run(main())
'''
        
        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=35
            )
            
            if "=== PAGE INFO ===" in result.stdout:
                return f"✅ 页面内容获取成功:\n\n{result.stdout}"
            else:
                return f"❌ 获取内容失败: {result.stderr or result.stdout}"
                
        except subprocess.TimeoutExpired:
            return "❌ 获取内容超时"
        except Exception as e:
            return f"❌ 获取内容错误: {str(e)}"
    
    async def _test_playwright(self) -> str:
        """测试playwright功能"""
        script = '''
import asyncio
from playwright.async_api import async_playwright

async def main():
    results = []
    async with async_playwright() as p:
        # 测试浏览器启动
        browser = await p.chromium.launch(headless=True)
        results.append("✅ Chromium浏览器启动成功")
        
        # 测试页面创建
        page = await browser.new_page()
        results.append("✅ 页面创建成功")
        
        # 测试导航
        try:
            response = await page.goto("https://www.example.com", timeout=10000)
            if response:
                results.append(f"✅ 导航成功，状态码: {response.status}")
            else:
                results.append("❌ 导航失败，无响应")
        except Exception as e:
            results.append(f"❌ 导航失败: {e}")
        
        # 测试页面操作
        try:
            title = await page.title()
            results.append(f"✅ 获取标题成功: {title}")
        except:
            results.append("❌ 获取标题失败")
        
        await browser.close()
        results.append("✅ 浏览器关闭成功")
    
    print("\\n".join(results))

asyncio.run(main())
'''
        
        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=20
            )
            
            return f"🔧 Playwright功能测试:\n\n{result.stdout}\n\n{result.stderr if result.stderr else ''}"
            
        except subprocess.TimeoutExpired:
            return "❌ Playwright测试超时"
        except Exception as e:
            return f"❌ Playwright测试错误: {str(e)}"