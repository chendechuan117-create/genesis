import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import time
import os
import tempfile
from pathlib import Path
import pyautogui
import cv2
import numpy as np
import json

class VisualAutomation(Tool):
    @property
    def name(self) -> str:
        return "visual_automation"
        
    @property
    def description(self) -> str:
        return "视觉接管与模拟点击工具。支持屏幕捕获、元素识别、鼠标操作、键盘输入等自动化功能。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["capture", "locate", "click", "type", "drag", "scroll", "hotkey", "record", "playback"],
                    "description": "操作类型：capture(截图), locate(定位元素), click(点击), type(输入), drag(拖拽), scroll(滚动), hotkey(快捷键), record(录制), playback(回放)"
                },
                "target": {
                    "type": "string",
                    "description": "目标元素或坐标。对于locate：可以是图像文件路径或元素描述；对于click：可以是坐标(x,y)或元素名称"
                },
                "text": {
                    "type": "string",
                    "description": "要输入的文本（仅type操作需要）"
                },
                "duration": {
                    "type": "number",
                    "description": "操作持续时间（秒），默认0.5"
                },
                "confidence": {
                    "type": "number",
                    "description": "图像匹配置信度阈值（0-1），默认0.8"
                },
                "region": {
                    "type": "array",
                    "description": "屏幕区域 [x, y, width, height]，默认全屏"
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, target: str = None, text: str = None, 
                     duration: float = 0.5, confidence: float = 0.8, region: list = None) -> str:
        
        try:
            # 确保pyautogui安全设置
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.1
            
            if action == "capture":
                return await self._capture_screen(target, region)
                
            elif action == "locate":
                return await self._locate_element(target, confidence, region)
                
            elif action == "click":
                return await self._click_target(target, duration)
                
            elif action == "type":
                return await self._type_text(text, duration)
                
            elif action == "drag":
                return await self._drag_mouse(target, duration)
                
            elif action == "scroll":
                return await self._scroll_mouse(target)
                
            elif action == "hotkey":
                return await self._press_hotkey(target)
                
            elif action == "record":
                return await self._record_macro(target)
                
            elif action == "playback":
                return await self._playback_macro(target)
                
            else:
                return f"❌ 未知操作: {action}"
                
        except Exception as e:
            return f"❌ 视觉自动化失败: {str(e)}"
    
    async def _capture_screen(self, filename: str = None, region: list = None) -> str:
        """捕获屏幕截图"""
        if filename is None:
            # 生成临时文件名
            temp_dir = tempfile.gettempdir()
            filename = os.path.join(temp_dir, f"screenshot_{int(time.time())}.png")
        
        # 捕获屏幕
        if region:
            screenshot = pyautogui.screenshot(region=tuple(region))
        else:
            screenshot = pyautogui.screenshot()
        
        screenshot.save(filename)
        
        # 获取屏幕信息
        screen_width, screen_height = pyautogui.size()
        mouse_x, mouse_y = pyautogui.position()
        
        return f"✅ 屏幕截图已保存: {filename}\n" \
               f"屏幕尺寸: {screen_width}x{screen_height}\n" \
               f"鼠标位置: ({mouse_x}, {mouse_y})"
    
    async def _locate_element(self, target: str, confidence: float = 0.8, region: list = None) -> str:
        """定位屏幕上的元素"""
        if not os.path.exists(target):
            return f"❌ 目标图像不存在: {target}"
        
        # 读取目标图像
        target_img = cv2.imread(target)
        if target_img is None:
            return f"❌ 无法读取图像: {target}"
        
        # 捕获当前屏幕
        screenshot = pyautogui.screenshot()
        screenshot_np = np.array(screenshot)
        screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
        
        # 模板匹配
        result = cv2.matchTemplate(screenshot_cv, target_img, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val < confidence:
            return f"❌ 未找到匹配元素 (置信度: {max_val:.2f} < {confidence})"
        
        # 计算中心坐标
        h, w = target_img.shape[:2]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        
        return f"✅ 找到匹配元素\n" \
               f"位置: ({center_x}, {center_y})\n" \
               f"置信度: {max_val:.2f}\n" \
               f"区域: [{max_loc[0]}, {max_loc[1]}, {w}, {h}]"
    
    async def _click_target(self, target: str, duration: float = 0.5) -> str:
        """点击目标"""
        if target is None:
            # 点击当前位置
            pyautogui.click()
            return "✅ 点击了当前位置"
        
        # 检查是否是坐标格式 "x,y"
        if "," in target:
            try:
                x, y = map(int, target.split(","))
                pyautogui.click(x, y, duration=duration)
                return f"✅ 点击了坐标 ({x}, {y})"
            except ValueError:
                return f"❌ 坐标格式错误: {target}"
        
        # 否则认为是图像文件，先定位再点击
        locate_result = await self._locate_element(target)
        if "位置:" not in locate_result:
            return f"❌ 无法定位目标: {target}\n{locate_result}"
        
        # 提取坐标
        import re
        match = re.search(r"位置: \((\d+), (\d+)\)", locate_result)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            pyautogui.click(x, y, duration=duration)
            return f"✅ 点击了目标: {target}\n坐标: ({x}, {y})"
        
        return f"❌ 无法从定位结果提取坐标: {locate_result}"
    
    async def _type_text(self, text: str, duration: float = 0.5) -> str:
        """输入文本"""
        if not text:
            return "❌ 未提供要输入的文本"
        
        pyautogui.typewrite(text, interval=duration/len(text))
        return f"✅ 已输入文本: {text}"
    
    async def _drag_mouse(self, target: str, duration: float = 0.5) -> str:
        """拖拽鼠标"""
        if not target or "," not in target:
            return "❌ 需要目标坐标格式: 'x,y'"
        
        try:
            x, y = map(int, target.split(","))
            pyautogui.dragTo(x, y, duration=duration)
            return f"✅ 拖拽到坐标 ({x}, {y})"
        except ValueError:
            return f"❌ 坐标格式错误: {target}"
    
    async def _scroll_mouse(self, amount: str) -> str:
        """滚动鼠标"""
        try:
            scroll_amount = int(amount) if amount else 100
            pyautogui.scroll(scroll_amount)
            return f"✅ 滚动了 {scroll_amount} 单位"
        except ValueError:
            return f"❌ 滚动量必须是数字: {amount}"
    
    async def _press_hotkey(self, keys: str) -> str:
        """按下快捷键"""
        if not keys:
            return "❌ 未提供快捷键"
        
        key_list = keys.split("+")
        pyautogui.hotkey(*key_list)
        return f"✅ 按下了快捷键: {keys}"
    
    async def _record_macro(self, filename: str) -> str:
        """录制宏（简化版）"""
        return "⚠️ 录制功能需要更复杂的实现，目前仅返回提示"
    
    async def _playback_macro(self, filename: str) -> str:
        """回放宏（简化版）"""
        return "⚠️ 回放功能需要更复杂的实现，目前仅返回提示"