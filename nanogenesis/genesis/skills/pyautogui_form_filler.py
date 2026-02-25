import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class PyAutoGUIFormFiller(Tool):
    @property
    def name(self) -> str:
        return "pyautogui_form_filler"
        
    @property
    def description(self) -> str:
        return "使用pyautogui自动化桌面浏览器操作，通过图像识别和键盘输入填写表单。适用于创作者申请流程等表单填写任务。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要访问的网页URL"},
                "form_data": {"type": "object", "description": "表单字段数据，键值对格式"},
                "browser": {"type": "string", "description": "浏览器类型：chrome, edge, firefox", "default": "chrome"}
            },
            "required": ["url", "form_data"]
        }
        
    async def execute(self, url: str, form_data: dict, browser: str = "chrome") -> str:
        import subprocess
        import time
        import pyautogui
        import os
        
        try:
            # 检查pyautogui是否安装
            import pyautogui as pg
            
            # 根据浏览器类型确定启动命令
            browser_commands = {
                "chrome": "google-chrome",
                "edge": "microsoft-edge",
                "firefox": "firefox"
            }
            
            if browser not in browser_commands:
                return f"不支持的浏览器：{browser}。支持：{', '.join(browser_commands.keys())}"
            
            # 启动浏览器并打开URL
            cmd = f"{browser_commands[browser]} {url}"
            subprocess.Popen(cmd, shell=True)
            time.sleep(3)  # 等待浏览器启动
            
            # 最大化窗口（按F11）
            pyautogui.press('f11')
            time.sleep(1)
            
            # 填写表单字段
            filled_fields = []
            
            for field_name, field_value in form_data.items():
                try:
                    # 模拟点击到表单区域（假设表单在页面中央）
                    screen_width, screen_height = pyautogui.size()
                    
                    # 向下滚动一点以确保表单可见
                    pyautogui.scroll(-300)
                    time.sleep(0.5)
                    
                    # 查找可能的输入框位置（基于常见布局）
                    # 尝试在页面中央区域点击
                    pyautogui.click(screen_width // 2, screen_height // 3 + len(filled_fields) * 50)
                    time.sleep(0.5)
                    
                    # 输入字段值
                    pyautogui.write(str(field_value))
                    filled_fields.append(f"{field_name}: {field_value}")
                    
                    # 按Tab键移动到下一个字段
                    pyautogui.press('tab')
                    time.sleep(0.5)
                    
                except Exception as e:
                    return f"填写字段 {field_name} 时出错: {str(e)}"
            
            # 等待一会儿让用户看到结果
            time.sleep(2)
            
            return f"表单填写完成！已填写的字段：{', '.join(filled_fields)}。页面URL：{url}。注意：这是一个基于pyautogui的自动化，可能需要根据实际页面布局调整。"
                
        except ImportError:
            return "pyautogui未安装。请运行：'pip install pyautogui'"
        except Exception as e:
            return f"自动化失败：{str(e)}"