"""
ErrorCompressor — Genesis 错误信号压缩器
=============================================
将工具执行产生的原始错误日志压缩为结构化 JSON，
降低 LLM 的认知负荷，同时保留原始尾部供回溯。

支持的错误源（error_source）：
  - "python"    : Python traceback / ModuleNotFoundError 等
  - "pacman"    : Arch Linux 包管理器报错
  - "systemd"   : journalctl / systemctl 输出
  - "shell"     : 通用 shell 命令错误（默认）

使用示例：
  ec = ErrorCompressor()
  result = ec.compress(raw_error_str, source="python")
  # result = {
  #   "component": "python", "error_type": "ModuleNotFoundError",
  #   "core_message": "No module named 'PIL'",
  #   "suggestion": "Consider: pip install Pillow",
  #   "raw_tail": "...last N lines..."
  # }
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# 规则库：每种错误源对应的提取规则
# --------------------------------------------------------------------------

_PYTHON_EXCEPTION_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Warning|Interrupt|Fault|Exit|Stop))"
    r"(?::(.*))?$",
    re.MULTILINE,
)
_PYTHON_FILE_RE = re.compile(r'File "(.+?)", line (\d+)')
_TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,\d]*\b")
_PID_RE = re.compile(r"\[\s*\d+\.\d+\]|\bpid\s*=?\s*\d+\b", re.IGNORECASE)
_HEX_ADDR_RE = re.compile(r"\b0x[0-9a-fA-F]{4,}\b")

# pacman 常见错误模式
_PACMAN_ERROR_RE = re.compile(
    r"error:.*?(?:conflicting|failed|unable|cannot|not found|permission denied)[^\n]*",
    re.IGNORECASE,
)

# systemd 常见错误模式
_SYSTEMD_FAIL_RE = re.compile(
    r"(?:failed|Active: failed|can't open|error)[^\n]*",
    re.IGNORECASE,
)

# 常见错误类型 → 建议词典
_SUGGESTION_MAP: Dict[str, str] = {
    "ModuleNotFoundError": "Consider: pip install <module_name>",
    "ImportError":          "Check if the package is installed in the active venv",
    "PermissionError":      "Check file/directory permissions or run with appropriate privileges",
    "FileNotFoundError":    "Verify the file path exists before accessing it",
    "ConnectionError":      "Check network availability and endpoint configuration",
    "TimeoutError":         "The operation timed out; consider increasing timeout or checking connectivity",
    "KeyError":             "The key does not exist in the dict/mapping; verify the data structure",
    "TypeError":            "Type mismatch; check argument types passed to the function",
    "ValueError":           "Invalid value passed; validate inputs before calling the function",
}


class ErrorCompressor:
    """
    结构化错误压缩器。

    参数：
      tail_lines  : 保留原始 log 的最后 N 行（用于回溯）
      max_raw_len : raw_tail 字段的最大字符长度
    """

    def __init__(self, tail_lines: int = 12, max_raw_len: int = 800):
        self.tail_lines = tail_lines
        self.max_raw_len = max_raw_len

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compress(self, raw: str, source: str = "shell") -> Dict[str, Any]:
        """
        压缩原始错误文本。

        Args:
            raw    : 工具执行返回的原始字符串（可能含几十到几百行）
            source : 错误来源标识，用于选择解析规则

        Returns:
            结构化错误字典，保证包含以下 key:
              component, error_type, core_message, suggestion, raw_tail
        """
        if not raw or not raw.strip():
            return self._empty(source)

        cleaned = self._clean_noise(raw)
        tail = self._extract_tail(raw)

        source_lower = source.lower()
        if "python" in source_lower or "traceback" in raw:
            result = self._parse_python(cleaned, tail)
        elif "pacman" in source_lower:
            result = self._parse_pacman(cleaned, tail)
        elif "systemd" in source_lower or "journalctl" in source_lower:
            result = self._parse_systemd(cleaned, tail)
        else:
            result = self._parse_shell(cleaned, tail)

        result["component"] = source
        result.setdefault("suggestion", "")
        result["raw_tail"] = tail

        logger.debug(f"🗜️ ErrorCompressor: {source} → {result['error_type']}")
        return result

    def format_for_llm(self, compressed: Dict[str, Any]) -> str:
        """
        将压缩结果格式化为 LLM 易读的单段文字。
        保留 raw_tail 以便 LLM 如需可参考原始输出。
        """
        lines = [
            f"[ERROR REPORT] Component: {compressed.get('component', 'unknown')}",
            f"Type: {compressed.get('error_type', 'Unknown')}",
            f"Core: {compressed.get('core_message', '')}",
        ]
        if compressed.get("suggestion"):
            lines.append(f"Hint: {compressed['suggestion']}")
        if compressed.get("raw_tail"):
            lines.append(f"Raw (last lines):\n{compressed['raw_tail']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_python(self, cleaned: str, tail: str) -> Dict[str, Any]:
        error_type = "UnknownError"
        core_message = ""

        matches = list(_PYTHON_EXCEPTION_RE.finditer(cleaned))
        if matches:
            last = matches[-1]
            error_type = last.group(1)
            core_message = (last.group(2) or "").strip()

        # Faulting file
        file_matches = list(_PYTHON_FILE_RE.finditer(cleaned))
        faulting_file = file_matches[-1].group(1) if file_matches else ""

        suggestion = _SUGGESTION_MAP.get(error_type, "")

        return {
            "error_type": error_type,
            "core_message": core_message or tail.split("\n")[-1].strip(),
            "faulting_file": faulting_file,
            "suggestion": suggestion,
        }

    def _parse_pacman(self, cleaned: str, tail: str) -> Dict[str, Any]:
        errors = _PACMAN_ERROR_RE.findall(cleaned)
        core = errors[-1].strip() if errors else tail.split("\n")[-1].strip()
        return {
            "error_type": "PackageManagerError",
            "core_message": core,
            "suggestion": "Check pacman log: journalctl -u pacman or /var/log/pacman.log",
        }

    def _parse_systemd(self, cleaned: str, tail: str) -> Dict[str, Any]:
        errors = _SYSTEMD_FAIL_RE.findall(cleaned)
        core = errors[-1].strip() if errors else tail.split("\n")[-1].strip()
        return {
            "error_type": "SystemdError",
            "core_message": core,
            "suggestion": "Check: journalctl -xe for detailed logs",
        }

    def _parse_shell(self, cleaned: str, tail: str) -> Dict[str, Any]:
        # 取最后一行非空内容作为 core
        lines = [l.strip() for l in tail.split("\n") if l.strip()]
        core = lines[-1] if lines else cleaned[:200]
        error_type = "ShellError"
        if "permission denied" in core.lower():
            error_type = "PermissionError"
        elif "not found" in core.lower() or "no such file" in core.lower():
            error_type = "FileNotFoundError"
        elif "connection" in core.lower() or "network" in core.lower():
            error_type = "ConnectionError"

        return {
            "error_type": error_type,
            "core_message": core,
            "suggestion": _SUGGESTION_MAP.get(error_type, ""),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clean_noise(self, raw: str) -> str:
        """去除时间戳、PID、十六进制地址等无关噪声"""
        text = _TIMESTAMP_RE.sub("", raw)
        text = _PID_RE.sub("", text)
        text = _HEX_ADDR_RE.sub("<addr>", text)
        return text

    def _extract_tail(self, raw: str) -> str:
        """取原始 log 的最后 N 行，限制最大长度"""
        lines = raw.strip().splitlines()
        tail_lines = lines[-self.tail_lines:]
        tail = "\n".join(tail_lines)
        if len(tail) > self.max_raw_len:
            tail = tail[-self.max_raw_len:]
        return tail

    def _empty(self, source: str) -> Dict[str, Any]:
        return {
            "component": source,
            "error_type": "Empty",
            "core_message": "No error output received",
            "suggestion": "",
            "raw_tail": "",
        }
