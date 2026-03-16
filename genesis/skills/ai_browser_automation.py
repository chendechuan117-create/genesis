import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import asyncio
import subprocess
import tempfile
import json
from pathlib import Path
import sys

class AiBrowserAutomation(Tool):
    @property
    def name(self) -> str:
        return "ai_browser_automation"
        
    @property
    def description(self) -> str:
        return "AI驱动的浏览器自动化工具，可以执行网页浏览、表单填写、截图等操作"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "description": "要执行的操作类型",
                    "enum": ["open_url", "take_screenshot", "get_page_content", "fill_form", "click_element", "run_script"],
                    "default": "open_url"
                },
                "url": {"type": "string", "description": "要打开的URL"},
                "selector": {"type": "string", "description": "CSS选择器或XPath"},
                "text": {"type": "string", "description": "要输入的文本"},
                "script": {"type": "string", "description": "要执行的JavaScript代码"},
                "output_path": {"type": "string", "description": "输出文件路径"},
                "headless": {"type": "boolean", "description": "是否使用无头模式", "default": True},
                "timeout": {"type": "integer", "description": "超时时间（秒）", "default": 30}
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, **kwargs) -> str:
        try:
            if action == "open_url":
                return await self._open_url(**kwargs)
            elif action == "take_screenshot":
                return await self._take_screenshot(**kwargs)
            elif action == "get_page_content":
                return await self._get_page_content(**kwargs)
            elif action == "fill_form":
                return await self._fill_form(**kwargs)
            elif action == "click_element":
                return await self._click_element(**kwargs)
            elif action == "run_script":
                return await self._run_script(**kwargs)
            else:
                return f"❌ 不支持的操作类型: {action}"
                
        except Exception as e:
            return f"❌ 浏览器自动化执行失败: {str(e)}"
    
    async def _open_url(self, url: str, headless: bool = True, timeout: int = 30, **kwargs) -> str:
        """打开URL并获取页面信息"""
        try:
            # 创建一个简单的Python脚本使用playwright
            script_content = f'''
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless={headless})
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            response = await page.goto("{url}", timeout={timeout*1000})
            status = response.status if response else "No response"
            title = await page.title()
            
            # 获取页面基本信息
            url_actual = page.url
            content_length = len(await page.content())
            
            print(f"URL: {{url_actual}}")
            print(f"Status: {{status}}")
            print(f"Title: {{title}}")
            print(f"Content length: {{content_length}} chars")
            
            # 检查页面是否有常见元素
            has_forms = await page.query_selector("form") is not None
            has_inputs = await page.query_selector("input") is not None
            has_buttons = await page.query_selector("button") is not None
            
            print(f"Has forms: {{has_forms}}")
            print(f"Has inputs: {{has_inputs}}")
            print(f"Has buttons: {{has_buttons}}")
            
        except Exception as e:
            print(f"Error: {{str(e)}}")
        finally:
            await browser.close()

asyncio.run(main())
'''
            
            # 执行脚本
            result = subprocess.run(
                [sys.executable, "-c", script_content],
                capture_output=True,
                text=True,
                timeout=timeout + 5
            )
            
            if result.returncode == 0:
                return f"✅ 成功打开URL: {url}\n\n{result.stdout}"
            else:
                return f"❌ 打开URL失败: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return f"❌ 操作超时 ({timeout}秒)"
        except Exception as e:
            return f"❌ 执行错误: {str(e)}"
    
    async def _take_screenshot(self, url: str, output_path: str = None, headless: bool = True, **kwargs) -> str:
        """截图网页"""
        try:
            if not output_path:
                output_path = f"/tmp/screenshot_{hash(url) % 10000}.png"
            
            script_content = f'''
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless={headless})
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto("{url}", timeout=30000)
            await page.screenshot(path="{output_path}", full_page=True)
            print(f"Screenshot saved to: {{'{output_path}'}}")
        finally:
            await browser.close()

asyncio.run(main())
'''
            
            result = subprocess.run(
                [sys.executable, "-c", script_content],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # 检查文件是否存在
                if Path(output_path).exists():
                    file_size = Path(output_path).stat().st_size
                    return f"✅ 截图成功保存到: {output_path} ({file_size} bytes)\n{result.stdout}"
                else:
                    return f"❌ 截图文件未生成: {result.stderr}"
            else:
                return f"❌ 截图失败: {result.stderr}"
                
        except Exception as e:
            return f"❌ 截图错误: {str(e)}"
    
    async def _get_page_content(self, url: str, headless: bool = True, **kwargs) -> str:
        """获取页面内容"""
        try:
            script_content = f'''
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless={headless})
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto("{url}", timeout=30000)
            content = await page.content()
            
            # 提取重要信息
            title = await page.title()
            url_actual = page.url
            
            # 获取文本内容（去除HTML标签）
            text_content = await page.evaluate('''() => {{
                return document.body.innerText;
            }}''')
            
            print(f"URL: {{url_actual}}")
            print(f"Title: {{title}}")
            print("\\n=== 页面文本内容（前1000字符） ===")
            print(text_content[:1000] + ("..." if len(text_content) > 1000 else ""))
            
        finally:
            await browser.close()

asyncio.run(main())
'''
            
            result = subprocess.run(
                [sys.executable, "-c", script_content],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return f"✅ 页面内容获取成功:\n\n{result.stdout}"
            else:
                return f"❌ 获取页面内容失败: {result.stderr}"
                
        except Exception as e:
            return f"❌ 获取内容错误: {str(e)}"
    
    async def _fill_form(self, url: str, selector: str, text: str, headless: bool = True, **kwargs) -> str:
        """填写表单"""
        return "⚠️ 表单填写功能需要更复杂的实现，建议使用完整的browser-use工具"
    
    async def _click_element(self, url: str, selector: str, headless: bool = True, **kwargs) -> str:
        """点击元素"""
        return "⚠️ 元素点击功能需要更复杂的实现，建议使用完整的browser-use工具"
    
    async def _run_script(self, url: str, script: str, headless: bool = True, **kwargs) -> str:
        """执行JavaScript"""
        return "⚠️ JavaScript执行功能需要更复杂的实现，建议使用完整的browser-use工具"