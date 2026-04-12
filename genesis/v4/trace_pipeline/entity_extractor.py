"""
Trace Entity Extractor — 从 spans 表确定性提取结构化实体

零 LLM。每个实体带置信度和溯源链（span_id → trace_id → 原始工具调用）。

提取方式与置信度:
  精确提取 (confidence=1.0): 文件路径、退出码、URL
  模式匹配 (confidence=0.8-0.9): 服务名、包名、错误分类
  共现推断 (confidence=0.5-0.7): 由上层 Relationship Builder 处理，不在此模块
"""

import re
import json
import sqlite3
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Set
from pathlib import Path

logger = logging.getLogger(__name__)

_TRACES_DB = Path(__file__).resolve().parent.parent.parent.parent / "runtime" / "traces.db"

# ── Path Normalization ────────────────────────────────────────────────────
# 同一文件会以不同形式出现：绝对路径、容器路径、相对路径
# 归一化到项目相对路径，消除重复实体

_STRIP_PREFIXES = [
    "/home/chendechusn/Genesis/Genesis/",
    "/workspace/genesis/",
    "/workspace/",
    "/root/project/",
]


def _normalize_file_path(path: str) -> str:
    """将文件路径归一化为项目相对路径"""
    normalized = path.strip()
    for prefix in _STRIP_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    # 去掉开头的 / （如果剩余路径仍是绝对路径且不在已知系统目录下）
    # 保留系统路径如 /etc/... /usr/... /var/...
    if normalized.startswith("/") and not any(
        normalized.startswith(p) for p in
        ["/etc/", "/usr/", "/var/", "/home/", "/tmp/", "/root/", "/sys/", "/proc/"]
    ):
        normalized = normalized.lstrip("/")
    return normalized


# ── Entity Types ──────────────────────────────────────────────────────────

class EntityType:
    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    COMMAND = "COMMAND"
    SERVICE = "SERVICE"
    ERROR = "ERROR"
    EXIT_CODE = "EXIT_CODE"
    URL = "URL"
    PACKAGE = "PACKAGE"


@dataclass
class TraceEntity:
    """管线提取的原子实体"""
    entity_type: str               # EntityType.*
    value: str                     # 规范化后的值
    confidence: float              # 0.0-1.0，由提取方式决定
    source_span_id: str            # 溯源：哪个 span 产出的
    source_trace_id: str           # 溯源：哪个 session
    source_tool: str               # 工具名
    extraction_rule: str           # 哪条规则提取的（可测试性）
    raw_fragment: str = ""         # 原始文本片段（调试用，可截断）

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpanRecord:
    """从 traces.db 读取的 span 记录"""
    span_id: str
    trace_id: str
    tool_name: str
    tool_args_preview: str
    tool_result_preview: str
    status: str
    started_at: float
    duration_ms: float


# ── Extraction Rules ──────────────────────────────────────────────────────
# 每条规则是一个函数：(span) -> List[TraceEntity]
# 规则可测试、可独立增删、可回归验证

# 文件路径模式（Unix 绝对路径 + 常见扩展）
_FILE_PATH_RE = re.compile(
    r'(/(?:[\w.\-]+/)*[\w.\-]+\.(?:py|js|ts|json|yaml|yml|toml|md|txt|conf|cfg|sh|sql|css|html|log|ini|service|env|sqlite|db|csv))\b'
)
# 目录路径（以 / 结尾或已知目录模式）
_DIR_PATH_RE = re.compile(
    r'(/(?:[\w.\-]+/)+)(?=[\s"\']|$)'
)
# URL 模式
_URL_RE = re.compile(
    r'(https?://[^\s"\'<>\]]+)'
)
# 退出码模式（中文格式 from Genesis shell tool）
_EXIT_CODE_RE = re.compile(
    r'退出码:\s*(\d+)'
)
# 服务名模式（systemctl / docker / 常见守护进程）
_SERVICE_PATTERNS = {
    re.compile(r'systemctl\s+\w+\s+([\w\-@.]+)'): "systemctl",
    re.compile(r'docker\s+(?:start|stop|restart|logs|exec|run|ps|inspect)\s+([\w][\w\-.]+)'): "docker",
    re.compile(r'service\s+([\w\-]+)\s+'): "service",
}
# 常见服务名的直接匹配
_KNOWN_SERVICES = frozenset([
    "v2ray", "v2raya", "nginx", "apache2", "httpd", "mysql", "mariadb",
    "postgresql", "postgres", "redis", "mongodb", "docker", "dockerd",
    "sshd", "ssh", "cron", "systemd", "journald", "ufw", "iptables",
    "nodejs", "pm2", "supervisor", "caddy", "traefik", "haproxy",
])
# 预编译词边界正则（避免 'node' 匹配 'node_id'，'genesis' 匹配文件路径）
_KNOWN_SERVICE_RE = {svc: re.compile(r'\b' + re.escape(svc) + r'\b') for svc in _KNOWN_SERVICES}
# pip/apt/npm 包名提取
_PACKAGE_PATTERNS = {
    re.compile(r'pip3?\s+install\s+([^\s;|&]+(?:\s+[^\s;|&-][^\s;|&]+)*)'): "pip",
    re.compile(r'apt(?:-get)?\s+install\s+(?:-y\s+)?([^\s;|&]+(?:\s+[^\s;|&-][^\s;|&]+)*)'): "apt",
    re.compile(r'npm\s+install\s+(?:--save(?:-dev)?\s+)?([^\s;|&]+)'): "npm",
}
# 错误模式
_ERROR_PATTERNS = [
    (re.compile(r'((?:Error|Exception|Traceback|FATAL|CRITICAL)[:\s].{10,120})'), "error_message"),
    (re.compile(r'(No such file or directory[:\s].{0,80})'), "file_not_found"),
    (re.compile(r'(Permission denied[:\s].{0,80})'), "permission_denied"),
    (re.compile(r'(Connection refused[:\s].{0,80})'), "connection_refused"),
    (re.compile(r'(command not found[:\s].{0,40})'), "command_not_found"),
    (re.compile(r'(Module\w*Error[:\s].{0,80})'), "module_error"),
    (re.compile(r'(ImportError[:\s].{0,80})'), "import_error"),
    (re.compile(r'(SyntaxError[:\s].{0,80})'), "syntax_error"),
    (re.compile(r'(TimeoutError[:\s].{0,80})'), "timeout_error"),
]


def _parse_args(args_preview: str) -> Dict[str, Any]:
    """安全解析 tool_args_preview JSON"""
    if not args_preview:
        return {}
    try:
        return json.loads(args_preview)
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_from_shell(span: SpanRecord) -> List[TraceEntity]:
    """从 shell 工具调用中提取实体"""
    entities = []
    args = _parse_args(span.tool_args_preview)
    command = args.get("command", "")
    result = span.tool_result_preview or ""

    if not command:
        return entities

    # COMMAND 实体
    # 截取命令核心部分（去掉 sudo, cd, bash -c 等包装）
    cmd_core = command
    for prefix in ["sudo ", "bash -c ", "sh -c "]:
        if cmd_core.startswith(prefix):
            cmd_core = cmd_core[len(prefix):]
    cmd_core = cmd_core.strip().strip('"').strip("'")
    entities.append(TraceEntity(
        entity_type=EntityType.COMMAND,
        value=cmd_core[:200],
        confidence=1.0,
        source_span_id=span.span_id,
        source_trace_id=span.trace_id,
        source_tool="shell",
        extraction_rule="shell_command_direct",
        raw_fragment=command[:200],
    ))

    # FILE 实体（从命令和结果中提取）
    for text, conf, rule in [(command, 1.0, "shell_cmd_file"), (result, 0.9, "shell_result_file")]:
        for m in _FILE_PATH_RE.finditer(text):
            entities.append(TraceEntity(
                entity_type=EntityType.FILE,
                value=_normalize_file_path(m.group(1)),
                confidence=conf,
                source_span_id=span.span_id,
                source_trace_id=span.trace_id,
                source_tool="shell",
                extraction_rule=rule,
                raw_fragment=m.group(0)[:100],
            ))

    # EXIT_CODE 实体
    ec_match = _EXIT_CODE_RE.search(result)
    if ec_match:
        entities.append(TraceEntity(
            entity_type=EntityType.EXIT_CODE,
            value=ec_match.group(1),
            confidence=1.0,
            source_span_id=span.span_id,
            source_trace_id=span.trace_id,
            source_tool="shell",
            extraction_rule="shell_exit_code",
            raw_fragment=ec_match.group(0),
        ))

    # SERVICE 实体（从命令中提取）
    combined = command.lower()
    for svc, pat in _KNOWN_SERVICE_RE.items():
        if pat.search(combined):
            entities.append(TraceEntity(
                entity_type=EntityType.SERVICE,
                value=svc,
                confidence=0.85,
                source_span_id=span.span_id,
                source_trace_id=span.trace_id,
                source_tool="shell",
                extraction_rule="shell_known_service",
                raw_fragment=svc,
            ))
    for pat, rule_name in _SERVICE_PATTERNS.items():
        m = pat.search(command)
        if m:
            svc_name = m.group(1).strip()
            if svc_name and len(svc_name) > 1:
                entities.append(TraceEntity(
                    entity_type=EntityType.SERVICE,
                    value=svc_name.lower(),
                    confidence=0.9,
                    source_span_id=span.span_id,
                    source_trace_id=span.trace_id,
                    source_tool="shell",
                    extraction_rule=f"shell_service_{rule_name}",
                    raw_fragment=m.group(0)[:100],
                ))

    # PACKAGE 实体
    for pat, pkg_manager in _PACKAGE_PATTERNS.items():
        m = pat.search(command)
        if m:
            raw_pkgs = m.group(1).strip()
            for pkg in raw_pkgs.split():
                pkg = pkg.strip().strip("'\"`,;)")
                if (pkg and not pkg.startswith("-") and not pkg.startswith(">")
                        and not pkg.startswith("<") and not pkg.startswith("/")
                        and len(pkg) > 1 and pkg[0].isalpha()):
                    entities.append(TraceEntity(
                        entity_type=EntityType.PACKAGE,
                        value=pkg,
                        confidence=0.95,
                        source_span_id=span.span_id,
                        source_trace_id=span.trace_id,
                        source_tool="shell",
                        extraction_rule=f"shell_package_{pkg_manager}",
                        raw_fragment=m.group(0)[:100],
                    ))

    # ERROR 实体（从结果中提取）
    for pat, error_kind in _ERROR_PATTERNS:
        m = pat.search(result)
        if m:
            entities.append(TraceEntity(
                entity_type=EntityType.ERROR,
                value=m.group(1).strip()[:200],
                confidence=0.85,
                source_span_id=span.span_id,
                source_trace_id=span.trace_id,
                source_tool="shell",
                extraction_rule=f"shell_error_{error_kind}",
                raw_fragment=m.group(0)[:100],
            ))

    return entities


def _extract_from_file_tool(span: SpanRecord) -> List[TraceEntity]:
    """从 read_file / write_file / append_file 中提取实体"""
    entities = []
    args = _parse_args(span.tool_args_preview)
    file_path = args.get("file_path", "")

    if file_path:
        entities.append(TraceEntity(
            entity_type=EntityType.FILE,
            value=_normalize_file_path(file_path),
            confidence=1.0,
            source_span_id=span.span_id,
            source_trace_id=span.trace_id,
            source_tool=span.tool_name,
            extraction_rule="file_tool_path_arg",
            raw_fragment=file_path,
        ))

    # write_file 结果中可能包含完整路径
    result = span.tool_result_preview or ""
    path_match = re.search(r'路径:\s*(\S+)', result)
    if path_match:
        full_path = path_match.group(1)
        norm_full = _normalize_file_path(full_path)
        if norm_full != _normalize_file_path(file_path):
            entities.append(TraceEntity(
                entity_type=EntityType.FILE,
                value=norm_full,
                confidence=1.0,
                source_span_id=span.span_id,
                source_trace_id=span.trace_id,
                source_tool=span.tool_name,
                extraction_rule="file_tool_result_path",
                raw_fragment=path_match.group(0)[:100],
            ))

    return entities


def _extract_from_list_directory(span: SpanRecord) -> List[TraceEntity]:
    """从 list_directory 中提取目录实体"""
    entities = []
    args = _parse_args(span.tool_args_preview)
    dir_path = args.get("path", "") or args.get("directory", "")

    if dir_path and dir_path.count('/') >= 3:
        entities.append(TraceEntity(
            entity_type=EntityType.DIRECTORY,
            value=dir_path.rstrip("/") + "/",
            confidence=1.0,
            source_span_id=span.span_id,
            source_trace_id=span.trace_id,
            source_tool="list_directory",
            extraction_rule="list_dir_path_arg",
            raw_fragment=dir_path,
        ))

    return entities


def _extract_from_web_search(span: SpanRecord) -> List[TraceEntity]:
    """从 web_search 中提取 URL 实体"""
    entities = []
    result = span.tool_result_preview or ""

    for m in _URL_RE.finditer(result):
        entities.append(TraceEntity(
            entity_type=EntityType.URL,
            value=m.group(1).rstrip(".)],"),
            confidence=0.95,
            source_span_id=span.span_id,
            source_trace_id=span.trace_id,
            source_tool="web_search",
            extraction_rule="web_search_url",
            raw_fragment=m.group(0)[:200],
        ))

    return entities


# ── 工具 → 提取器路由 ──────────────────────────────────────────────────

_TOOL_EXTRACTORS = {
    "shell": _extract_from_shell,
    "read_file": _extract_from_file_tool,
    "write_file": _extract_from_file_tool,
    "append_file": _extract_from_file_tool,
    "list_directory": _extract_from_list_directory,
    "web_search": _extract_from_web_search,
}


# ── Public API ────────────────────────────────────────────────────────────

class TraceEntityExtractor:
    """从 traces.db 批量提取结构化实体"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _TRACES_DB

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def extract_from_trace(self, trace_id: str) -> List[TraceEntity]:
        """从单个 trace（session）提取所有实体"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT span_id, trace_id, tool_name, tool_args_preview, "
                "tool_result_preview, status, started_at, duration_ms "
                "FROM spans WHERE trace_id = ? AND span_type = 'tool_call' "
                "ORDER BY started_at",
                (trace_id,)
            ).fetchall()
            return self._extract_from_rows(rows)
        finally:
            conn.close()

    def extract_recent(self, limit: int = 100) -> List[TraceEntity]:
        """从最近 N 个 trace 中提取实体"""
        conn = self._get_conn()
        try:
            trace_ids = conn.execute(
                "SELECT trace_id FROM traces ORDER BY started_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            all_entities = []
            for row in trace_ids:
                all_entities.extend(self.extract_from_trace(row["trace_id"]))
            return all_entities
        finally:
            conn.close()

    def extract_from_rows(self, rows: list) -> List[TraceEntity]:
        """公开的行级提取入口（便于测试）"""
        return self._extract_from_rows(rows)

    def _extract_from_rows(self, rows: list) -> List[TraceEntity]:
        all_entities = []
        for row in rows:
            span = SpanRecord(
                span_id=row["span_id"],
                trace_id=row["trace_id"],
                tool_name=row["tool_name"] or "",
                tool_args_preview=row["tool_args_preview"] or "",
                tool_result_preview=row["tool_result_preview"] or "",
                status=row["status"] or "",
                started_at=row["started_at"] or 0,
                duration_ms=row["duration_ms"] or 0,
            )
            extractor = _TOOL_EXTRACTORS.get(span.tool_name)
            if extractor:
                try:
                    entities = extractor(span)
                    all_entities.extend(entities)
                except Exception as e:
                    logger.warning(f"Entity extraction failed for span {span.span_id}: {e}")
        return all_entities

    def summary(self, entities: List[TraceEntity]) -> Dict[str, Any]:
        """实体统计摘要"""
        by_type: Dict[str, int] = {}
        by_rule: Dict[str, int] = {}
        avg_confidence = 0.0
        for e in entities:
            by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
            by_rule[e.extraction_rule] = by_rule.get(e.extraction_rule, 0) + 1
            avg_confidence += e.confidence
        if entities:
            avg_confidence /= len(entities)
        return {
            "total": len(entities),
            "by_type": dict(sorted(by_type.items(), key=lambda x: -x[1])),
            "by_rule": dict(sorted(by_rule.items(), key=lambda x: -x[1])[:10]),
            "avg_confidence": round(avg_confidence, 3),
            "unique_values": len({(e.entity_type, e.value) for e in entities}),
        }
