import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class ScreenVisualTester(Tool):
    @property
    def name(self) -> str:
        return "screen_visual_tester"
        
    @property
    def description(self) -> str:
        return "测试系统视觉能力：捕获屏幕截图并分析内容"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "test_type": {
                    "type": "string", 
                    "enum": ["capture", "analyze", "both"],
                    "description": "测试类型：capture(仅截图), analyze(仅分析), both(截图并分析)"
                },
                "save_path": {
                    "type": "string",
                    "description": "截图保存路径（可选）",
                    "default": "/tmp/screenshot_test.png"
                }
            },
            "required": ["test_type"]
        }
        
    async def execute(self, test_type: str, save_path: str = "/tmp/screenshot_test.png") -> str:
        import subprocess
        import os
        import json
        
        result = {
            "test_type": test_type,
            "success": False,
            "details": {}
        }
        
        try:
            # 检查图形环境
            display = os.environ.get('DISPLAY', '')
            xauth = os.environ.get('XAUTHORITY', '')
            
            result["details"]["environment"] = {
                "DISPLAY": display,
                "XAUTHORITY": xauth,
                "has_gui": bool(display)
            }
            
            if test_type in ["capture", "both"]:
                # 尝试使用scrot截图
                cmd = f"scrot -q 100 {save_path}"
                process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                result["details"]["capture"] = {
                    "command": cmd,
                    "returncode": process.returncode,
                    "stdout": process.stdout,
                    "stderr": process.stderr
                }
                
                # 检查文件是否创建
                if os.path.exists(save_path):
                    file_info = os.stat(save_path)
                    result["details"]["file_info"] = {
                        "path": save_path,
                        "size": file_info.st_size,
                        "exists": True
                    }
                    
                    # 尝试获取图片信息
                    try:
                        from PIL import Image
                        img = Image.open(save_path)
                        result["details"]["image_info"] = {
                            "format": img.format,
                            "size": img.size,
                            "mode": img.mode,
                            "width": img.width,
                            "height": img.height
                        }
                        img.close()
                        result["success"] = True
                    except ImportError:
                        result["details"]["image_info"] = {"error": "PIL not available"}
                        result["success"] = True
                else:
                    result["details"]["file_info"] = {"exists": False}
            
            if test_type in ["analyze", "both"] and result["success"]:
                # 简单的视觉分析（如果截图成功）
                try:
                    from PIL import Image
                    img = Image.open(save_path)
                    
                    # 基础分析
                    analysis = {
                        "resolution": f"{img.width}x{img.height}",
                        "aspect_ratio": round(img.width / img.height, 2),
                        "is_portrait": img.height > img.width,
                        "is_landscape": img.width > img.height,
                        "is_square": img.width == img.height
                    }
                    
                    # 颜色分析（简化版）
                    if img.mode == 'RGB':
                        # 获取中心像素颜色
                        center_x, center_y = img.width // 2, img.height // 2
                        center_color = img.getpixel((center_x, center_y))
                        analysis["center_color_rgb"] = center_color
                    
                    result["details"]["analysis"] = analysis
                    img.close()
                    
                except Exception as e:
                    result["details"]["analysis_error"] = str(e)
            
            return json.dumps(result, indent=2, ensure_ascii=False)
            
        except Exception as e:
            result["details"]["error"] = str(e)
            return json.dumps(result, indent=2, ensure_ascii=False)