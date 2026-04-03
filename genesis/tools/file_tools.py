"""
文件操作工具
"""

from pathlib import Path
from typing import Dict, Any
import logging

from genesis.core.artifacts import record_managed_artifact, resolve_tool_path, should_hide_from_directory_listing, debris_warning, is_project_debris
from genesis.core.base import Tool

logger = logging.getLogger(__name__)


def _format_file_success(action_title: str, path: Path, size: int, encoding: str = "", artifact_id: str = "") -> str:
    lines = [action_title, f"路径: {path}"]
    if size >= 0:
        lines.append(f"大小: {size} 字符")
    if encoding:
        lines.append(f"编码: {encoding}")
    if artifact_id:
        lines.append(f"artifact_id: {artifact_id}")
        lines.append("managed_root: runtime/scratch")
    return "\n".join(lines)


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
            import os
            path = Path(os.path.expandvars(file_path)).expanduser().resolve()
            
            if not path.exists():
                return f"Error: 文件不存在: {file_path}"
            
            if not path.is_file():
                return f"Error: 不是文件: {file_path}"
            
            # 读取文件
            content = path.read_text(encoding=encoding)
            
            # 截断处理 (保留首尾各 4000 字符)
            limit = 8000
            if len(content) > limit:
                half = limit // 2
                content = content[:half] + f"\n...[File Truncated ({len(content) - limit} chars hidden)]...\n" + content[-half:]
            
            # 返回结果
            warn = debris_warning(path)
            return f"""{warn}文件: {path}
大小: {path.stat().st_size} 字符 (显示截断后)
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
        return "写入内容到文件。默认写入 runtime/scratch（受管临时区）。仅当修改正式源码时才传 use_scratch=false。"
    
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
                },
                "use_scratch": {
                    "type": "boolean",
                    "description": "是否将目标路径限制在 runtime/scratch 下并记录为受管临时产物。默认 true；仅修改正式源码时设为 false",
                    "default": True
                },
                "artifact_type": {
                    "type": "string",
                    "description": "use_scratch=true 时的产物类型，如 scratch、probe、patch_script、audit、backup",
                    "default": "scratch"
                },
                "artifact_label": {
                    "type": "string",
                    "description": "use_scratch=true 时的简短用途标签，便于后续清理和审计",
                    "default": ""
                }
            },
            "required": ["file_path", "content"]
        }
    
    async def execute(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
        use_scratch: bool = True,
        artifact_type: str = "scratch",
        artifact_label: str = ""
    ) -> str:
        """执行文件写入"""
        try:
            path = resolve_tool_path(file_path, use_scratch=use_scratch)
            
            # 创建父目录
            if create_dirs and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            path.write_text(content, encoding=encoding)
            artifact_id = ""
            if use_scratch:
                artifact_id = record_managed_artifact(
                    path,
                    tool_name=self.name,
                    action="write",
                    requested_path=file_path,
                    artifact_type=artifact_type,
                    artifact_label=artifact_label,
                )
            return _format_file_success("✓ 文件写入成功", path, len(content), encoding, artifact_id)
        
        except Exception as e:
            logger.error(f"写入文件失败: {file_path}, error: {e}")
            return f"Error: 写入文件失败 - {str(e)}"


class AppendFileTool(Tool):
    """追加文件工具"""
    
    @property
    def name(self) -> str:
        return "append_file"
    
    @property
    def description(self) -> str:
        return "追加内容到文件末尾。默认写入 runtime/scratch（受管临时区）。仅当修改正式源码时才传 use_scratch=false。"
    
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
                },
                "use_scratch": {
                    "type": "boolean",
                    "description": "是否将目标路径限制在 runtime/scratch 下并记录为受管临时产物。默认 true；仅修改正式源码时设为 false",
                    "default": True
                },
                "artifact_type": {
                    "type": "string",
                    "description": "use_scratch=true 时的产物类型，如 scratch、probe、patch_script、audit、backup",
                    "default": "scratch"
                },
                "artifact_label": {
                    "type": "string",
                    "description": "use_scratch=true 时的简短用途标签，便于后续清理和审计",
                    "default": ""
                }
            },
            "required": ["file_path", "content"]
        }
    
    async def execute(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        use_scratch: bool = True,
        artifact_type: str = "scratch",
        artifact_label: str = ""
    ) -> str:
        """执行文件追加"""
        try:
            path = resolve_tool_path(file_path, use_scratch=use_scratch)
            if use_scratch and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            
            # 追加内容
            with path.open('a', encoding=encoding) as f:
                f.write(content)
            artifact_id = ""
            if use_scratch:
                artifact_id = record_managed_artifact(
                    path,
                    tool_name=self.name,
                    action="append",
                    requested_path=file_path,
                    artifact_type=artifact_type,
                    artifact_label=artifact_label,
                )
            return _format_file_success("✓ 内容追加成功", path, len(content), artifact_id=artifact_id)
        
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
        return "列出目录中的文件和子目录。默认隐藏所有碎片区（runtime/scratch、tmp、doctor 等），除非显式要求显示。"
    
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
                },
                "include_debris": {
                    "type": "boolean",
                    "description": "是否显示碎片区（runtime/scratch、tmp、doctor 等）的内容，默认 false",
                    "default": False
                }
            },
            "required": ["directory"]
        }
    
    async def execute(self, directory: str, pattern: str = "*", include_debris: bool = False) -> str:
        """执行目录列出"""
        try:
            import os
            path = Path(os.path.expandvars(directory)).expanduser().resolve()
            
            if not path.exists():
                return f"Error: 目录不存在: {directory}"
            
            if not path.is_dir():
                return f"Error: 不是目录: {directory}"
            
            # 列出文件
            items = sorted(path.glob(pattern))
            if not include_debris:
                items = [item for item in items
                         if not should_hide_from_directory_listing(path, item)
                         and not is_project_debris(item)]
            
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
