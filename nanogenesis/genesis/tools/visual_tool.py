
import os
import subprocess
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Any

from genesis.core.base import Tool

logger = logging.getLogger(__name__)

class VisualTool(Tool):
    """
    视觉工具 (Visual Cortex)
    
    Capabilities:
    1. Capture Screenshot (ADB / Desktop)
    2. Return image path for VLM consumption
    """
    
    def __init__(self, workspace_root: str = None):
        self.workspace_root = Path(workspace_root) if workspace_root else Path.home() / "Genesis_Captures"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        
    @property
    def name(self) -> str:
        return "visual"
        
    @property
    def description(self) -> str:
        return "Captures visual capability (screenshots) for VLM analysis. Targets: 'adb' (Android) or 'desktop' (Linux Host)."
        
    @property
    def parameters(self) -> Dict[str, Any]:
        """Tool parameters Schema"""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["capture_screenshot", "analyze_image"],
                    "description": "Action to perform: 'capture_screenshot' to take a picture, 'analyze_image' to inspect an existing image file."
                },
                "target": {
                    "type": "string",
                    "description": "For 'capture_screenshot': 'adb' or 'desktop'. For 'analyze_image': absolute path to the image file."
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, target: str = None, **kwargs) -> Any:
        """Execute visual commands"""
        if action == "capture_screenshot":
            return self._capture_screenshot(target or "adb")
        elif action == "analyze_image":
            return self._analyze_image(target)
        else:
            return f"Unknown action: {action}"

    def _analyze_image(self, path: str) -> str:
        """Analyze an image file (Metadata + OCR fallback)"""
        if not path:
            return "Error: No image path provided for analysis."
        
        p = Path(path)
        if not p.exists():
            return f"Error: Image file not found at {path}"
            
        try:
            from PIL import Image
            img = Image.open(p)
            info = f"Image Info: Format={img.format}, Size={img.size}, Mode={img.mode}"
            
            # Try OCR if available
            ocr_text = ""
            try:
                import pytesseract
                # Simple check if tesseract is in path
                import shutil
                if shutil.which("tesseract"):
                    text = pytesseract.image_to_string(img).strip()
                    if text:
                        ocr_text = f"\n[OCR Detected Text]:\n{text[:1000]}"
                        if len(text) > 1000: ocr_text += "\n...(truncated)"
            except Exception:
                pass # OCR not available, skip
                
            return info + ocr_text + "\n(Note: This model cannot natively view pixels, but file properties are verified.)"
            
        except ImportError:
            return "Error: PIL (Pillow) library not installed. Cannot analyze image."
        except Exception as e:
            return f"Error analyzing image: {e}"

    def _capture_screenshot(self, target: str) -> Dict[str, Any]:
        """Capture screenshot and return Image Payload"""
        timestamp = int(time.time())
        filename = f"capture_{target}_{timestamp}_{str(uuid.uuid4())[:4]}.png"
        filepath = self.workspace_root / filename
        
        try:
            if target == "adb":
                # Check ADB connection first? optimize later.
                cmd = f"adb exec-out screencap -p > {filepath}"
                subprocess.check_call(cmd, shell=True)
                
            elif target == "desktop":
                # 关键修复：注入 XWayland 的 XAUTHORITY，否则 scrot 会触发 KDE 远程控制弹窗
                env = os.environ.copy()
                if "DISPLAY" not in env:
                    env["DISPLAY"] = ":1"
                
                # 自动检测 XWayland xauth 文件（KDE Wayland 会话下）
                if "XAUTHORITY" not in env:
                    import glob, os as _os
                    uid = _os.getuid()
                    xauth_files = glob.glob(f"/run/user/{uid}/xauth_*")
                    if xauth_files:
                        env["XAUTHORITY"] = xauth_files[0]
                        logger.info(f"🔑 自动注入 XAUTHORITY: {xauth_files[0]}")
                
                captured = False
                # 先尝试 mss（纯 Python，最干净）
                try:
                    import mss
                    import mss.tools
                    with mss.mss() as sct:
                        mon = sct.monitors[0]
                        shot = sct.grab(mon)
                        mss.tools.to_png(shot.rgb, shot.size, output=str(filepath))
                    captured = True
                    logger.info(f"📸 mss 截图成功")
                except Exception:
                    pass
                
                # fallback: scrot（注入 XAUTHORITY 后不会触发 KDE Portal 弹窗）
                if not captured and self._is_command_available("scrot"):
                    result = subprocess.run(
                        ["scrot", "-o", str(filepath)],
                        capture_output=True, timeout=10, env=env
                    )
                    if result.returncode == 0:
                        captured = True
                        logger.info(f"📸 scrot 截图成功")
                    else:
                        logger.warning(f"scrot 失败: {result.stderr.decode()[:100]}")
                
                if not captured:
                    return "Error: 截图失败。请检查 DISPLAY 和 XAUTHORITY 环境变量。"
            
            else:
                return f"Error: Unknown target {target}"
                
            # SUCCESS: Return Special Payload for AgentLoop
            logger.info(f"📸 Screenshot captured: {filepath}")
            return {
                "type": "image",
                "path": str(filepath),
                "description": f"Screenshot of {target} at {timestamp}"
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Screenshot failed: {e}")
            return f"Error capturing screenshot: {e}"
        except Exception as e:
            logger.error(f"Visual tool error: {e}")
            return f"Error: {e}"

    def _is_command_available(self, cmd: str) -> bool:
        from shutil import which
        return which(cmd) is not None
