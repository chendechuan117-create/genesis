import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class CreateAvatarTool(Tool):
    @property
    def name(self) -> str:
        return "create_avatar"
        
    @property
    def description(self) -> str:
        return "生成一个简单的圆形头像，包含字母'A'，并保存为PNG格式到指定路径。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string", 
                    "description": "输出文件的完整路径，例如：/home/user/Desktop/avatar.png"
                },
                "size": {
                    "type": "integer",
                    "description": "头像的尺寸（正方形，像素），默认256",
                    "default": 256
                }
            },
            "required": ["output_path"]
        }
        
    async def execute(self, output_path: str, size: int = 256) -> str:
        import subprocess
        import sys
        import os
        
        # 检查PIL/Pillow是否已安装
        try:
            from PIL import Image, ImageDraw, ImageFont
            PIL_AVAILABLE = True
        except ImportError:
            PIL_AVAILABLE = False
            
        if not PIL_AVAILABLE:
            # 尝试安装Pillow
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "--quiet"])
                from PIL import Image, ImageDraw, ImageFont
                PIL_AVAILABLE = True
            except Exception as e:
                return f"无法安装Pillow库: {str(e)}。请手动安装或使用其他方法。"
        
        try:
            # 创建新图像
            img = Image.new('RGB', (size, size), color='#4A90E2')  # 蓝色背景
            draw = ImageDraw.Draw(img)
            
            # 绘制圆形（作为头像形状）
            draw.ellipse([10, 10, size-10, size-10], fill='#FFFFFF', outline='#333333', width=3)
            
            # 尝试加载字体，如果失败则使用默认字体
            try:
                # 尝试使用系统字体
                font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", size//2)
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", size//2)
                except:
                    font = ImageFont.load_default()
            
            # 计算文本位置使其居中
            text = "A"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            position = ((size - text_width) // 2, (size - text_height) // 2)
            
            # 绘制字母"A"
            draw.text(position, text, fill='#333333', font=font)
            
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 保存图像
            img.save(output_path, 'PNG')
            
            # 获取文件信息
            file_size = os.path.getsize(output_path)
            
            return f"头像已成功生成并保存到: {output_path}\n尺寸: {size}x{size} 像素\n文件大小: {file_size} 字节"
            
        except Exception as e:
            return f"生成头像时出错: {str(e)}"