import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class VisualAnalyzer(Tool):
    @property
    def name(self) -> str:
        return "visual_analyzer"
        
    @property
    def description(self) -> str:
        return "分析图像文件的基本信息（不依赖PIL库），支持PNG格式"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "图像文件路径"}
            },
            "required": ["image_path"]
        }
        
    async def execute(self, image_path: str) -> str:
        import os
        import struct
        
        if not os.path.exists(image_path):
            return f"错误：文件不存在 - {image_path}"
            
        try:
            # 读取文件头分析PNG格式
            with open(image_path, 'rb') as f:
                # PNG文件头：89 50 4E 47 0D 0A 1A 0A
                header = f.read(8)
                if header != b'\x89PNG\r\n\x1a\n':
                    return f"错误：不是有效的PNG文件 - {image_path}"
                
                # 获取文件大小
                file_size = os.path.getsize(image_path)
                
                # 查找IHDR块获取分辨率
                f.seek(8)  # 跳过文件头
                while True:
                    chunk_data = f.read(8)
                    if len(chunk_data) < 8:
                        break
                        
                    chunk_length = struct.unpack('>I', chunk_data[:4])[0]
                    chunk_type = chunk_data[4:8]
                    
                    if chunk_type == b'IHDR':
                        # IHDR块包含：宽度(4字节) + 高度(4字节) + ...
                        ihdr_data = f.read(13)  # 读取IHDR数据
                        width = struct.unpack('>I', ihdr_data[:4])[0]
                        height = struct.unpack('>I', ihdr_data[4:8])[0]
                        
                        # 获取文件创建时间
                        mtime = os.path.getmtime(image_path)
                        
                        return f"""图像分析结果：
文件路径: {image_path}
文件大小: {file_size} 字节 ({file_size/1024:.1f} KB)
格式: PNG (已验证)
分辨率: {width} × {height} 像素
宽高比: {width/height:.2f}:1
创建时间: {mtime}
状态: 有效PNG图像文件"""
                    
                    # 跳过当前块的数据和CRC
                    f.seek(chunk_length + 4, 1)
                    
                return f"警告：找到PNG文件头但未找到IHDR块 - {image_path}"
                
        except Exception as e:
            return f"分析图像时出错: {str(e)}"