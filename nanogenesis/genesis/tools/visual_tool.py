
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
                    "enum": ["capture_screenshot"],
                    "description": "Action to perform"
                },
                "target": {
                    "type": "string",
                    "enum": ["adb", "desktop"],
                    "description": "Target device to capture from. Default: 'adb' if available, else 'desktop'.",
                    "default": "adb"
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, target: str = "adb", **kwargs) -> Any:
        """Execute visual commands"""
        if action == "capture_screenshot":
            return self._capture_screenshot(target)
        else:
            return f"Unknown action: {action}"

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
                # Try scrot then gnome-screenshot
                if self._is_command_available("scrot"):
                    cmd = f"scrot {filepath}"
                    subprocess.check_call(cmd.split())
                elif self._is_command_available("gnome-screenshot"):
                    cmd = f"gnome-screenshot -f {filepath}"
                    subprocess.check_call(cmd.split())
                else:
                    return "Error: No screenshot tool found (scrot/gnome-screenshot missing)."
            
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
