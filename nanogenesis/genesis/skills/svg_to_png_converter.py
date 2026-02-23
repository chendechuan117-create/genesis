import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class SvgToPngConverter(Tool):
    @property
    def name(self) -> str:
        return "svg_to_png_converter"
        
    @property
    def description(self) -> str:
        return "将SVG格式图像转换为PNG格式，支持自定义尺寸和背景颜色"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "svg_path": {"type": "string", "description": "SVG源文件路径"},
                "png_path": {"type": "string", "description": "PNG输出文件路径"},
                "width": {"type": "integer", "description": "输出宽度（像素）", "default": 256},
                "height": {"type": "integer", "description": "输出高度（像素）", "default": 256},
                "background_color": {"type": "string", "description": "背景颜色（十六进制或名称）", "default": "white"}
            },
            "required": ["svg_path", "png_path"]
        }
        
    async def execute(self, svg_path: str, png_path: str, width: int = 256, height: int = 256, background_color: str = "white") -> str:
        import subprocess
        import os
        
        # 检查cairo是否可用（用于SVG转PNG）
        try:
            # 使用rsvg-convert（通常通过librsvg提供）
            cmd = [
                "rsvg-convert",
                "-w", str(width),
                "-h", str(height),
                "-b", background_color,
                "-o", png_path,
                svg_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # 验证文件是否创建成功
                if os.path.exists(png_path):
                    file_size = os.path.getsize(png_path)
                    return f"✅ 转换成功！PNG文件已保存到：{png_path}\n文件大小：{file_size} 字节\n尺寸：{width}x{height} 像素"
                else:
                    return f"❌ 文件创建失败：{png_path}"
            else:
                # 如果rsvg-convert不可用，尝试使用convert（ImageMagick）
                cmd = [
                    "convert",
                    "-background", background_color,
                    "-size", f"{width}x{height}",
                    svg_path,
                    png_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0 and os.path.exists(png_path):
                    file_size = os.path.getsize(png_path)
                    return f"✅ 使用ImageMagick转换成功！PNG文件已保存到：{png_path}\n文件大小：{file_size} 字节"
                else:
                    return f"❌ 转换失败：{result.stderr}\n\n建议：请安装librsvg或ImageMagick：\nsudo pacman -S librsvg imagemagick"
                    
        except FileNotFoundError as e:
            return f"❌ 转换工具未找到：{e}\n\n请安装必要的工具：\nsudo pacman -S librsvg imagemagick"
        except Exception as e:
            return f"❌ 转换过程中出现错误：{str(e)}"