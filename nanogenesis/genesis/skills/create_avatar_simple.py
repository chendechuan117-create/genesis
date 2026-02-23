import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class CreateAvatarSimpleTool(Tool):
    @property
    def name(self) -> str:
        return "create_avatar_simple"
        
    @property
    def description(self) -> str:
        return "使用纯Python和SVG格式创建简单头像，无需PIL库依赖"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string", 
                    "description": "输出文件的完整路径，例如：/home/user/Desktop/avatar.svg"
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
        import os
        
        try:
            # 创建SVG内容
            svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
  <!-- 蓝色背景 -->
  <rect width="{size}" height="{size}" fill="#4A90E2"/>
  
  <!-- 白色圆形 -->
  <circle cx="{size//2}" cy="{size//2}" r="{size//2 - 10}" 
          fill="#FFFFFF" stroke="#333333" stroke-width="3"/>
  
  <!-- 字母A -->
  <text x="{size//2}" y="{size//2}" 
        font-family="Arial, sans-serif" 
        font-size="{size//2}" 
        font-weight="bold" 
        fill="#333333" 
        text-anchor="middle" 
        dominant-baseline="middle">A</text>
</svg>'''
            
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 保存SVG文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            
            # 获取文件信息
            file_size = os.path.getsize(output_path)
            
            return f"SVG头像已成功生成并保存到: {output_path}\n尺寸: {size}x{size} 像素\n文件大小: {file_size} 字节\n格式: SVG (可缩放矢量图形)"
            
        except Exception as e:
            return f"生成SVG头像时出错: {str(e)}"