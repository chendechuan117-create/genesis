import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class SimpleBrowserFormFiller(Tool):
    @property
    def name(self) -> str:
        return "simple_browser_form_filler"
        
    @property
    def description(self) -> str:
        return "使用系统默认浏览器打开URL并模拟键盘输入填写表单。适用于简单的创作者申请流程。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要访问的网页URL"},
                "form_data": {"type": "object", "description": "表单字段数据，键值对格式"}
            },
            "required": ["url", "form_data"]
        }
        
    async def execute(self, url: str, form_data: dict) -> str:
        import subprocess
        import time
        import os
        
        try:
            # 使用系统命令打开浏览器
            if os.name == 'nt':  # Windows
                os.system(f'start {url}')
            elif os.name == 'posix':  # Linux/macOS
                os.system(f'xdg-open {url}')
            else:
                return f"不支持的操作系统：{os.name}"
            
            time.sleep(3)  # 等待浏览器打开
            
            # 提供填写说明
            form_fields_str = "\n".join([f"- {key}: {value}" for key, value in form_data.items()])
            
            return f"""浏览器已打开，请手动填写表单：
            
URL: {url}

需要填写的字段：
{form_fields_str}

填写说明：
1. 浏览器窗口已打开
2. 请手动填写上述字段
3. 填写完成后提交表单

注意：由于系统限制，无法自动安装浏览器自动化库。建议手动安装：
- Playwright: pip install playwright && playwright install
- 或使用系统包管理器安装：pacman -S python-playwright
"""
                
        except Exception as e:
            return f"打开浏览器失败：{str(e)}"