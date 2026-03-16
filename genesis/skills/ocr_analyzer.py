import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import pytesseract
from PIL import Image
import io
import base64
import os

class OcrAnalyzer(Tool):
    @property
    def name(self) -> str:
        return "ocr_analyzer"
        
    @property
    def description(self) -> str:
        return "使用OCR技术分析图片中的文本，特别用于识别n8n Web界面中的用户信息"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "图片文件路径"},
                "search_text": {"type": "string", "description": "要搜索的关键词，如'用户'、'登录'、'admin'等", "default": ""}
            },
            "required": ["image_path"]
        }
        
    async def execute(self, image_path: str, search_text: str = "") -> str:
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                return f"错误：图片文件不存在 - {image_path}"
            
            # 打开图片
            image = Image.open(image_path)
            
            # 使用pytesseract进行OCR识别
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            
            result = f"=== OCR分析结果 ===\n"
            result += f"图片路径: {image_path}\n"
            result += f"图片尺寸: {image.size}\n"
            result += f"识别到的文本:\n{text}\n"
            
            # 如果指定了搜索文本，进行筛选
            if search_text:
                lines = text.split('\n')
                matching_lines = [line for line in lines if search_text.lower() in line.lower()]
                if matching_lines:
                    result += f"\n=== 包含'{search_text}'的行 ===\n"
                    for line in matching_lines:
                        result += f"- {line}\n"
                else:
                    result += f"\n未找到包含'{search_text}'的文本\n"
            
            return result
            
        except Exception as e:
            return f"OCR分析失败: {str(e)}"