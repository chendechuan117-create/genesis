import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class MouseController(Tool):
    @property
    def name(self) -> str:
        return "mouse_controller"
        
    @property
    def description(self) -> str:
        return "鼠标模拟控制器。可以移动鼠标、点击、拖拽、滚动等操作。用于自动化GUI交互，特别是当API/命令与视觉界面不一致时。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["move", "click", "double_click", "right_click", "drag", "scroll", "get_position"],
                    "description": "鼠标操作类型"
                },
                "x": {
                    "type": "integer", 
                    "description": "X坐标（像素），屏幕左上角为(0,0)"
                },
                "y": {
                    "type": "integer", 
                    "description": "Y坐标（像素），屏幕左上角为(0,0)"
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "鼠标按钮（仅click/double_click/right_click需要）",
                    "default": "left"
                },
                "duration": {
                    "type": "number",
                    "description": "拖拽持续时间（秒，仅drag需要）",
                    "default": 0.5
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "滚动量（正数向上，负数向下，仅scroll需要）",
                    "default": 10
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, x: int = None, y: int = None, button: str = "left", duration: float = 0.5, scroll_amount: int = 10) -> str:
        import subprocess
        import time
        
        # 获取屏幕分辨率（用于坐标验证）
        def get_screen_resolution():
            try:
                result = subprocess.run(["xrandr"], capture_output=True, text=True, check=True)
                for line in result.stdout.split('\n'):
                    if '*' in line:
                        # 解析分辨率，如 "2560x1440"
                        parts = line.strip().split()
                        for part in parts:
                            if 'x' in part and '*' in part:
                                res = part.replace('*', '')
                                width, height = map(int, res.split('x'))
                                return width, height
                return 1920, 1080  # 默认值
            except:
                return 1920, 1080
        
        screen_width, screen_height = get_screen_resolution()
        
        if action == "get_position":
            # 获取当前鼠标位置
            try:
                result = subprocess.run(["xdotool", "getmouselocation"], capture_output=True, text=True, check=True)
                # 输出格式: "x:123 y:456 screen:0 window:12345678"
                return f"当前鼠标位置: {result.stdout.strip()}"
            except Exception as e:
                return f"获取鼠标位置失败: {str(e)}"
        
        elif action == "move":
            if x is None or y is None:
                return "移动鼠标需要x和y坐标"
            
            # 验证坐标在屏幕范围内
            if x < 0 or x >= screen_width or y < 0 or y >= screen_height:
                return f"坐标({x},{y})超出屏幕范围({screen_width}x{screen_height})"
            
            try:
                subprocess.run(["xdotool", "mousemove", str(x), str(y)], check=True)
                return f"鼠标已移动到({x},{y})"
            except Exception as e:
                return f"移动鼠标失败: {str(e)}"
        
        elif action in ["click", "double_click", "right_click"]:
            if x is not None and y is not None:
                # 先移动到指定位置
                move_result = await self.execute("move", x, y)
                if "失败" in move_result:
                    return move_result
            
            try:
                if action == "click":
                    subprocess.run(["xdotool", "click", "1"], check=True)  # 1=左键
                    return f"在当前位置点击{button}键"
                elif action == "double_click":
                    subprocess.run(["xdotool", "click", "--repeat", "2", "1"], check=True)
                    return f"在当前位置双击{button}键"
                elif action == "right_click":
                    subprocess.run(["xdotool", "click", "3"], check=True)  # 3=右键
                    return f"在当前位置右键点击"
            except Exception as e:
                return f"点击操作失败: {str(e)}"
        
        elif action == "drag":
            if x is None or y is None:
                return "拖拽需要目标坐标x和y"
            
            try:
                # 按下鼠标
                subprocess.run(["xdotool", "mousedown", "1"], check=True)
                time.sleep(0.1)
                
                # 移动到目标位置
                subprocess.run(["xdotool", "mousemove", str(x), str(y)], check=True)
                time.sleep(duration)
                
                # 释放鼠标
                subprocess.run(["xdotool", "mouseup", "1"], check=True)
                return f"从当前位置拖拽到({x},{y})，持续时间{duration}秒"
            except Exception as e:
                return f"拖拽失败: {str(e)}"
        
        elif action == "scroll":
            try:
                # xdotool的wheel参数：正数向上，负数向下
                subprocess.run(["xdotool", "click", "4"] if scroll_amount > 0 else ["xdotool", "click", "5"], check=True)
                direction = "向上" if scroll_amount > 0 else "向下"
                return f"鼠标滚轮{direction}滚动{abs(scroll_amount)}单位"
            except Exception as e:
                return f"滚动失败: {str(e)}"
        
        else:
            return f"未知操作: {action}"