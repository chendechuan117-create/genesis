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
        return (
            "读取文件内容。支持指定行范围（start_line/end_line）和文件内搜索（search_pattern）。\n"
            "• 读整个文件：read_file(file_path=...)\n"
            "• 读指定行：read_file(file_path=..., start_line=10, end_line=50)\n"
            "• 文件内搜索：read_file(file_path=..., search_pattern='def main')\n"
            "比 shell('cat file | head') 更高效，且返回带行号的结构化输出。"
        )
    
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
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（1-based）。可与 end_line 搭配读取特定范围"
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号（1-based，含）。不指定则读到文件末尾"
                },
                "search_pattern": {
                    "type": "string",
                    "description": "在文件内搜索的文本模式（支持正则）。返回匹配行及上下文"
                },
                "context_lines": {
                    "type": "integer",
                    "description": "搜索时每个匹配行的上下文行数，默认 3",
                    "default": 3
                }
            },
            "required": ["file_path"]
        }
    
    async def execute(self, file_path: str, encoding: str = "utf-8",
                      start_line: int = None, end_line: int = None,
                      search_pattern: str = None, context_lines: int = 3) -> str:
        """执行文件读取"""
        try:
            import os
            import re as _re
            path = Path(os.path.expandvars(file_path)).expanduser().resolve()
            
            if not path.exists():
                return f"Error: 文件不存在: {file_path}"
            
            if not path.is_file():
                return f"Error: 不是文件: {file_path}"
            
            content = path.read_text(encoding=encoding)
            lines = content.splitlines()
            total_lines = len(lines)
            warn = debris_warning(path)
            header = f"{warn}文件: {path}\n总行数: {total_lines} | 大小: {path.stat().st_size} bytes\n"

            # 模式 A: 文件内搜索
            if search_pattern:
                try:
                    pattern = _re.compile(search_pattern, _re.IGNORECASE)
                except _re.error:
                    pattern = _re.compile(_re.escape(search_pattern), _re.IGNORECASE)
                matches = []
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        matches.append(i)
                if not matches:
                    return f"{header}搜索: '{search_pattern}'\n结果: 未找到匹配"
                # 构建上下文片段
                output_parts = [f"{header}搜索: '{search_pattern}' | 匹配 {len(matches)} 处\n"]
                shown = set()
                for m_idx in matches[:50]:  # 最多展示 50 个匹配
                    ctx_start = max(0, m_idx - context_lines)
                    ctx_end = min(total_lines, m_idx + context_lines + 1)
                    for li in range(ctx_start, ctx_end):
                        if li not in shown:
                            marker = ">>>" if li == m_idx else "   "
                            output_parts.append(f"{marker} {li+1:>5}: {lines[li]}")
                            shown.add(li)
                    output_parts.append("")
                if len(matches) > 50:
                    output_parts.append(f"... 另有 {len(matches)-50} 处匹配未展示")
                return "\n".join(output_parts)

            # 模式 B: 行范围读取
            if start_line is not None or end_line is not None:
                s = max(1, start_line or 1) - 1
                e = min(total_lines, end_line or total_lines)
                selected = lines[s:e]
                numbered = [f"{i+s+1:>5}: {line}" for i, line in enumerate(selected)]
                body = "\n".join(numbered)
                return f"{header}行范围: {s+1}-{e}\n\n{body}"

            # 模式 C: 读取整个文件（原始逻辑，截断保护）
            limit = 8000
            if len(content) > limit:
                half = limit // 2
                content = content[:half] + f"\n...[File Truncated ({len(content) - limit} chars hidden)]...\n" + content[-half:]
            
            return f"{header}编码: {encoding}\n\n内容:\n{content}"
        
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


class GrepFilesTool(Tool):
    """跨文件文本搜索工具"""

    @property
    def name(self) -> str:
        return "grep_files"

    @property
    def description(self) -> str:
        return (
            "在目录下递归搜索文件内容（类似 grep -rn）。\n"
            "• 基本搜索：grep_files(directory='.', pattern='TODO')\n"
            "• 限定文件类型：grep_files(directory='.', pattern='import asyncio', file_glob='*.py')\n"
            "• 正则搜索：grep_files(directory='.', pattern='def \\w+_test')\n"
            "比 shell('grep -rn pattern dir') 更高效，自动过滤碎片和二进制文件。"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "搜索的根目录路径"
                },
                "pattern": {
                    "type": "string",
                    "description": "搜索文本或正则表达式"
                },
                "file_glob": {
                    "type": "string",
                    "description": "文件名过滤（glob），如 '*.py'、'*.json'。默认搜索所有文本文件",
                    "default": "*"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回匹配数，默认 50",
                    "default": 50
                },
                "context_lines": {
                    "type": "integer",
                    "description": "每个匹配行的上下文行数，默认 1",
                    "default": 1
                }
            },
            "required": ["directory", "pattern"]
        }

    async def execute(self, directory: str, pattern: str, file_glob: str = "*",
                      max_results: int = 50, context_lines: int = 1) -> str:
        """执行跨文件搜索"""
        try:
            import os
            import re as _re
            from fnmatch import fnmatch

            root = Path(os.path.expandvars(directory)).expanduser().resolve()
            if not root.exists():
                return f"Error: 目录不存在: {directory}"
            if not root.is_dir():
                return f"Error: 不是目录: {directory}"

            try:
                regex = _re.compile(pattern, _re.IGNORECASE)
            except _re.error:
                regex = _re.compile(_re.escape(pattern), _re.IGNORECASE)

            max_results = max(1, min(max_results, 200))
            context_lines = max(0, min(context_lines, 5))

            # 二进制文件后缀排除
            _BINARY_EXT = {'.pyc', '.pyo', '.so', '.o', '.a', '.dll', '.exe', '.bin',
                           '.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2',
                           '.ttf', '.eot', '.zip', '.gz', '.tar', '.bz2', '.7z',
                           '.db', '.sqlite', '.sqlite3', '.pkl', '.npy', '.npz'}

            results = []
            files_searched = 0
            files_matched = 0

            for dirpath, dirnames, filenames in os.walk(str(root)):
                # 跳过隐藏目录和常见噪声
                dirnames[:] = [d for d in dirnames
                               if not d.startswith('.')
                               and d not in ('__pycache__', 'node_modules', '.git', 'venv', '.venv')]
                dp = Path(dirpath)
                if is_project_debris(dp):
                    continue

                for fname in filenames:
                    if file_glob != "*" and not fnmatch(fname, file_glob):
                        continue
                    fpath = dp / fname
                    if fpath.suffix.lower() in _BINARY_EXT:
                        continue
                    if is_project_debris(fpath):
                        continue

                    try:
                        text = fpath.read_text(encoding='utf-8', errors='ignore')
                    except (PermissionError, OSError):
                        continue

                    file_lines = text.splitlines()
                    files_searched += 1
                    file_has_match = False

                    for i, line in enumerate(file_lines):
                        if regex.search(line):
                            if not file_has_match:
                                files_matched += 1
                                file_has_match = True
                            rel = fpath.relative_to(root) if fpath.is_relative_to(root) else fpath
                            ctx_start = max(0, i - context_lines)
                            ctx_end = min(len(file_lines), i + context_lines + 1)
                            ctx = []
                            for ci in range(ctx_start, ctx_end):
                                marker = ">>>" if ci == i else "   "
                                ctx.append(f"{marker} {ci+1:>5}: {file_lines[ci]}")
                            results.append(f"── {rel}:{i+1}\n" + "\n".join(ctx))

                            if len(results) >= max_results:
                                break
                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break

            header = (f"搜索: '{pattern}' in {root}\n"
                      f"文件过滤: {file_glob} | 搜索了 {files_searched} 文件\n"
                      f"匹配: {len(results)} 处 (在 {files_matched} 个文件中)\n")

            if not results:
                return f"{header}结果: 未找到匹配"

            body = "\n\n".join(results)
            truncation = ""
            if len(results) >= max_results:
                truncation = f"\n\n... 已达上限 {max_results}，可增大 max_results 或缩小搜索范围"
            return f"{header}\n{body}{truncation}"

        except Exception as e:
            return f"Error: 搜索失败 - {str(e)}"


class ListDirectoryTool(Tool):
    """列出目录工具"""
    
    @property
    def name(self) -> str:
        return "list_directory"
    
    @property
    def description(self) -> str:
        return (
            "列出目录中的文件和子目录。支持递归列出（max_depth）。\n"
            "默认隐藏碎片区（runtime/scratch、tmp、doctor 等）。\n"
            "• 单层：list_directory(directory=...)\n"
            "• 递归：list_directory(directory=..., max_depth=3)\n"
            "• 按模式过滤：list_directory(directory=..., pattern='*.py', max_depth=2)\n"
            "比 shell('find . -type f') 更高效，且自动过滤碎片。"
        )
    
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
                },
                "max_depth": {
                    "type": "integer",
                    "description": "递归深度。默认 1（仅当前层），设置更大值可递归列出子目录",
                    "default": 1
                }
            },
            "required": ["directory"]
        }
    
    async def execute(self, directory: str, pattern: str = "*", include_debris: bool = False, max_depth: int = 1) -> str:
        """执行目录列出"""
        try:
            import os
            path = Path(os.path.expandvars(directory)).expanduser().resolve()
            
            if not path.exists():
                return f"Error: 目录不存在: {directory}"
            
            if not path.is_dir():
                return f"Error: 不是目录: {directory}"

            max_depth = max(1, min(max_depth, 10))  # 防御性截断
            lines = [f"目录: {path}", f"模式: {pattern} | 深度: {max_depth}"]
            file_count = 0
            dir_count = 0
            MAX_ITEMS = 500  # 输出截断保护

            def _walk(p: Path, depth: int, prefix: str):
                nonlocal file_count, dir_count
                if depth > max_depth or file_count + dir_count >= MAX_ITEMS:
                    return
                try:
                    items = sorted(p.glob(pattern)) if depth == 1 else sorted(p.iterdir())
                except PermissionError:
                    lines.append(f"{prefix}⚠️ [permission denied]")
                    return
                if not include_debris:
                    items = [item for item in items
                             if not should_hide_from_directory_listing(p, item)
                             and not is_project_debris(item)]
                for item in items:
                    if file_count + dir_count >= MAX_ITEMS:
                        lines.append(f"{prefix}... (截断，已达 {MAX_ITEMS} 项)")
                        return
                    if item.is_file():
                        # 递归模式下深层文件也按 pattern 过滤
                        if depth > 1 and pattern != "*":
                            from fnmatch import fnmatch
                            if not fnmatch(item.name, pattern):
                                continue
                        size = item.stat().st_size
                        lines.append(f"{prefix}📄 {item.name} ({size} bytes)")
                        file_count += 1
                    elif item.is_dir():
                        sub_count = sum(1 for _ in item.iterdir()) if item.is_dir() else 0
                        lines.append(f"{prefix}📁 {item.name}/ ({sub_count} items)")
                        dir_count += 1
                        if depth < max_depth:
                            _walk(item, depth + 1, prefix + "  ")

            _walk(path, 1, "  ")
            lines.insert(2, f"共 {file_count} 文件, {dir_count} 目录\n")
            
            if file_count + dir_count == 0:
                return f"目录为空或没有匹配 '{pattern}' 的文件: {path}"
            
            return "\n".join(lines)
        
        except Exception as e:
            return f"Error: 列出目录失败 - {str(e)}"
