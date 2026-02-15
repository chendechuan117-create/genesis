"""
文件操作工具
"""

import sys
from pathlib import Path
from typing import Dict, Any

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base import Tool


class ReadFileTool(Tool):
    """读取文件工具"""
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return "读取文件内容。支持文本文件，返回文件内容。"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径（绝对路径或相对路径）"
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码，默认 utf-8",
                    "default": "utf-8"
                }
            },
            "required": ["file_path"]
        }
    
    async def execute(self, file_path: str, encoding: str = "utf-8") -> str:
        """执行文件读取"""
        try:
            path = Path(file_path).expanduser().resolve()
            
            if not path.exists():
                return f"Error: 文件不存在: {file_path}"
            
            if not path.is_file():
                return f"Error: 不是文件: {file_path}"
            
            # 读取文件
            content = path.read_text(encoding=encoding)
            
            # 返回结果
            return f"""文件: {path}
大小: {len(content)} 字符
编码: {encoding}

内容:
{content}"""
        
        except UnicodeDecodeError:
            logger.warning(f"文件可能是二进制文件: {file_path}")
            return f"Error: 无法使用 {encoding} 编码读取文件，可能是二进制文件"
        
        except Exception as e:
            logger.error(f"读取文件失败: {file_path}, error: {e}")
            return f"Error: 读取文件失败 - {str(e)}"


class WriteFileTool(Tool):
    """写入文件工具"""
    
    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "写入内容到文件。如果文件不存在会创建，如果存在会覆盖。"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径（绝对路径或相对路径）"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容"
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码，默认 utf-8",
                    "default": "utf-8"
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "是否自动创建父目录，默认 true",
                    "default": True
                }
            },
            "required": ["file_path", "content"]
        }
    
    async def execute(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True
    ) -> str:
        """执行文件写入"""
        try:
            path = Path(file_path).expanduser().resolve()
            
            # 创建父目录
            if create_dirs and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            path.write_text(content, encoding=encoding)
            
            return f"""✓ 文件写入成功
路径: {path}
大小: {len(content)} 字符
编码: {encoding}"""
        
        except Exception as e:
            return f"Error: 写入文件失败 - {str(e)}"


class AppendFileTool(Tool):
    """追加文件工具"""
    
    @property
    def name(self) -> str:
        return "append_file"
    
    @property
    def description(self) -> str:
        return "追加内容到文件末尾。如果文件不存在会创建。"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "content": {
                    "type": "string",
                    "description": "要追加的内容"
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码，默认 utf-8",
                    "default": "utf-8"
                }
            },
            "required": ["file_path", "content"]
        }
    
    async def execute(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8"
    ) -> str:
        """执行文件追加"""
        try:
            path = Path(file_path).expanduser().resolve()
            
            # 追加内容
            with path.open('a', encoding=encoding) as f:
                f.write(content)
            
            return f"""✓ 内容追加成功
路径: {path}
追加: {len(content)} 字符"""
        
        except Exception as e:
            logger.error(f"追加文件失败: {file_path}, error: {e}")
            return f"Error: 追加文件失败 - {str(e)}"


class ListDirectoryTool(Tool):
    """列出目录工具"""
    
    @property
    def name(self) -> str:
        return "list_directory"
    
    @property
    def description(self) -> str:
        return "列出目录中的文件和子目录"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "目录路径"
                },
                "pattern": {
                    "type": "string",
                    "description": "文件名模式（glob），如 '*.py'",
                    "default": "*"
                }
            },
            "required": ["directory"]
        }
    
    async def execute(self, directory: str, pattern: str = "*") -> str:
        """执行目录列出"""
        try:
            path = Path(directory).expanduser().resolve()
            
            if not path.exists():
                return f"Error: 目录不存在: {directory}"
            
            if not path.is_dir():
                return f"Error: 不是目录: {directory}"
            
            # 列出文件
            items = sorted(path.glob(pattern))
            
            if not items:
                return f"目录为空或没有匹配 '{pattern}' 的文件: {path}"
            
            # 格式化输出
            lines = [f"目录: {path}", f"匹配: {pattern}", f"共 {len(items)} 项\n"]
            
            for item in items:
                if item.is_file():
                    size = item.stat().st_size
                    lines.append(f"  📄 {item.name} ({size} bytes)")
                elif item.is_dir():
                    lines.append(f"  📁 {item.name}/")
                else:
                    lines.append(f"  ❓ {item.name}")
            
            return "\n".join(lines)
        
        except Exception as e:
            return f"Error: 列出目录失败 - {str(e)}"
