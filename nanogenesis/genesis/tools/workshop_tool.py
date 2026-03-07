"""
Genesis V3 - Workshop Tool
Genesis 的自管理记忆接口。

Genesis 通过此工具直接操作自己的 SQLite 数据库。
没有预设 schema。Genesis 自己决定 CREATE 什么表、INSERT 什么数据。
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any

from genesis.core.base import Tool

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".nanogenesis" / "workshop_v3.sqlite"


class WorkshopTool(Tool):
    """
    Genesis 的持久化记忆。
    允许 Genesis 执行任意 SQL 来管理自己的知识。
    """

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "workshop"

    @property
    def description(self) -> str:
        return (
            "Your persistent memory. A SQLite database that survives across conversations. "
            "Use 'schema' to see what your past self left behind. "
            "Use 'query' to read data (SELECT). "
            "Use 'execute' to write data (CREATE/INSERT/UPDATE/DELETE/ALTER). "
            "You decide the structure. There is no preset schema."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["schema", "query", "execute"],
                    "description": (
                        "'schema': show all tables and their columns. "
                        "'query': run a SELECT statement. "
                        "'execute': run CREATE/INSERT/UPDATE/DELETE/ALTER."
                    )
                },
                "sql": {
                    "type": "string",
                    "description": "The SQL statement to run. Required for 'query' and 'execute'."
                }
            },
            "required": ["action"]
        }

    async def execute(self, action: str, sql: str = "", **kwargs) -> str:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            if action == "schema":
                return self._get_schema(conn)
            elif action == "query":
                return self._run_query(conn, sql)
            elif action == "execute":
                # Safe DDL Guardrails
                sql_upper = sql.upper().strip()
                if "DROP TABLE" in sql_upper or ("DELETE FROM" in sql_upper and "WHERE" not in sql_upper):
                    return (
                        "Error: [System Guardrail] Destructive operations (DROP TABLE, bulk DELETE without WHERE) "
                        "are prohibited to protect core memory. If you want to deprecate data, please use a status flag "
                        "like `is_deleted = 1` instead."
                    )
                return self._run_execute(conn, sql)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"Workshop error: {e}"
        finally:
            conn.close()

    def _get_schema(self, conn: sqlite3.Connection) -> str:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        if not tables:
            return "Workshop is empty. No tables exist yet. This may be your first awakening."

        lines = [f"Workshop has {len(tables)} table(s):\n"]
        for t in tables:
            tname = t["name"]
            cols = conn.execute(f"PRAGMA table_info({tname})").fetchall()
            count = conn.execute(f"SELECT COUNT(*) as c FROM {tname}").fetchone()["c"]
            col_desc = ", ".join(f"{c['name']} ({c['type'] or 'TEXT'})" for c in cols)
            lines.append(f"  {tname} ({count} rows): {col_desc}")

        return "\n".join(lines)

    def _run_query(self, conn: sqlite3.Connection, sql: str) -> str:
        if not sql.strip():
            return "Error: No SQL provided."

        rows = conn.execute(sql).fetchall()
        if not rows:
            return "(no results)"

        # Format as readable text
        keys = rows[0].keys()
        lines = [" | ".join(keys)]
        lines.append("-" * len(lines[0]))
        for row in rows[:100]:  # Cap at 100 rows
            lines.append(" | ".join(str(row[k]) for k in keys))

        if len(rows) > 100:
            lines.append(f"... ({len(rows)} total rows, showing first 100)")

        return "\n".join(lines)

    def _run_execute(self, conn: sqlite3.Connection, sql: str) -> str:
        if not sql.strip():
            return "Error: No SQL provided."

        cursor = conn.execute(sql)
        conn.commit()
        affected = cursor.rowcount
        return f"OK. Rows affected: {affected}"
