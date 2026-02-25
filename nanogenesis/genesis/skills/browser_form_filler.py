import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class BrowserFormFiller(Tool):
    @property
    def name(self) -> str:
        return "browser_form_filler"
        
    @property
    def description(self) -> str:
        return "使用Playwright自动化浏览器操作，导航到指定URL并填写表单。适用于创作者申请流程等表单填写任务。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要访问的网页URL"},
                "form_data": {"type": "object", "description": "表单字段数据，键值对格式"},
                "screenshot_path": {"type": "string", "description": "截图保存路径（可选）", "default": ""}
            },
            "required": ["url", "form_data"]
        }
        
    async def execute(self, url: str, form_data: dict, screenshot_path: str = "") -> str:
        import asyncio
        from playwright.async_api import async_playwright
        import json
        
        try:
            # 启动Playwright
            async with async_playwright() as p:
                # 启动浏览器（默认使用Chromium）
                browser = await p.chromium.launch(headless=False)  # 显示浏览器以便调试
                context = await browser.new_context()
                page = await context.new_page()
                
                # 导航到目标URL
                await page.goto(url)
                await page.wait_for_load_state('networkidle')
                
                # 填写表单字段
                filled_fields = []
                for field_name, field_value in form_data.items():
                    try:
                        # 尝试多种选择器策略
                        selectors = [
                            f'input[name="{field_name}"]',
                            f'textarea[name="{field_name}"]',
                            f'[id="{field_name}"]',
                            f'[data-name="{field_name}"]',
                            f'input[placeholder*="{field_name}"]',
                            f'textarea[placeholder*="{field_name}"]',
                        ]
                        
                        filled = False
                        for selector in selectors:
                            if await page.locator(selector).count() > 0:
                                await page.fill(selector, str(field_value))
                                filled_fields.append(f"{field_name}: {field_value}")
                                filled = True
                                break
                        
                        if not filled:
                            # 尝试通过标签文本查找
                            try:
                                await page.get_by_label(field_name).fill(str(field_value))
                                filled_fields.append(f"{field_name}: {field_value}")
                            except:
                                pass
                    except Exception as e:
                        return f"填写字段 {field_name} 时出错: {str(e)}"
                
                # 可选：截图
                if screenshot_path:
                    await page.screenshot(path=screenshot_path)
                
                # 等待一会儿让用户看到结果
                await asyncio.sleep(2)
                
                # 关闭浏览器
                await browser.close()
                
                return f"表单填写完成！已填写的字段：{', '.join(filled_fields)}。页面URL：{url}"
                
        except Exception as e:
            return f"浏览器自动化失败：{str(e)}。请确保已安装Playwright：'pip install playwright && playwright install'"