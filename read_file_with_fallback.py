"""
read_file 包装函数：失败时自动降级到 list_directory 返回候选路径
"""
from pathlib import Path
import os
import re


def read_file_with_fallback(file_path: str, encoding: str = "utf-8", 
                             start_line: int = None, end_line: int = None,
                             search_pattern: str = None, context_lines: int = 3) -> dict:
    """
    包装 read_file：失败时自动降级到 list_directory 返回候选路径
    
    Returns:
        dict: {
            "success": bool,
            "content": str,
            "candidates": list,
            "error_type": str
        }
    """
    path = Path(os.path.expandvars(file_path)).expanduser().resolve()
    
    result = {
        "success": False,
        "content": "",
        "candidates": [],
        "error_type": None
    }
    
    # 尝试直接读取
    if path.exists() and path.is_file():
        try:
            content = path.read_text(encoding=encoding)
            lines = content.splitlines()
            total_lines = len(lines)
            
            if start_line is not None or end_line is not None:
                start = (start_line or 1) - 1
                end = (end_line or total_lines)
                lines = lines[start:end]
                content = "\n".join(lines)
            
            if search_pattern:
                try:
                    pattern = re.compile(search_pattern, re.IGNORECASE)
                except re.error:
                    pattern = re.compile(re.escape(search_pattern), re.IGNORECASE)
                
                matches = []
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        start_ctx = max(0, i - context_lines)
                        end_ctx = min(len(lines), i + context_lines + 1)
                        matches.extend(lines[start_ctx:end_ctx])
                
                content = "\n".join(matches) if matches else f"搜索 '{search_pattern}' 未找到匹配"
            
            result["success"] = True
            result["content"] = content
            return result
            
        except Exception as e:
            result["error_type"] = "read_error"
            result["content"] = f"Error: 读取失败 - {str(e)}"
            return result
    
    # 失败 → 降级到 list_directory
    if not path.exists():
        result["error_type"] = "file_not_found"
    elif not path.is_file():
        result["error_type"] = "not_a_file"
    
    parent = path.parent
    filename = path.name
    
    if parent.exists() and parent.is_dir():
        try:
            candidates = []
            for item in parent.iterdir():
                if item.is_file():
                    if filename.lower() in item.name.lower() or item.name.lower() in filename.lower():
                        candidates.append(str(item))
                    elif path.suffix and item.suffix == path.suffix:
                        candidates.append(str(item))
            
            result["candidates"] = candidates[:10]
            error_msg = f"Error: 文件不存在: {file_path}"
            
            if candidates:
                candidate_list = "\n  - " + "\n  - ".join(candidates)
                result["content"] = f"{error_msg}\n\n在 {parent} 发现可能的候选文件:{candidate_list}"
            else:
                dir_items = [f"{'📄' if i.is_file() else '📁'} {i.name}" for i in sorted(parent.iterdir())]
                result["content"] = f"{error_msg}\n\n{parent} 目录内容:\n  " + "\n  ".join(dir_items[:20])
                
        except Exception as e:
            result["content"] = f"{error_msg}\n\n无法列出父目录: {str(e)}"
    else:
        result["content"] = f"Error: 文件不存在: {file_path}\n父目录也不存在: {parent}"
    
    return result


if __name__ == "__main__":
    r = read_file_with_fallback("genesis/tools/nonexistent.py")
    print(f"Test: success={r['success']}, candidates={len(r['candidates'])}")
    print(r['content'][:300])
