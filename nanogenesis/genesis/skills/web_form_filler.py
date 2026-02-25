import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class WebFormFiller(Tool):
    @property
    def name(self) -> str:
        return "web_form_filler"

    @property
    def description(self) -> str:
        return "使用 Playwright 自动在浏览器中填写网页表单。适用于创作者申请、注册等流程。需要目标URL和字段数据字典。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要填写的表单页面URL"},
                "form_data": {
                    "type": "object",
                    "description": "表单字段数据，键为字段名/选择器，值为要填写的内容。例如：{'#name': '张三', 'input[type=\"email\"]': 'test@example.com'}",
                    "additionalProperties": {"type": "string"}
                },
                "headless": {"type": "boolean", "description": "是否使用无头模式（不显示浏览器界面），默认为True", "default": True},
                "submit": {"type": "boolean", "description": "是否在填写后点击提交按钮（尝试寻找type='submit'的按钮）", "default": False}
            },
            "required": ["url", "form_data"]
        }

    async def execute(self, url: str, form_data: dict, headless: bool = True, submit: bool = False) -> str:
        import asyncio
        from playwright.async_api import async_playwright
        import json

        async def fill_form():
            async with async_playwright() as p:
                # 安装浏览器（如果尚未安装）
                try:
                    browser = await p.chromium.launch(headless=headless)
                except Exception as e:
                    # 尝试安装playwright浏览器
                    import subprocess
                    subprocess.run(["playwright", "install", "chromium"], capture_output=True)
                    browser = await p.chromium.launch(headless=headless)

                page = await browser.new_page()
                try:
                    await page.goto(url, wait_until="networkidle")
                except Exception as e:
                    await browser.close()
                    return f"导航到页面失败: {e}"

                filled_fields = []
                for selector, value in form_data.items():
                    try:
                        element = await page.wait_for_selector(selector, timeout=5000)
                        await element.fill(value)
                        filled_fields.append(selector)
                    except Exception as e:
                        # 如果找不到精确选择器，尝试通过placeholder、name、id等属性查找
                        try:
                            # 尝试多种查找方式
                            element = await page.query_selector(f'[name="{selector}"], [id="{selector}"], [placeholder*="{selector}"]')
                            if element:
                                await element.fill(value)
                                filled_fields.append(selector)
                            else:
                                return f"无法找到字段: {selector}。请提供更精确的CSS选择器。"
                        except Exception as e2:
                            return f"填写字段 '{selector}' 时出错: {e2}"

                if submit:
                    try:
                        # 尝试点击提交按钮
                        await page.click('button[type="submit"], input[type="submit"]')
                        await page.wait_for_timeout(2000)  # 等待提交后页面变化
                    except Exception as e:
                        # 如果找不到特定提交按钮，尝试点击第一个按钮或包含"提交"文本的按钮
                        try:
                            await page.click('button:has-text("提交"), button:has-text("Submit"), button:first-of-type')
                            await page.wait_for_timeout(2000)
                        except Exception as e2:
                            return f"表单填写成功（字段: {filled_fields}），但提交按钮点击失败: {e2}。请手动检查页面。"

                # 截图以供验证
                screenshot_path = "/tmp/form_filled.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                await browser.close()
                return f"表单填写完成。已填充字段: {filled_fields}。截图已保存至: {screenshot_path}。{'已尝试提交。' if submit else '未执行提交，请手动检查并提交。'}"

        # 运行异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(fill_form())
        finally:
            loop.close()
        return result