import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

import PyPDF2
import pdfplumber
import os
from typing import Optional

class PDFParserTool:
    name = "pdf_parser"
    description = "解析PDF文件并提取文本内容"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "PDF文件路径"
            },
            "method": {
                "type": "string",
                "description": "解析方法：'pdfplumber'（默认，更好处理复杂布局）或 'pypdf2'",
                "default": "pdfplumber"
            }
        },
        "required": ["file_path"]
    }

    def execute(self, file_path: str, method: str = "pdfplumber") -> str:
        """解析PDF文件并返回文本内容"""
        
        if not os.path.exists(file_path):
            return f"错误：文件不存在 - {file_path}"
        
        if not file_path.lower().endswith('.pdf'):
            return f"错误：文件不是PDF格式 - {file_path}"
        
        try:
            if method == "pdfplumber":
                return self._parse_with_pdfplumber(file_path)
            elif method == "pypdf2":
                return self._parse_with_pypdf2(file_path)
            else:
                return f"错误：不支持的解析方法 '{method}'，请使用 'pdfplumber' 或 'pypdf2'"
        except Exception as e:
            return f"解析PDF时出错：{str(e)}\n\n这可能是因为：\n1. PDF文件已加密或受保护\n2. PDF是扫描件（图像格式）需要OCR\n3. PDF文件损坏\n\n建议：\n- 尝试使用其他PDF阅读器打开文件\n- 如果是扫描件，需要OCR工具处理"

    def _parse_with_pdfplumber(self, file_path: str) -> str:
        """使用pdfplumber解析PDF（更好的布局处理）"""
        try:
            import pdfplumber
        except ImportError:
            return "错误：pdfplumber库未安装。请先安装：pip install pdfplumber"
        
        text_content = []
        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                text_content.append(f"PDF文件：{os.path.basename(file_path)}")
                text_content.append(f"总页数：{total_pages}")
                text_content.append("=" * 50)
                
                for i, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        text_content.append(f"\n第 {i} 页：")
                        text_content.append("-" * 30)
                        text_content.append(page_text.strip())
                    else:
                        text_content.append(f"\n第 {i} 页：无文本内容（可能是扫描件或图像）")
                        text_content.append("提示：此页可能需要OCR处理")
        
        except Exception as e:
            return f"使用pdfplumber解析失败：{str(e)}"
        
        return "\n".join(text_content)

    def _parse_with_pypdf2(self, file_path: str) -> str:
        """使用PyPDF2解析PDF"""
        try:
            import PyPDF2
        except ImportError:
            return "错误：PyPDF2库未安装。请先安装：pip install PyPDF2"
        
        text_content = []
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                text_content.append(f"PDF文件：{os.path.basename(file_path)}")
                text_content.append(f"总页数：{total_pages}")
                text_content.append("=" * 50)
                
                for i in range(total_pages):
                    page = pdf_reader.pages[i]
                    page_text = page.extract_text()
                    if page_text:
                        text_content.append(f"\n第 {i+1} 页：")
                        text_content.append("-" * 30)
                        text_content.append(page_text.strip())
                    else:
                        text_content.append(f"\n第 {i+1} 页：无文本内容（可能是扫描件或图像）")
                        text_content.append("提示：此页可能需要OCR处理")
        
        except Exception as e:
            return f"使用PyPDF2解析失败：{str(e)}"
        
        return "\n".join(text_content)