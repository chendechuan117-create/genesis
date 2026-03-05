"""
Genesis V2 - Workshop System
车间系统：厂长（Manager）的持久化类型化知识库

四个车间：
  tool_workshop        — 可调用工具/脚本
  known_info_workshop  — 已验证事实/环境信息
  metacognition_workshop — 解题模式/策略经验
  output_format_workshop — op 返回数据规范

[GENESIS_V2_SPEC.md 核心原则 #3 #4]
- 按需装配：厂长先拿元数据索引，再按 ID 加载 content
- 车间是持久化知识，每条记录含 last_verified 时间戳
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── 工具语义标签映射 ────────────────────────────────────────────────────────────
# survival = 默认出门物资，每个 OpSpec 自动携带；其余 tag 为概念分类供厂长决策
_TOOL_TAG_MAP: Dict[str, List[str]] = {
    "evomap_skill_search":  ["survival", "skill_discovery"],
    "skill_creator":        ["survival", "tool_creation"],
    "skill_creator_tool":   ["survival", "tool_creation"],
    "skill_importer":       ["survival", "tool_creation"],
    "spawn_sub_agent":      ["survival", "multi_agent"],
    "check_sub_agent":      ["survival", "multi_agent"],
    "send_to_sub_agent":    ["survival", "multi_agent"],
    "get_sub_agent_result": ["survival", "multi_agent"],
    "read_file":            ["file"],
    "write_file":           ["file"],
    "append_file":          ["file"],
    "list_directory":       ["file"],
    "shell":                ["shell"],
    "web_search":           ["web"],
    "browser":              ["web"],
    "github_commits":       ["web"],
    "douyin_analysis":      ["media"],
    "visual":               ["vision"],
    "scheduler":            ["scheduling"],
    "system_health":        ["system"],
}


# ─── Entry Models ──────────────────────────────────────────────────────────────

class ToolEntry(BaseModel):
    """工具车间条目 — 一个可调用工具/函数"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    tags: List[str] = Field(default_factory=list)
    summary: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    content: str = ""
    last_used: Optional[str] = None


class FactEntry(BaseModel):
    """已知信息车间条目 — 一个已验证的事实或环境信息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    key: str
    category: str = "general"
    value: str
    last_verified: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: str = "user"
    confidence: float = 1.0


class PatternEntry(BaseModel):
    """元认知车间条目 — 一个解题模式或策略经验"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    pattern_name: str
    context_tags: List[str] = Field(default_factory=list)
    approach: str
    usage_count: int = 0


class FormatEntry(BaseModel):
    """输出格式车间条目 — 一个 op 返回数据的结构化规范"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    format_name: str
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    example: str = ""


class CapabilityEntry(BaseModel):
    """能力校准车间条目 — 一个工具的执行统计（AI 原生执行校准观）"""
    capability: str                       # 工具名称，e.g. "shell", "read_file"
    total_calls: int = 0
    successes: int = 0
    reliability: float = 0.0
    common_failure: Optional[str] = None  # 最近一次失败摘要
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())


# ─── Lesson (op 执行经验反馈到车间) ─────────────────────────────────────────────

class WorkshopLesson(BaseModel):
    """
    op 执行完成后产生的学习记录。
    confidence >= 0.7 时自动写入车间；低于阈值进入待审队列。
    """
    lesson_type: Literal["new_fact", "correction", "new_pattern", "new_tool"]
    target_workshop: Literal["tool", "known_info", "metacognition", "output_format"]
    content: Dict[str, Any]
    confidence: float = 0.8


# ─── WorkshopManager ───────────────────────────────────────────────────────────

class WorkshopManager:
    """
    车间管理器 — Genesis V2 的持久化知识库核心。

    存储后端：SQLite（本地文件，零依赖）
    搜索策略：LIKE 模糊匹配（可无缝升级为 ChromaDB 向量检索）
    """

    CONFIDENCE_THRESHOLD = 0.7  # 低于此值的 lesson 进入待审队列

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".nanogenesis" / "workshops.sqlite"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"WorkshopManager ready: {self.db_path}")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tool_workshop (
                    id           TEXT PRIMARY KEY,
                    name         TEXT NOT NULL UNIQUE,
                    tags         TEXT NOT NULL DEFAULT '[]',
                    summary      TEXT NOT NULL DEFAULT '',
                    input_schema TEXT NOT NULL DEFAULT '{}',
                    content      TEXT NOT NULL DEFAULT '',
                    dimensions   TEXT NOT NULL DEFAULT '{}',
                    last_used    TEXT
                );

                CREATE TABLE IF NOT EXISTS known_info_workshop (
                    id            TEXT PRIMARY KEY,
                    key           TEXT NOT NULL UNIQUE,
                    category      TEXT NOT NULL DEFAULT 'general',
                    value         TEXT NOT NULL,
                    last_verified TEXT NOT NULL,
                    source        TEXT NOT NULL DEFAULT 'user',
                    confidence    REAL NOT NULL DEFAULT 1.0,
                    dimensions    TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS metacognition_workshop (
                    id           TEXT PRIMARY KEY,
                    pattern_name TEXT NOT NULL UNIQUE,
                    context_tags TEXT NOT NULL DEFAULT '[]',
                    approach     TEXT NOT NULL,
                    usage_count  INTEGER NOT NULL DEFAULT 0,
                    dimensions   TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS output_format_workshop (
                    id          TEXT PRIMARY KEY,
                    format_name TEXT NOT NULL UNIQUE,
                    schema      TEXT NOT NULL DEFAULT '{}',
                    example     TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS capability_workshop (
                    capability     TEXT PRIMARY KEY,
                    total_calls    INTEGER NOT NULL DEFAULT 0,
                    successes      INTEGER NOT NULL DEFAULT 0,
                    reliability    REAL NOT NULL DEFAULT 0.0,
                    common_failure TEXT,
                    last_updated   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_lessons (
                    id               TEXT PRIMARY KEY,
                    lesson_type      TEXT NOT NULL,
                    target_workshop  TEXT NOT NULL,
                    content          TEXT NOT NULL,
                    confidence       REAL NOT NULL,
                    created_at       TEXT NOT NULL
                );
            """)
            conn.commit()
        self._migrate_dimensions()
        self._seed_default_formats()
        self._cold_start_scan()

    # ─── Dimension Migration & Lookup ─────────────────────────────────────────

    # 从 category/tags 到 dimensions 的默认映射
    _CATEGORY_TO_DIMS: Dict[str, Dict[str, str]] = {
        "system":             {"scope": "local", "target": "config"},
        "system_info":        {"scope": "local", "target": "config"},
        "environment":        {"scope": "local", "target": "config"},
        "installed_software": {"scope": "local", "target": "software", "action": "install"},
        "installed_package":  {"scope": "local", "target": "software", "action": "install"},
        "user_profile":       {"scope": "user", "target": "data"},
        "user_info":          {"scope": "user", "target": "data"},
        "file_system":        {"scope": "local", "target": "file"},
        "software":           {"scope": "local", "target": "software"},
    }

    def _migrate_dimensions(self) -> None:
        """给已有表添加 dimensions 列（如果不存在），并从 category/tags 回填。"""
        with self._conn() as conn:
            # 添加列（忽略已存在错误）
            for table in ("known_info_workshop", "tool_workshop", "metacognition_workshop"):
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN dimensions TEXT NOT NULL DEFAULT '{{}}'")
                except Exception:
                    pass  # 列已存在

            # 回填 known_info 的 dimensions（从 category 映射）
            rows = conn.execute(
                "SELECT id, category FROM known_info_workshop WHERE dimensions = '{}'"
            ).fetchall()
            for r in rows:
                dims = self._CATEGORY_TO_DIMS.get(r["category"], {"scope": "general"})
                conn.execute(
                    "UPDATE known_info_workshop SET dimensions = ? WHERE id = ?",
                    (json.dumps(dims), r["id"])
                )

            # 回填 tool_workshop 的 dimensions（从 tags 映射）
            rows = conn.execute(
                "SELECT id, tags FROM tool_workshop WHERE dimensions = '{}'"
            ).fetchall()
            for r in rows:
                tags = json.loads(r["tags"] or "[]")
                dims = {}
                if "file" in tags: dims.update({"scope": "local", "target": "file"})
                elif "web" in tags: dims.update({"scope": "network", "target": "data"})
                elif "shell" in tags: dims.update({"scope": "local", "action": "execute"})
                elif "survival" in tags: dims.update({"scope": "meta", "target": "tool"})
                elif "media" in tags: dims.update({"scope": "local", "target": "media"})
                if dims:
                    conn.execute(
                        "UPDATE tool_workshop SET dimensions = ? WHERE id = ?",
                        (json.dumps(dims), r["id"])
                    )

            conn.commit()

    def get_by_dimensions(self, table: str, dims: Dict[str, str]) -> List[Dict[str, Any]]:
        """按维度匹配查找条目。dims 中的每个 key=value 都必须匹配。"""
        if not dims:
            return []

        # SQLite JSON 查询：用 LIKE 匹配每个维度键值对
        conditions = []
        params = []
        for k, v in dims.items():
            conditions.append("dimensions LIKE ?")
            params.append(f'%"{k}": "{v}"%')

        where = " AND ".join(conditions)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {where}", tuple(params)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_digest(self) -> str:
        """返回所有车间的摘要——厂长的'馆藏概念'，固定 ~20 行。"""
        with self._conn() as conn:
            # known_info: 按 category 聚合，每类取代表性 key
            fact_cats = conn.execute("""
                SELECT category, COUNT(*) as cnt,
                       GROUP_CONCAT(key, ', ') as keys
                FROM known_info_workshop
                GROUP BY category ORDER BY cnt DESC
            """).fetchall()

            # tools: 按 tags 聚合
            tool_count = conn.execute("SELECT COUNT(*) FROM tool_workshop").fetchone()[0]

            # patterns: 总数 + top 3 by usage
            pattern_count = conn.execute("SELECT COUNT(*) FROM metacognition_workshop").fetchone()[0]
            top_patterns = conn.execute(
                "SELECT pattern_name FROM metacognition_workshop ORDER BY usage_count DESC LIMIT 3"
            ).fetchall()

            # capability: top 3 most used
            top_cap = conn.execute(
                "SELECT capability, reliability, total_calls FROM capability_workshop ORDER BY total_calls DESC LIMIT 3"
            ).fetchall()

        lines = ["WORKSHOP DIGEST:"]

        # Facts digest
        lines.append(f"  known_info ({sum(r['cnt'] for r in fact_cats)} facts):")
        for r in fact_cats[:8]:  # 最多显示 8 个类别
            keys_preview = ", ".join(r["keys"].split(", ")[:3])
            lines.append(f"    {r['category']} ({r['cnt']}): {keys_preview}")

        # Tools digest
        lines.append(f"  tools: {tool_count} registered")

        # Patterns digest
        top_names = [r["pattern_name"] for r in top_patterns]
        lines.append(f"  patterns: {pattern_count} (top: {', '.join(top_names) if top_names else 'none'})")

        # Capability digest
        if top_cap:
            cap_str = ", ".join(f"{r['capability']}={r['reliability']:.0%}" for r in top_cap)
            lines.append(f"  capability: {cap_str}")

        return "\n".join(lines)

    # ─── Cold-Start Environment Scan ────────────────────────────────────────────

    def _cold_start_scan(self) -> None:
        """
        首次初始化时（known_info_workshop 为空）自动探测系统环境。
        使用 Python stdlib，100% 确定性，无 LLM 依赖。
        后续启动跳过（已有数据）。
        """
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM known_info_workshop").fetchone()[0]
        if count > 0:
            return

        import os
        import platform
        import shutil
        import sys

        def _which(cmd: str) -> str:
            p = shutil.which(cmd)
            return p if p else "not found"

        facts = [
            FactEntry(key="os_name",       category="environment", value=platform.system(),          source="cold_start"),
            FactEntry(key="os_version",    category="environment", value=platform.version(),         source="cold_start"),
            FactEntry(key="os_arch",       category="environment", value=platform.machine(),         source="cold_start"),
            FactEntry(key="hostname",      category="environment", value=platform.node(),            source="cold_start"),
            FactEntry(key="python_version",category="environment", value=sys.version.split()[0],     source="cold_start"),
            FactEntry(key="python_exec",   category="environment", value=sys.executable,             source="cold_start"),
            FactEntry(key="user_home",     category="environment", value=str(Path.home()),           source="cold_start"),
            FactEntry(key="current_user",  category="environment", value=os.getenv("USER", os.getenv("USERNAME", "unknown")), source="cold_start"),
            FactEntry(key="shell",         category="environment", value=os.getenv("SHELL", "unknown"), source="cold_start"),
            FactEntry(key="cpu_count",     category="environment", value=str(os.cpu_count()),        source="cold_start"),
            FactEntry(key="which_git",     category="tools",       value=_which("git"),              source="cold_start"),
            FactEntry(key="which_python3", category="tools",       value=_which("python3"),          source="cold_start"),
            FactEntry(key="which_docker",  category="tools",       value=_which("docker"),           source="cold_start"),
            FactEntry(key="which_node",    category="tools",       value=_which("node"),             source="cold_start"),
            FactEntry(key="which_curl",    category="tools",       value=_which("curl"),             source="cold_start"),
        ]

        for f in facts:
            self.add_fact(f)

        logger.info(f"✓ 冷启动扫描完成：写入 {len(facts)} 条环境事实到 known_info_workshop")
        self._seed_bootstrap_patterns()

    def _seed_bootstrap_patterns(self) -> None:
        """
        首次初始化时向 metacognition_workshop 写入最低限度的启动模式。
        这些模式是可覆盖的起点，不是硬编码规则。
        厂长通过执行反馈可以更新或替代它们。
        """
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM metacognition_workshop").fetchone()[0]
        if count > 0:
            return

        seeds = [
            PatternEntry(
                pattern_name="executor_exit_protocol",
                context_tags=["any_task", "execution"],
                approach=(
                    "After completing the task, call system_task_complete(summary=...) "
                    "to signal success. If stuck or unable to proceed, call "
                    "system_report_failure(reason=...). Never generate text output as the final result."
                ),
            ),
            PatternEntry(
                pattern_name="tool_selection_minimal",
                context_tags=["assembly", "tool_selection"],
                approach=(
                    "Select only the tools strictly necessary for the objective. "
                    "Prefer tools with higher reliability scores from the capability profile. "
                    "Avoid selecting tools speculatively."
                ),
            ),
        ]

        for p in seeds:
            self.add_pattern(p)

        logger.info(f"✓ 冷启动模式种子：写入 {len(seeds)} 条基础模式到 metacognition_workshop")

    # ─── Tool Workshop ──────────────────────────────────────────────────────────

    def add_tool(self, entry: ToolEntry) -> str:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tool_workshop
                   (id, name, tags, summary, input_schema, content, last_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, entry.name, json.dumps(entry.tags),
                 entry.summary, json.dumps(entry.input_schema),
                 entry.content, entry.last_used)
            )
            conn.commit()
        return entry.id

    def search_tools(self, query: str, limit: int = 5) -> List[ToolEntry]:
        q = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM tool_workshop
                   WHERE name LIKE ? OR summary LIKE ? OR tags LIKE ?
                   LIMIT ?""",
                (q, q, q, limit)
            ).fetchall()
        return [self._row_to_tool(r) for r in rows]

    def get_tool(self, tool_id: str) -> Optional[ToolEntry]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tool_workshop WHERE id = ? OR name = ?",
                (tool_id, tool_id)
            ).fetchone()
        return self._row_to_tool(row) if row else None

    def get_tool_index(self) -> List[Dict[str, Any]]:
        """轻量索引 — 只返回元数据，不含 content（厂长初次浏览用）"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, tags, summary FROM tool_workshop"
            ).fetchall()
        return [
            {"id": r["id"], "name": r["name"],
             "tags": json.loads(r["tags"]), "summary": r["summary"]}
            for r in rows
        ]

    def mark_tool_used(self, tool_name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE tool_workshop SET last_used = ? WHERE name = ?",
                (datetime.now().isoformat(), tool_name)
            )
            conn.commit()

    def _row_to_tool(self, row: sqlite3.Row) -> ToolEntry:
        return ToolEntry(
            id=row["id"], name=row["name"],
            tags=json.loads(row["tags"]),
            summary=row["summary"],
            input_schema=json.loads(row["input_schema"]),
            content=row["content"],
            last_used=row["last_used"]
        )

    # ─── Known Info Workshop ────────────────────────────────────────────────────

    def add_fact(self, entry: FactEntry) -> str:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO known_info_workshop
                   (id, key, category, value, last_verified, source, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, entry.key, entry.category, entry.value,
                 entry.last_verified, entry.source, entry.confidence)
            )
            conn.commit()
        return entry.id

    def search_facts(self, query: str, limit: int = 5) -> List[FactEntry]:
        q = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM known_info_workshop
                   WHERE key LIKE ? OR value LIKE ? OR category LIKE ?
                   ORDER BY confidence DESC LIMIT ?""",
                (q, q, q, limit)
            ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def get_facts_by_category(self, category: str) -> List[FactEntry]:
        """返回指定 category 的所有事实条目。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM known_info_workshop WHERE category = ?",
                (category,)
            ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def get_fact(self, key: str) -> Optional[FactEntry]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM known_info_workshop WHERE key = ? OR id = ?",
                (key, key)
            ).fetchone()
        return self._row_to_fact(row) if row else None

    def get_fact_index(self) -> List[Dict[str, Any]]:
        """轻量索引 — 含 value 预览，厂长据此判断是否选入 OpSpec"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, key, category, value, confidence FROM known_info_workshop"
            ).fetchall()
        return [
            {"id": r["id"], "key": r["key"], "category": r["category"],
             "value": str(r["value"])[:80], "confidence": r["confidence"]}
            for r in rows
        ]

    def _row_to_fact(self, row: sqlite3.Row) -> FactEntry:
        return FactEntry(
            id=row["id"], key=row["key"], category=row["category"],
            value=row["value"], last_verified=row["last_verified"],
            source=row["source"], confidence=row["confidence"]
        )

    # ─── Metacognition Workshop ─────────────────────────────────────────────────

    def add_pattern(self, entry: PatternEntry) -> str:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO metacognition_workshop
                   (id, pattern_name, context_tags, approach, usage_count)
                   VALUES (?, ?, ?, ?, ?)""",
                (entry.id, entry.pattern_name, json.dumps(entry.context_tags),
                 entry.approach, entry.usage_count)
            )
            conn.commit()
        return entry.id

    def search_patterns(self, query: str, limit: int = 3) -> List[PatternEntry]:
        q = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM metacognition_workshop
                   WHERE pattern_name LIKE ? OR context_tags LIKE ? OR approach LIKE ?
                   ORDER BY usage_count DESC LIMIT ?""",
                (q, q, q, limit)
            ).fetchall()
        return [self._row_to_pattern(r) for r in rows]

    def increment_pattern_usage(self, pattern_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE metacognition_workshop SET usage_count = usage_count + 1 WHERE id = ?",
                (pattern_id,)
            )
            conn.commit()

    def _row_to_pattern(self, row: sqlite3.Row) -> PatternEntry:
        return PatternEntry(
            id=row["id"], pattern_name=row["pattern_name"],
            context_tags=json.loads(row["context_tags"]),
            approach=row["approach"], usage_count=row["usage_count"]
        )

    # ─── Output Format Workshop ─────────────────────────────────────────────────

    def add_format(self, entry: FormatEntry) -> str:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO output_format_workshop
                   (id, format_name, schema, example)
                   VALUES (?, ?, ?, ?)""",
                (entry.id, entry.format_name,
                 json.dumps(entry.output_schema), entry.example)
            )
            conn.commit()
        return entry.id

    def get_format(self, format_name: str) -> Optional[FormatEntry]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM output_format_workshop WHERE format_name = ? OR id = ?",
                (format_name, format_name)
            ).fetchone()
        return self._row_to_format(row) if row else None

    def list_formats(self) -> List[Dict[str, Any]]:
        """列出所有格式规范的名称和 ID"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, format_name FROM output_format_workshop"
            ).fetchall()
        return [{"id": r["id"], "format_name": r["format_name"]} for r in rows]

    def _row_to_format(self, row: sqlite3.Row) -> FormatEntry:
        return FormatEntry(
            id=row["id"], format_name=row["format_name"],
            output_schema=json.loads(row["schema"]), example=row["example"]
        )

    def _seed_default_formats(self) -> None:
        """首次初始化时写入通用输出格式规范"""
        defaults = [
            FormatEntry(
                format_name="plain_text",
                output_schema={"result": "str"},
                example='{"result": "操作已完成"}'
            ),
            FormatEntry(
                format_name="file_operation",
                output_schema={"success": "bool", "path": "str", "detail": "str"},
                example='{"success": true, "path": "/home/user/file.txt", "detail": "写入 42 字节"}'
            ),
            FormatEntry(
                format_name="code_execution",
                output_schema={"success": "bool", "stdout": "str", "stderr": "str", "exit_code": "int"},
                example='{"success": true, "stdout": "Hello", "stderr": "", "exit_code": 0}'
            ),
            FormatEntry(
                format_name="search_result",
                output_schema={"found": "bool", "items": "list", "count": "int"},
                example='{"found": true, "items": ["a", "b"], "count": 2}'
            ),
        ]
        for fmt in defaults:
            if not self.get_format(fmt.format_name):
                self.add_format(fmt)

    # ─── Seed from ToolRegistry ─────────────────────────────────────────────────

    def seed_from_registry(self, registry: Any) -> int:
        """
        首次启动时从 ToolRegistry 自动填充工具车间。
        按 name 去重，已存在的工具不会重复写入；但会补填空 tags。
        """
        _INTERNAL_TOOL_PREFIXES = ("system_",)
        _INTERNAL_TOOL_NAMES = {
            # V2 system tools (执行管道内部信号，非用户任务工具)
            "system_task_complete", "system_report_failure",
            # V1 pure plumbing tools
            "save_memory", "search_memory", "chain_next", "context_switch",
            "protocol_emit", "trust_anchor", "capability_forge",
        }

        # 清理已入库的纯内部工具（历史遗留）
        with self._conn() as conn:
            placeholders = ",".join("?" * len(_INTERNAL_TOOL_NAMES))
            removed = conn.execute(
                f"DELETE FROM tool_workshop WHERE name IN ({placeholders})",
                tuple(_INTERNAL_TOOL_NAMES),
            ).rowcount
        if removed:
            logger.info(f"🧹 清理 {removed} 个内部工具从 tool_workshop")

        seeded = 0
        backfilled = 0
        for tool_name in registry.list_tools():
            tool = registry.get(tool_name)
            if not tool:
                continue
            if tool_name in _INTERNAL_TOOL_NAMES:
                continue
            if any(tool_name.startswith(p) for p in _INTERNAL_TOOL_PREFIXES):
                continue

            tags = _TOOL_TAG_MAP.get(tool_name, [])
            existing = self.get_tool(tool_name)
            if existing:
                # 补填空 tags（升级旧数据库）
                if not existing.tags and tags:
                    with self._conn() as conn:
                        conn.execute(
                            "UPDATE tool_workshop SET tags = ? WHERE name = ?",
                            (json.dumps(tags), tool_name),
                        )
                    backfilled += 1
                continue

            schema = tool.to_schema()
            entry = ToolEntry(
                name=tool.name,
                tags=tags,
                summary=tool.description[:300],
                input_schema=schema.get("function", {}).get("parameters", {}),
                content=""
            )
            self.add_tool(entry)
            seeded += 1

        if seeded or backfilled:
            logger.info(f"✓ 工具车间：新增 {seeded} 个，补填 tags {backfilled} 个")
        return seeded

    def get_survival_tools(self) -> List[str]:
        """返回标记为 survival 的工具名称列表（默认出门物资）。"""
        with self._conn() as conn:
            rows = conn.execute("SELECT name, tags FROM tool_workshop").fetchall()
        return [
            r["name"] for r in rows
            if "survival" in json.loads(r["tags"] or "[]")
        ]

    # ─── Capability Workshop ──────────────────────────────────────────────────────

    def update_capability(self, tool_name: str, succeeded: bool, failure_reason: Optional[str] = None) -> None:
        """
        更新工具的执行校准数据。成功和失败都应调用。
        reliability = successes / total_calls，纯执行统计，无 LLM 介入。
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT total_calls, successes FROM capability_workshop WHERE capability = ?",
                (tool_name,)
            ).fetchone()

            now = datetime.now().isoformat()
            if row:
                total = row["total_calls"] + 1
                succ  = row["successes"] + (1 if succeeded else 0)
                rel   = succ / total
                conn.execute(
                    """UPDATE capability_workshop
                       SET total_calls=?, successes=?, reliability=?, common_failure=?, last_updated=?
                       WHERE capability=?""",
                    (total, succ, rel, failure_reason if not succeeded else None, now, tool_name)
                )
            else:
                succ = 1 if succeeded else 0
                conn.execute(
                    """INSERT INTO capability_workshop
                       (capability, total_calls, successes, reliability, common_failure, last_updated)
                       VALUES (?, 1, ?, ?, ?, ?)""",
                    (tool_name, succ, float(succ), failure_reason if not succeeded else None, now)
                )
            conn.commit()

    def get_capability_profile(self, min_calls: int = 2) -> List[Dict[str, Any]]:
        """返回有足够样本量的工具可靠性统计（min_calls 次以上才纳入）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT capability, total_calls, successes, reliability, common_failure "
                "FROM capability_workshop WHERE total_calls >= ? ORDER BY total_calls DESC",
                (min_calls,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── Verified Fact Write (Execution-Confirmed) ──────────────────────────────

    def add_verified_fact(self, key: str, value: str, category: str = "execution", source: str = "tool_execution") -> None:
        """
        直接写入已由工具执行验证的事实，跳过待审队列。

        只应由 Manager._extract_execution_facts() 调用，
        该方法只提取工具返回的字面结果，不做任何 LLM 推断。
        """
        entry = FactEntry(
            key=key,
            category=category,
            value=str(value),
            source=source,
            confidence=1.0,
            last_verified=datetime.now().isoformat()
        )
        self.add_fact(entry)
        # 自动分配维度（从 category 映射）
        dims = self._CATEGORY_TO_DIMS.get(category, {"scope": "general"})
        with self._conn() as conn:
            conn.execute(
                "UPDATE known_info_workshop SET dimensions = ? WHERE key = ?",
                (json.dumps(dims), key)
            )
        logger.info(f"✓ 执行验证事实写入: [{category}] {key} = {str(value)[:60]} dims={dims}")

    # ─── Lesson Application (Feedback Loop) ─────────────────────────────────────

    AUTO_APPROVE_THRESHOLD = 0.9

    def apply_lesson(self, lesson: WorkshopLesson) -> bool:
        """
        将 op 执行经验写入车间或待审队列。

        confidence >= AUTO_APPROVE_THRESHOLD: 自动写入稳定车间（防止堵塞）。
        confidence < AUTO_APPROVE_THRESHOLD: 进 pending_lessons 待人工审核。

        Returns:
            True — 已自动写入稳定车间
            False — 已入队，等待审核
        """
        if lesson.confidence >= self.AUTO_APPROVE_THRESHOLD:
            committed = self._commit_lesson(lesson)
            if committed:
                logger.info(
                    f"✅ Lesson 自动放行 (confidence={lesson.confidence:.2f}): "
                    f"{lesson.lesson_type} → {lesson.target_workshop}"
                )
                return True

        self._queue_lesson(lesson)
        logger.info(
            f"📥 Lesson 待审 (confidence={lesson.confidence:.2f}): "
            f"{lesson.lesson_type} → {lesson.target_workshop}"
        )
        return False

    def _commit_lesson(self, lesson: WorkshopLesson) -> bool:
        """
        将已审核的 lesson 实际写入车间（仅由 approve_lesson 调用）。
        """
        try:
            if lesson.target_workshop == "tool" and lesson.lesson_type == "new_tool":
                self.add_tool(ToolEntry(**lesson.content))

            elif lesson.target_workshop == "known_info":
                if lesson.lesson_type == "new_fact":
                    self.add_fact(FactEntry(**lesson.content))
                elif lesson.lesson_type == "correction":
                    key = lesson.content.get("key")
                    if key:
                        existing = self.get_fact(key)
                        if existing:
                            existing.value = lesson.content.get("value", existing.value)
                            existing.last_verified = datetime.now().isoformat()
                            existing.confidence = lesson.confidence
                            self.add_fact(existing)

            elif lesson.target_workshop == "metacognition" and lesson.lesson_type == "new_pattern":
                self.add_pattern(PatternEntry(**lesson.content))

            logger.info(f"✓ Lesson 写入: {lesson.lesson_type} → {lesson.target_workshop}")
            return True

        except Exception as e:
            logger.error(f"Lesson 写入失败: {e}")
            return False

    def _queue_lesson(self, lesson: WorkshopLesson) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO pending_lessons
                   (id, lesson_type, target_workshop, content, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4())[:8], lesson.lesson_type, lesson.target_workshop,
                 json.dumps(lesson.content), lesson.confidence, datetime.now().isoformat())
            )
            conn.commit()

    def get_pending_lessons(self) -> List[Dict[str, Any]]:
        """获取待用户审核的 lessons 列表"""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM pending_lessons ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def approve_lesson(self, lesson_id: str) -> bool:
        """用户手动确认一条 pending lesson，提升为 confidence=1.0 写入"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM pending_lessons WHERE id = ?", (lesson_id,)
            ).fetchone()
            if not row:
                return False
            lesson = WorkshopLesson(
                lesson_type=row["lesson_type"],
                target_workshop=row["target_workshop"],
                content=json.loads(row["content"]),
                confidence=1.0
            )
            conn.execute("DELETE FROM pending_lessons WHERE id = ?", (lesson_id,))
            conn.commit()
        return self._commit_lesson(lesson)

    def dismiss_lesson(self, lesson_id: str) -> bool:
        """用户拒绝一条 pending lesson，从队列删除"""
        with self._conn() as conn:
            result = conn.execute(
                "DELETE FROM pending_lessons WHERE id = ?", (lesson_id,)
            )
            conn.commit()
        return result.rowcount > 0

    def approve_all_lessons(self) -> int:
        """批量确认所有 pending lessons，返回成功写入数量"""
        lessons = self.get_pending_lessons()
        approved = 0
        for row in lessons:
            if self.approve_lesson(row["id"]):
                approved += 1
        return approved

    def dismiss_all_lessons(self) -> int:
        """批量拒绝所有 pending lessons，返回删除数量"""
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM pending_lessons").fetchone()[0]
            conn.execute("DELETE FROM pending_lessons")
            conn.commit()
        return count

    def format_pending_review(self) -> str:
        """
        返回待审核 lessons 的人类可读摘要。
        用于 agent.review_workshop_lessons() 的输出。
        """
        rows = self.get_pending_lessons()
        if not rows:
            return "✅ 待审核队列为空，没有需要处理的知识。"

        lines = [f"📥 待审核知识 ({len(rows)} 条)\n"]
        for r in rows:
            content = json.loads(r["content"]) if isinstance(r["content"], str) else r["content"]
            summary = list(content.values())[0] if content else "(无内容)"
            lines.append(
                f"  [{r['id']}] {r['lesson_type']} → {r['target_workshop']}"
                f"  confidence={r['confidence']:.2f}"
                f"  | {summary}"
            )
        lines += [
            "",
            "操作方式：",
            "  agent.workshops.approve_lesson('<id>')   # 确认单条",
            "  agent.workshops.dismiss_lesson('<id>')   # 拒绝单条",
            "  agent.workshops.approve_all_lessons()    # 全部确认",
            "  agent.workshops.dismiss_all_lessons()    # 全部拒绝",
        ]
        return "\n".join(lines)

    # ─── Stats ──────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        """返回各车间条目数量，便于调试"""
        with self._conn() as conn:
            return {
                "tool_workshop": conn.execute("SELECT COUNT(*) FROM tool_workshop").fetchone()[0],
                "known_info_workshop": conn.execute("SELECT COUNT(*) FROM known_info_workshop").fetchone()[0],
                "metacognition_workshop": conn.execute("SELECT COUNT(*) FROM metacognition_workshop").fetchone()[0],
                "output_format_workshop": conn.execute("SELECT COUNT(*) FROM output_format_workshop").fetchone()[0],
                "pending_lessons": conn.execute("SELECT COUNT(*) FROM pending_lessons").fetchone()[0],
            }
