import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

import os
import subprocess
import tempfile

class PDFReaderTool:
    name = "pdf_reader"
    description = "读取PDF文件内容，支持多种解析方法"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "PDF文件路径"
            }
        },
        "required": ["file_path"]
    }

    def execute(self, file_path: str) -> str:
        """读取PDF文件内容"""
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return f"错误：文件不存在 - {file_path}"
        
        if not file_path.lower().endswith('.pdf'):
            return f"错误：文件不是PDF格式 - {file_path}"
        
        # 尝试多种方法解析PDF
        methods = [
            self._try_pdftotext,
            self._try_python_libs,
            self._try_qpdf
        ]
        
        for method in methods:
            result = method(file_path)
            if result and not result.startswith("错误："):
                return result
        
        return "无法解析PDF文件。可能原因：\n1. 文件已加密或受保护\n2. 文件是扫描件（图像）\n3. 文件损坏\n4. 系统中没有PDF解析工具"

    def _try_pdftotext(self, file_path: str) -> str:
        """使用pdftotext命令（poppler-utils）"""
        try:
            result = subprocess.run(
                ['pdftotext', file_path, '-'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # 获取页数信息
                page_info = subprocess.run(
                    ['pdfinfo', file_path],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                output = []
                if page_info.returncode == 0:
                    for line in page_info.stdout.split('\n'):
                        if 'Pages:' in line:
                            output.append(f"总页数：{line.split(':')[1].strip()}")
                            break
                
                output.append("提取的文本内容：")
                output.append("=" * 50)
                output.append(result.stdout.strip())
                return "\n".join(output)
            else:
                return f"错误：pdftotext解析失败 - {result.stderr}"
                
        except FileNotFoundError:
            return "错误：pdftotext命令未安装。请安装poppler-utils：sudo pacman -S poppler"
        except Exception as e:
            return f"错误：使用pdftotext时出错 - {str(e)}"

    def _try_python_libs(self, file_path: str) -> str:
        """尝试使用Python库解析"""
        try:
            import PyPDF2
            
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                total_pages = len(pdf_reader.pages)
                
                output = [f"总页数：{total_pages}", "提取的文本内容：", "=" * 50]
                
                for i, page in enumerate(pdf_reader.pages, 1):
                    text = page.extract_text()
                    if text and text.strip():
                        output.append(f"\n第 {i} 页：")
                        output.append("-" * 30)
                        output.append(text.strip())
                
                if len(output) > 3:  # 有实际内容
                    return "\n".join(output)
                else:
                    return "错误：PyPDF2未能提取到文本（可能是扫描件）"
                    
        except ImportError:
            return "错误：PyPDF2未安装。请安装：pip install PyPDF2"
        except Exception as e:
            return f"错误：PyPDF2解析失败 - {str(e)}"

    def _try_qpdf(self, file_path: str) -> str:
        """使用qpdf检查PDF基本信息"""
        try:
            result = subprocess.run(
                ['qpdf', '--check', file_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return f"PDF文件基本信息：\n文件：{os.path.basename(file_path)}\n大小：{os.path.getsize(file_path)} 字节\nqpdf检查：通过\n\n注意：此PDF可能是扫描件或加密文件，需要特殊工具处理。"
            else:
                return f"PDF文件检查失败：\n{result.stderr}"
                
        except FileNotFoundError:
            return "错误：qpdf命令未安装"
        except Exception as e:
            return f"错误：qpdf检查失败 - {str(e)}"