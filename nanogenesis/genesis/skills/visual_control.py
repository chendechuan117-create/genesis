import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import time
import os
import tempfile
import json

class VisualControl(Tool):
    @property
    def name(self) -> str:
        return "visual_control"
        
    @property
    def description(self) -> str:
        return "视觉控制工具。使用系统命令实现屏幕捕获和鼠标键盘模拟。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["screenshot", "mouse_move", "mouse_click", "keyboard_type", "get_mouse_pos", "open_browser"],
                    "description": "操作类型：screenshot(截图), mouse_move(移动鼠标), mouse_click(点击), keyboard_type(键盘输入), get_mouse_pos(获取鼠标位置), open_browser(打开浏览器)"
                },
                "x": {
                    "type": "integer",
                    "description": "X坐标（mouse_move需要）"
                },
                "y": {
                    "type": "integer",
                    "description": "Y坐标（mouse_move需要）"
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "鼠标按钮：left(左键), right(右键), middle(中键)，默认left"
                },
                "text": {
                    "type": "string",
                    "description": "要输入的文本（keyboard_type需要）"
                },
                "url": {
                    "type": "string",
                    "description": "要打开的URL（open_browser需要）"
                },
                "filename": {
                    "type": "string",
                    "description": "截图保存文件名（screenshot需要）"
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, x: int = None, y: int = None, button: str = "left", 
                     text: str = None, url: str = None, filename: str = None) -> str:
        
        try:
            if action == "screenshot":
                return await self._take_screenshot(filename)
                
            elif action == "mouse_move":
                return await self._move_mouse(x, y)
                
            elif action == "mouse_click":
                return await self._click_mouse(button, x, y)
                
            elif action == "keyboard_type":
                return await self._type_text(text)
                
            elif action == "get_mouse_pos":
                return await self._get_mouse_position()
                
            elif action == "open_browser":
                return await self._open_browser(url)
                
            else:
                return f"❌ 未知操作: {action}"
                
        except Exception as e:
            return f"❌ 视觉控制失败: {str(e)}"
    
    async def _take_screenshot(self, filename: str = None) -> str:
        """使用scrot截图"""
        if filename is None:
            temp_dir = tempfile.gettempdir()
            filename = os.path.join(temp_dir, f"screenshot_{int(time.time())}.png")
        
        # 使用scrot命令截图
        result = subprocess.run(["scrot", "-q", "100", filename], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            # 获取文件信息
            file_size = os.path.getsize(filename) if os.path.exists(filename) else 0
            return f"✅ 截图已保存: {filename}\n大小: {file_size} 字节"
        else:
            return f"❌ 截图失败: {result.stderr}"
    
    async def _move_mouse(self, x: int, y: int) -> str:
        """使用xdotool移动鼠标"""
        if x is None or y is None:
            return "❌ 需要提供x和y坐标"
        
        result = subprocess.run(["xdotool", "mousemove", str(x), str(y)], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            return f"✅ 鼠标已移动到 ({x}, {y})"
        else:
            # 如果xdotool不可用，尝试其他方法
            return f"❌ 移动鼠标失败: {result.stderr}"
    
    async def _click_mouse(self, button: str, x: int = None, y: int = None) -> str:
        """使用xdotool点击鼠标"""
        cmd = ["xdotool", "click"]
        
        # 映射按钮名称
        button_map = {"left": "1", "right": "3", "middle": "2"}
        if button not in button_map:
            return f"❌ 无效的按钮: {button}"
        
        cmd.append(button_map[button])
        
        # 如果提供了坐标，先移动再点击
        if x is not None and y is not None:
            move_result = await self._move_mouse(x, y)
            if "失败" in move_result:
                return move_result
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            pos_info = f"在 ({x}, {y})" if x and y else ""
            return f"✅ 已点击鼠标{button}键 {pos_info}"
        else:
            return f"❌ 点击失败: {result.stderr}"
    
    async def _type_text(self, text: str) -> str:
        """使用xdotool输入文本"""
        if not text:
            return "❌ 未提供要输入的文本"
        
        # 转义特殊字符
        escaped_text = text.replace('"', '\\"').replace("'", "\\'")
        
        result = subprocess.run(["xdotool", "type", "--clearmodifiers", escaped_text], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            return f"✅ 已输入文本: {text}"
        else:
            return f"❌ 输入失败: {result.stderr}"
    
    async def _get_mouse_position(self) -> str:
        """获取鼠标当前位置"""
        try:
            # 尝试使用xdotool
            result = subprocess.run(["xdotool", "getmouselocation"], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                # 解析输出格式: x:123 y:456 screen:0 window:12345
                lines = result.stdout.strip().split()
                pos = {}
                for line in lines:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        pos[key] = value
                
                x = pos.get("x", "未知")
                y = pos.get("y", "未知")
                return f"✅ 鼠标位置: x={x}, y={y}"
            else:
                return "❌ 无法获取鼠标位置 (xdotool不可用)"
                
        except Exception as e:
            return f"❌ 获取鼠标位置失败: {str(e)}"
    
    async def _open_browser(self, url: str) -> str:
        """打开浏览器"""
        if not url:
            url = "http://localhost:2017"  # v2raya默认地址
        
        # 使用xdg-open打开URL
        result = subprocess.run(["xdg-open", url], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            return f"✅ 已打开浏览器访问: {url}"
        else:
            return f"❌ 打开浏览器失败: {result.stderr}"