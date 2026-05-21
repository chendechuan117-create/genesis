import re
import json
import sqlite3
import time
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from genesis.core.base import Tool
try:
    from genesis.v4.manager import DB_PATH, _LEGACY_DB_PATH
except Exception:
    DB_PATH = Path("~/.genesis/workshop_v4.sqlite").expanduser()
    _LEGACY_DB_PATH = Path("~/.nanogenesis/workshop_v4.sqlite").expanduser()

QUERY_TIMEOUT_SECONDS = 5.0
PLS_DB_ENV_VAR = "GENESIS_PLS_DB_PATH"
PLS_DB_CANDIDATES = [
    "/home/yoga/.genesis/workshop_v4.sqlite",
    "/home/chendechusn/Genesis/Genesis/runtime/yogg_workshop_v4.sqlite",
    "/home/chendechusn/Genesis/Genesis/runtime/workshop_v4_yogg.sqlite",
    "/home/chendechusn/Genesis/Genesis/runtime/workshop_v4_snapshot.sqlite",
]


class PLSQueryTool(Tool):
    def __init__(self):
        self._has_reasoning_lines_same_round = True

    @property
    def name(self) -> str:
        return "pls_query"

    @property
    def description(self) -> str:
        return "只读查询 Genesis PLS 全局拓扑地图：基础点、前沿点、RL-only、饱和虚点、证伪边、势样本、消融和单点详情。"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["overview", "basis", "frontier", "rl_only", "saturation", "contradictions", "potential", "proposals", "ablation", "impact", "basin", "theme", "node"],
                    "description": "查询模式。overview=全局总览；basis=高入线基础点；frontier=未被复用前沿点；rl_only=有推理线但无知识边；saturation=VIRT饱和区；contradictions=正式/语义证伪；potential=势/共场样本；proposals=异步候选暂存；ablation=必要性消融；impact=依赖影响审计；basin=盆地/出口摘要；theme=关键词局部面；node=单点PLS详情。"
                },
                "query": {"type": "string", "description": "theme 模式关键词；node 模式可作为 node_id 备用。"},
                "node_id": {"type": "string", "description": "node 模式目标节点 ID。"},
                "since": {"type": "string", "description": "可选起始时间，格式如 2026-05-06 08:10:00。"},
                "limit": {"type": "integer", "description": "每组返回数量，默认 12，最大 50。"},
                "include_same_round": {"type": "boolean", "description": "是否把 same_round 推理线计入拓扑，默认 false。"},
                "include_hidden": {"type": "boolean", "description": "是否包含 ablation_active>0 的隐藏节点，默认 false。"},
                "include_virtual": {"type": "boolean", "description": "是否包含 is_virtual=1/VIRT_ 虚点，默认 false。"},
                "db_path": {"type": "string", "description": "可选只读 SQLite DB 路径；运维诊断用，默认自动探测 Yogg/本地 NodeVault。"}
            },
            "required": ["mode"]
        }

    def is_concurrency_safe(self, arguments: Dict[str, Any]) -> bool:
        return True

    async def execute(self, mode: str = "overview", query: str = "", node_id: str = "", since: str = "", limit: int = 12, include_same_round: bool = False, db_path: str = "", **kwargs) -> str:
        conn = None
        try:
            mode = (mode or "overview").strip().lower()
            include_hidden = self._bool_arg(kwargs.get("include_hidden"), False)
            include_virtual = self._bool_arg(kwargs.get("include_virtual"), False)
            conn, resolved_db_path = self._connect_ro(db_path, require_knowledge_nodes=(mode != "proposals"))
            resolved_limit = self._limit(limit)
            if mode == "overview":
                return self._with_source(self._overview(conn, since, resolved_limit, include_same_round, include_hidden, include_virtual), resolved_db_path)
            if mode == "basis":
                return self._with_source(self._basis(conn, since, resolved_limit, include_same_round, include_hidden, include_virtual), resolved_db_path)
            if mode == "frontier":
                return self._with_source(self._frontier(conn, since, resolved_limit, include_same_round, include_hidden, include_virtual), resolved_db_path)
            if mode == "rl_only":
                return self._with_source(self._rl_only(conn, since, resolved_limit, include_same_round, include_hidden, include_virtual), resolved_db_path)
            if mode == "saturation":
                return self._with_source(self._saturation(conn, since, resolved_limit), resolved_db_path)
            if mode == "contradictions":
                return self._with_source(self._contradictions(conn, since, resolved_limit, include_hidden, include_virtual), resolved_db_path)
            if mode == "potential":
                return self._with_source(self._potential(conn, since, resolved_limit), resolved_db_path)
            if mode == "proposals":
                return self._with_source(self._proposals(conn, query, since, resolved_limit), resolved_db_path)
            if mode == "ablation":
                return self._with_source(self._ablation(conn, since, resolved_limit), resolved_db_path)
            if mode == "impact":
                return self._with_source(self._impact(conn, node_id or query, resolved_limit, include_same_round, include_hidden, include_virtual), resolved_db_path)
            if mode == "basin":
                return self._with_source(self._basin(conn, query, since, resolved_limit, include_hidden, include_virtual), resolved_db_path)
            if mode == "theme":
                return self._with_source(self._theme(conn, query, since, resolved_limit, include_same_round, include_hidden, include_virtual), resolved_db_path)
            if mode == "node":
                return self._with_source(self._node(conn, node_id or query, resolved_limit, include_same_round, include_hidden, include_virtual), resolved_db_path)
            return f"未知 mode: {mode}"
        except Exception as e:
            return f"PLS查询失败: {e}"
        finally:
            if conn is not None:
                conn.close()

    def _connect_ro(self, requested_db_path: str = "", require_knowledge_nodes: bool = True) -> Tuple[sqlite3.Connection, Path]:
        candidates = self._db_candidates(requested_db_path)
        errors = []
        for db_path, required in candidates:
            try:
                if not db_path.exists():
                    if required:
                        raise FileNotFoundError(f"DB 不存在: {db_path}")
                    continue
                if db_path.stat().st_size <= 0:
                    if required:
                        raise FileNotFoundError(f"DB 为空文件: {db_path}")
                    continue
                conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=3)
                conn.row_factory = sqlite3.Row
                deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
                conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
                if require_knowledge_nodes and not self._has_table(conn, "knowledge_nodes"):
                    conn.close()
                    if required:
                        raise FileNotFoundError(f"DB 缺少 knowledge_nodes 表: {db_path}")
                    continue
                try:
                    cols = [r[1] for r in conn.execute("PRAGMA table_info(reasoning_lines)").fetchall()]
                    self._has_reasoning_lines_same_round = "same_round" in cols
                except Exception:
                    self._has_reasoning_lines_same_round = False
                return conn, db_path
            except Exception as e:
                errors.append(f"{db_path}: {e}")
                if required:
                    break
        searched = "；".join(str(p) for p, _ in candidates)
        detail = "；".join(errors[-5:])
        raise FileNotFoundError(f"未找到可用 NodeVault/PLS DB。searched={searched}。errors={detail}")

    def _db_candidates(self, requested_db_path: str = "") -> List[Tuple[Path, bool]]:
        requested = (requested_db_path or "").strip()
        if requested:
            return [(Path(requested).expanduser(), True)]
        env_path = os.environ.get(PLS_DB_ENV_VAR, "").strip()
        if env_path:
            return [(Path(env_path).expanduser(), True)]
        result = []
        seen = set()
        for raw in PLS_DB_CANDIDATES + [DB_PATH, _LEGACY_DB_PATH]:
            path = Path(raw).expanduser()
            key = path.as_posix()
            if key in seen:
                continue
            seen.add(key)
            result.append((path, False))
        return result

    def _with_source(self, text: str, db_path: Path) -> str:
        return f"[PLS DB] {db_path}\n{text}"

    def _limit(self, limit: int) -> int:
        try:
            return max(1, min(50, int(limit or 12)))
        except Exception:
            return 12

    def _bool_arg(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    def _rl_filter(self, include_same_round: bool, alias: str = "rl") -> str:
        if not self._has_reasoning_lines_same_round:
            return "1=1"
        return "1=1" if include_same_round else f"COALESCE({alias}.same_round, 0) = 0"

    def _active_node_filter(self, alias: str, include_hidden: bool = False, include_virtual: bool = False) -> str:
        clauses = []
        if not include_hidden:
            clauses.append(f"COALESCE({alias}.ablation_active,0)=0")
        if not include_virtual:
            clauses.append(f"COALESCE({alias}.is_virtual,0)=0")
        return " AND ".join(clauses) if clauses else "1=1"

    def _node_scope_filter(self, alias: str = "k", include_hidden: bool = False, include_virtual: bool = False) -> str:
        return f"{alias}.node_id NOT LIKE 'MEM_CONV_%' AND {self._active_node_filter(alias, include_hidden, include_virtual)}"

    def _active_rl_filter(self, include_same_round: bool, alias: str = "rl", new_alias: str = "new_node", basis_alias: str = "basis_node", include_hidden: bool = False, include_virtual: bool = False) -> str:
        return (
            f"{self._rl_filter(include_same_round, alias)} "
            f"AND {self._active_node_filter(new_alias, include_hidden, include_virtual)} "
            f"AND {self._active_node_filter(basis_alias, include_hidden, include_virtual)}"
        )

    def _active_edge_filter(self, src_alias: str = "src", dst_alias: str = "dst", include_hidden: bool = False, include_virtual: bool = False) -> str:
        return (
            f"{self._active_node_filter(src_alias, include_hidden, include_virtual)} "
            f"AND {self._active_node_filter(dst_alias, include_hidden, include_virtual)}"
        )

    def _since(self, alias: str, since: str) -> Tuple[str, List[Any]]:
        if since and str(since).strip():
            return f" AND {alias}.created_at >= ?", [str(since).strip()]
        return "", []

    def _scalar(self, conn, sql: str, params: List[Any] = None) -> int:
        row = conn.execute(sql, params or []).fetchone()
        return int(row[0] or 0) if row else 0

    def _has_table(self, conn, table: str) -> bool:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [table]).fetchone()
        return row is not None

    def _has_column(self, conn, table: str, column: str) -> bool:
        try:
            return column in {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            return False

    def _short(self, value: Any, n: int = 84) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[: n - 3] + "..." if len(text) > n else text

    def _node_metrics(self, conn, nid: str, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> Dict[str, int]:
        rl_cond = self._active_rl_filter(include_same_round, include_hidden=include_hidden, include_virtual=include_virtual)
        edge_cond = self._active_edge_filter(include_hidden=include_hidden, include_virtual=include_virtual)
        return {
            "incoming": self._scalar(conn, f"""SELECT COUNT(*)
                FROM reasoning_lines rl
                JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
                JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
                WHERE rl.basis_point_id = ? AND {rl_cond}""", [nid]),
            "rl_out": self._scalar(conn, f"""SELECT COUNT(*)
                FROM reasoning_lines rl
                JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
                JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
                WHERE rl.new_point_id = ? AND {rl_cond}""", [nid]),
            "edge_out": self._scalar(conn, f"""SELECT COUNT(*)
                FROM node_edges e
                JOIN knowledge_nodes src ON src.node_id = e.source_id
                JOIN knowledge_nodes dst ON dst.node_id = e.target_id
                WHERE e.source_id = ? AND {edge_cond}""", [nid]),
            "edge_in": self._scalar(conn, f"""SELECT COUNT(*)
                FROM node_edges e
                JOIN knowledge_nodes src ON src.node_id = e.source_id
                JOIN knowledge_nodes dst ON dst.node_id = e.target_id
                WHERE e.target_id = ? AND {edge_cond}""", [nid]),
            "contradicted_by": self._scalar(conn, f"""SELECT COUNT(*)
                FROM node_edges e
                JOIN knowledge_nodes src ON src.node_id = e.source_id
                JOIN knowledge_nodes dst ON dst.node_id = e.target_id
                WHERE e.target_id = ? AND LOWER(e.relation) IN ('contradicts','falsifies','falsify','contradict') AND {edge_cond}""", [nid]),
        }

    def _overview(self, conn, since: str, limit: int, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> str:
        ns, np = self._since("k", since)
        es, ep = self._since("e", since)
        rs, rp = self._since("rl", since)
        node_scope = self._node_scope_filter("k", include_hidden, include_virtual)
        node_where = "WHERE " + node_scope + ns
        rl_where = "WHERE 1=1" + rs
        edge_where = "WHERE 1=1" + es
        rl_cond = self._active_rl_filter(include_same_round, include_hidden=include_hidden, include_virtual=include_virtual)
        edge_cond = self._active_edge_filter(include_hidden=include_hidden, include_virtual=include_virtual)
        lines = ["=== PLS全局地图 / overview ==="]
        if since:
            lines.append(f"window: {since} → now")
        lines.append(f"nodes(non_mem): {self._scalar(conn, 'SELECT COUNT(*) FROM knowledge_nodes k ' + node_where, np)}")
        lines.append(f"nodes(active_nonvirtual): {self._scalar(conn, 'SELECT COUNT(*) FROM knowledge_nodes k ' + node_where + ' AND COALESCE(k.is_virtual,0)=0 AND COALESCE(k.ablation_active,0)=0', np)}")
        lines.append(f"virtual_saturation_points: {self._scalar(conn, 'SELECT COUNT(*) FROM knowledge_nodes k ' + node_where + ' AND (COALESCE(k.is_virtual,0)=1 OR k.node_id LIKE \'VIRT_%\')', np)}")
        lines.append(f"reasoning_lines: {self._scalar(conn, 'SELECT COUNT(*) FROM reasoning_lines rl ' + rl_where, rp)}")
        lines.append(f"reasoning_lines_counted_for_pls: {self._scalar(conn, 'SELECT COUNT(*) FROM reasoning_lines rl JOIN knowledge_nodes new_node ON new_node.node_id=rl.new_point_id JOIN knowledge_nodes basis_node ON basis_node.node_id=rl.basis_point_id ' + rl_where + ' AND ' + rl_cond, rp)}")
        lines.append(f"node_edges: {self._scalar(conn, 'SELECT COUNT(*) FROM node_edges e ' + edge_where, ep)}")
        lines.append(f"node_edges_counted_for_pls: {self._scalar(conn, 'SELECT COUNT(*) FROM node_edges e JOIN knowledge_nodes src ON src.node_id=e.source_id JOIN knowledge_nodes dst ON dst.node_id=e.target_id ' + edge_where + ' AND ' + edge_cond, ep)}")
        lines.append(f"formal_contradiction_edges: {self._scalar(conn, 'SELECT COUNT(*) FROM node_edges e JOIN knowledge_nodes src ON src.node_id=e.source_id JOIN knowledge_nodes dst ON dst.node_id=e.target_id ' + edge_where + " AND LOWER(e.relation) IN ('contradicts','falsifies','falsify','contradict') AND " + edge_cond, ep)}")
        lines.append(f"open_void_tasks: {self._scalar(conn, "SELECT COUNT(*) FROM void_tasks WHERE status = 'open'")}")
        if self._has_table(conn, "potential_samples"):
            ps, pp = self._since("p", since)
            lines.append(f"potential_samples: {self._scalar(conn, 'SELECT COUNT(*) FROM potential_samples p WHERE 1=1' + ps, pp)}")
        if self._has_table(conn, "ablation_baselines"):
            lines.append(f"ablation_baselines: {self._scalar(conn, 'SELECT COUNT(*) FROM ablation_baselines')}")
        lines.append(f"ablation_active_nodes: {self._scalar(conn, 'SELECT COUNT(*) FROM knowledge_nodes WHERE COALESCE(ablation_active,0)>0')}")
        rows = conn.execute("SELECT k.node_id FROM knowledge_nodes k " + node_where, np).fetchall()
        ids = [r[0] for r in rows]
        patterns = {
            "P_Q_R": sum(1 for nid in ids if str(nid).startswith("P_Q_R")),
            "P_R": sum(1 for nid in ids if re.fullmatch(r"P_R\d+[A-Z]?", str(nid) or "")),
            "P_hash10": sum(1 for nid in ids if re.fullmatch(r"P_[0-9A-F]{10}", str(nid) or "")),
            "VIRT": sum(1 for nid in ids if str(nid).startswith("VIRT_")),
        }
        lines.append("id_patterns: " + ", ".join(f"{k}={v}" for k, v in patterns.items()))
        lines.append("")
        lines.append("-- type distribution --")
        for row in conn.execute("SELECT k.type, COUNT(*) c FROM knowledge_nodes k " + node_where + " GROUP BY k.type ORDER BY c DESC LIMIT 12", np):
            lines.append(f"{row['type']}: {row['c']}")
        lines.append("")
        lines.append("-- node_edge relations --")
        for row in conn.execute("SELECT LOWER(e.relation) rel, COUNT(*) c FROM node_edges e " + edge_where + " GROUP BY LOWER(e.relation) ORDER BY c DESC LIMIT 12", ep):
            lines.append(f"{row['rel']}: {row['c']}")
        lines.append("")
        lines.append("-- top basis preview --")
        lines.extend(self._basis_rows(conn, "", min(6, limit), include_same_round, include_hidden, include_virtual))
        return "\n".join(lines)

    def _basis_rows(self, conn, since: str, limit: int, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> List[str]:
        ns, np = self._since("k", since)
        rl_cond = self._active_rl_filter(include_same_round, include_hidden=include_hidden, include_virtual=include_virtual)
        node_scope = self._node_scope_filter("k", include_hidden, include_virtual)
        rows = conn.execute(f"""
            SELECT k.node_id, k.type, k.title, k.usage_count, k.created_at, COUNT(*) incoming
            FROM knowledge_nodes k
            JOIN reasoning_lines rl ON rl.basis_point_id = k.node_id
            JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
            JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
            WHERE {node_scope} {ns} AND {rl_cond}
            GROUP BY k.node_id
            ORDER BY incoming DESC, COALESCE(k.usage_count,0) DESC
            LIMIT ?
        """, np + [limit]).fetchall()
        if not rows:
            return ["(none)"]
        result = []
        for r in rows:
            m = self._node_metrics(conn, r['node_id'], include_same_round, include_hidden, include_virtual)
            result.append(f"{r['incoming']:>3} in | rl_out={m['rl_out']} edges={m['edge_out']}/{m['edge_in']} | {r['node_id']} <{r['type']}> {self._short(r['title'])}")
        return result

    def _basis(self, conn, since: str, limit: int, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> str:
        lines = ["=== PLS基础点 / basis ==="]
        if since:
            lines.append(f"window: {since} → now")
        lines.extend(self._basis_rows(conn, since, limit, include_same_round, include_hidden, include_virtual))
        return "\n".join(lines)

    def _frontier(self, conn, since: str, limit: int, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> str:
        ns, np = self._since("k", since)
        node_scope = self._node_scope_filter("k", include_hidden, include_virtual)
        rl_cond = self._active_rl_filter(include_same_round, include_hidden=include_hidden, include_virtual=include_virtual)
        ri_cond = self._active_rl_filter(include_same_round, alias="ri", new_alias="ri_new", basis_alias="ri_basis", include_hidden=include_hidden, include_virtual=include_virtual)
        edge_cond = self._active_edge_filter(include_hidden=include_hidden, include_virtual=include_virtual)
        rows = conn.execute(f"""
            SELECT k.node_id, k.type, k.title, k.created_at, COALESCE(k.usage_count,0) usage_count,
                   (SELECT COUNT(*) FROM reasoning_lines rl
                    JOIN knowledge_nodes new_node ON new_node.node_id=rl.new_point_id
                    JOIN knowledge_nodes basis_node ON basis_node.node_id=rl.basis_point_id
                    WHERE rl.new_point_id=k.node_id AND {rl_cond}) rl_out,
                   (SELECT COUNT(*) FROM node_edges e
                    JOIN knowledge_nodes src ON src.node_id=e.source_id
                    JOIN knowledge_nodes dst ON dst.node_id=e.target_id
                    WHERE (e.source_id=k.node_id OR e.target_id=k.node_id) AND {edge_cond}) edge_count
            FROM knowledge_nodes k
            WHERE {node_scope} {ns}
              AND NOT EXISTS (
                SELECT 1 FROM reasoning_lines ri
                JOIN knowledge_nodes ri_new ON ri_new.node_id=ri.new_point_id
                JOIN knowledge_nodes ri_basis ON ri_basis.node_id=ri.basis_point_id
                WHERE ri.basis_point_id=k.node_id AND {ri_cond}
              )
            ORDER BY k.created_at DESC
            LIMIT ?
        """, np + [limit]).fetchall()
        lines = ["=== PLS前沿点 / frontier ==="]
        for r in rows:
            lines.append(f"{r['created_at']} | rl_out={r['rl_out']} edges={r['edge_count']} usage={r['usage_count']} | {r['node_id']} <{r['type']}> {self._short(r['title'])}")
        return "\n".join(lines if len(lines) > 1 else lines + ["(none)"])

    def _rl_only(self, conn, since: str, limit: int, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> str:
        ns, np = self._since("k", since)
        node_scope = self._node_scope_filter("k", include_hidden, include_virtual)
        rl_cond = self._active_rl_filter(include_same_round, include_hidden=include_hidden, include_virtual=include_virtual)
        ri_cond = self._active_rl_filter(include_same_round, alias="ri", new_alias="ri_new", basis_alias="ri_basis", include_hidden=include_hidden, include_virtual=include_virtual)
        ro_cond = self._active_rl_filter(include_same_round, alias="ro", new_alias="ro_new", basis_alias="ro_basis", include_hidden=include_hidden, include_virtual=include_virtual)
        edge_cond = self._active_edge_filter(include_hidden=include_hidden, include_virtual=include_virtual)
        rows = conn.execute(f"""
            SELECT k.node_id, k.type, k.title, k.created_at, COALESCE(k.usage_count,0) usage_count,
                   (SELECT COUNT(*) FROM reasoning_lines rl
                    JOIN knowledge_nodes new_node ON new_node.node_id=rl.new_point_id
                    JOIN knowledge_nodes basis_node ON basis_node.node_id=rl.basis_point_id
                    WHERE rl.new_point_id=k.node_id AND {rl_cond}) rl_out,
                   (SELECT COUNT(*) FROM reasoning_lines ri
                    JOIN knowledge_nodes ri_new ON ri_new.node_id=ri.new_point_id
                    JOIN knowledge_nodes ri_basis ON ri_basis.node_id=ri.basis_point_id
                    WHERE ri.basis_point_id=k.node_id AND {ri_cond}) incoming
            FROM knowledge_nodes k
            WHERE {node_scope} {ns}
              AND EXISTS (
                SELECT 1 FROM reasoning_lines ro
                JOIN knowledge_nodes ro_new ON ro_new.node_id=ro.new_point_id
                JOIN knowledge_nodes ro_basis ON ro_basis.node_id=ro.basis_point_id
                WHERE ro.new_point_id=k.node_id AND {ro_cond}
              )
              AND NOT EXISTS (
                SELECT 1 FROM node_edges e
                JOIN knowledge_nodes src ON src.node_id=e.source_id
                JOIN knowledge_nodes dst ON dst.node_id=e.target_id
                WHERE (e.source_id=k.node_id OR e.target_id=k.node_id) AND {edge_cond}
              )
            ORDER BY usage_count DESC, k.created_at DESC
            LIMIT ?
        """, np + [limit]).fetchall()
        lines = ["=== RL-only节点 / reasoning anchored but no node_edges ==="]
        for r in rows:
            lines.append(f"usage={r['usage_count']} incoming={r['incoming']} rl_out={r['rl_out']} | {r['node_id']} <{r['type']}> {self._short(r['title'])}")
        return "\n".join(lines if len(lines) > 1 else lines + ["(none)"])

    def _saturation(self, conn, since: str, limit: int) -> str:
        ns, np = self._since("k", since)
        rows = conn.execute(f"""
            SELECT k.node_id, k.title, k.created_at, COALESCE(k.usage_count,0) usage_count,
                   COUNT(e.source_id) linked_edges
            FROM knowledge_nodes k
            LEFT JOIN node_edges e ON e.source_id=k.node_id OR e.target_id=k.node_id
            WHERE (COALESCE(k.is_virtual,0)=1 OR k.node_id LIKE 'VIRT_%') {ns}
            GROUP BY k.node_id
            ORDER BY usage_count DESC, k.created_at DESC
            LIMIT ?
        """, np + [limit]).fetchall()
        lines = ["=== PLS饱和区 / saturation VIRT ==="]
        for r in rows:
            links = conn.execute("""
                SELECT CASE WHEN e.source_id=? THEN e.target_id ELSE e.source_id END nid, k.title
                FROM node_edges e LEFT JOIN knowledge_nodes k ON k.node_id = CASE WHEN e.source_id=? THEN e.target_id ELSE e.source_id END
                WHERE e.source_id=? OR e.target_id=? LIMIT 4
            """, [r['node_id'], r['node_id'], r['node_id'], r['node_id']]).fetchall()
            linked = "; ".join(f"{x['nid']}:{self._short(x['title'], 36)}" for x in links)
            lines.append(f"usage={r['usage_count']} links={r['linked_edges']} | {r['node_id']} {self._short(r['title'])}")
            if linked:
                lines.append(f"  linked: {linked}")
        return "\n".join(lines if len(lines) > 1 else lines + ["(none)"])

    def _contradictions(self, conn, since: str, limit: int, include_hidden: bool = False, include_virtual: bool = False) -> str:
        es, ep = self._since("e", since)
        ns, np = self._since("k", since)
        edge_cond = self._active_edge_filter(include_hidden=include_hidden, include_virtual=include_virtual)
        node_scope = self._node_scope_filter("k", include_hidden, include_virtual)
        formal = conn.execute(f"""
            SELECT e.created_at, e.source_id, s.title st, e.relation, e.target_id, t.title tt
            FROM node_edges e
            JOIN knowledge_nodes src ON src.node_id=e.source_id
            JOIN knowledge_nodes dst ON dst.node_id=e.target_id
            LEFT JOIN knowledge_nodes s ON s.node_id=e.source_id
            LEFT JOIN knowledge_nodes t ON t.node_id=e.target_id
            WHERE LOWER(e.relation) IN ('contradicts','falsifies','falsify','contradict') {es}
              AND {edge_cond}
            ORDER BY e.created_at DESC LIMIT ?
        """, ep + [limit]).fetchall()
        terms = ["%证伪%", "%反驳%", "%矛盾%", "%失效%", "%invalidated%", "%falsif%", "%contradict%"]
        debt = conn.execute(f"""
            SELECT k.node_id, k.type, k.title, k.created_at
            FROM knowledge_nodes k
            WHERE {node_scope} {ns}
              AND ({' OR '.join(['k.title LIKE ?' for _ in terms])})
              AND NOT EXISTS (
                SELECT 1 FROM node_edges e
                JOIN knowledge_nodes src ON src.node_id=e.source_id
                JOIN knowledge_nodes dst ON dst.node_id=e.target_id
                WHERE e.source_id=k.node_id AND LOWER(e.relation) IN ('contradicts','falsifies','falsify','contradict')
                  AND {edge_cond}
              )
            ORDER BY k.created_at DESC LIMIT ?
        """, np + terms + [limit]).fetchall()
        lines = ["=== PLS证伪/衰减 / contradictions ===", "-- formal edges --"]
        for r in formal:
            lines.append(f"{r['created_at']} | {r['source_id']} --{r['relation']}--> {r['target_id']} | {self._short(r['st'], 52)} -> {self._short(r['tt'], 52)}")
        if not formal:
            lines.append("(none)")
        lines.append("-- semantic contradiction debt: title says falsify/invalidated but no formal edge --")
        for r in debt:
            lines.append(f"{r['created_at']} | {r['node_id']} <{r['type']}> {self._short(r['title'])}")
        if not debt:
            lines.append("(none)")
        return "\n".join(lines)

    def _potential(self, conn, since: str, limit: int) -> str:
        if not self._has_table(conn, "potential_samples"):
            return "potential_samples 表不存在。"
        ps, pp = self._since("p", since)
        has_status = self._has_column(conn, "potential_samples", "status")
        status_expr = "COALESCE(p.status, 'open')" if has_status else "'legacy_open'"
        resolution_expr = "p.resolution_node_id" if self._has_column(conn, "potential_samples", "resolution_node_id") else "NULL"
        resolution_note_expr = "p.resolution_note" if self._has_column(conn, "potential_samples", "resolution_note") else "NULL"
        triage_expr = "COALESCE(p.triage_category, 'structural')" if self._has_column(conn, "potential_samples", "triage_category") else "'structural'"
        target_expr = "p.target_basin" if self._has_column(conn, "potential_samples", "target_basin") else "NULL"
        note_expr = "p.triage_note" if self._has_column(conn, "potential_samples", "triage_note") else "NULL"
        occurrence_expr = "COALESCE(p.occurrence_count, 1)" if self._has_column(conn, "potential_samples", "occurrence_count") else "1"
        last_seen_expr = "p.last_seen_at" if self._has_column(conn, "potential_samples", "last_seen_at") else "NULL"
        dedupe_expr = "p.dedupe_key" if self._has_column(conn, "potential_samples", "dedupe_key") else "NULL"
        rows = conn.execute(f"""
            SELECT p.created_at, p.source, p.potential_type, p.title, p.detail, p.node_ids, p.evidence,
                   {status_expr} status, {resolution_expr} resolution_node_id, {resolution_note_expr} resolution_note,
                   {triage_expr} triage_category, {target_expr} target_basin, {note_expr} triage_note,
                   {occurrence_expr} occurrence_count, {last_seen_expr} last_seen_at, {dedupe_expr} dedupe_key
            FROM potential_samples p
            WHERE 1=1 {ps}
            ORDER BY p.created_at DESC, p.sample_id DESC
            LIMIT ?
        """, pp + [limit]).fetchall()
        lines = ["=== PLS势样本 / potential samples ==="]
        if since:
            lines.append(f"window: {since} → now")
        if self._has_column(conn, "potential_samples", "dedupe_key"):
            guard = conn.execute(f"""
                SELECT COUNT(*) total_rows,
                       SUM(CASE WHEN p.dedupe_key IS NULL OR p.dedupe_key = '' THEN 1 ELSE 0 END) missing_dedupe,
                       SUM(CASE WHEN {status_expr} IN ('open', 'actionable') THEN 1 ELSE 0 END) active_open,
                       SUM(CASE WHEN {status_expr} IN ('open', 'actionable') AND {triage_expr} = 'actionable' THEN 1 ELSE 0 END) actionable_open,
                       SUM(CASE WHEN {status_expr} IN ('open', 'actionable') AND {triage_expr} <> 'actionable' THEN 1 ELSE 0 END) non_actionable_open
                FROM potential_samples p
                WHERE 1=1 {ps}
            """, pp).fetchone()
            if guard:
                lines.append("-- lifecycle guardrails --")
                lines.append(
                    f"total={guard['total_rows'] or 0} missing_dedupe={guard['missing_dedupe'] or 0} "
                    f"active_open={guard['active_open'] or 0} actionable_open={guard['actionable_open'] or 0} "
                    f"non_actionable_open={guard['non_actionable_open'] or 0}"
                )
        lines.append("-- distribution --")
        for r in conn.execute(f"""
            SELECT p.source, p.potential_type, {triage_expr} triage_category, {status_expr} status,
                   COUNT(*) c, SUM({occurrence_expr}) occurrences
            FROM potential_samples p
            WHERE 1=1 {ps}
            GROUP BY p.source, p.potential_type, {triage_expr}, {status_expr}
            ORDER BY c DESC LIMIT 12
        """, pp):
            lines.append(f"{r['triage_category']} | {r['status']} | {r['source']} / {r['potential_type']}: rows={r['c']} seen={r['occurrences']}")
        lines.append("-- recent samples --")
        for r in rows:
            seen = r['occurrence_count'] or 1
            last_seen = f" | last_seen={r['last_seen_at']}" if r['last_seen_at'] else ""
            lines.append(f"{r['created_at']} | {r['triage_category']} | {r['status']} | seen={seen}{last_seen} | {r['source']} / {r['potential_type']} | {self._short(r['title'])}")
            lines.append(f"  detail: {self._short(r['detail'], 120)}")
            if r['target_basin']:
                lines.append(f"  basin: {self._short(r['target_basin'], 120)}")
            if r['triage_note']:
                lines.append(f"  triage: {self._short(r['triage_note'], 120)}")
            if r['dedupe_key']:
                lines.append(f"  dedupe: {str(r['dedupe_key'])[:12]}")
            lines.append(f"  nodes: {self._short(r['node_ids'], 160)}")
            if r['resolution_node_id']:
                lines.append(f"  resolution: {r['resolution_node_id']}")
            if r['resolution_note']:
                lines.append(f"  resolution_note: {self._short(r['resolution_note'], 120)}")
            if r['evidence']:
                lines.append(f"  evidence: {self._short(r['evidence'], 160)}")
        return "\n".join(lines if len(lines) > 3 else lines + ["(none)"])

    def _proposal_payload_summary(self, payload_text: str, basis_text: str) -> Tuple[str, str, str, List[str]]:
        try:
            payload = json.loads(payload_text or "{}")
        except Exception:
            payload = {}
        try:
            basis_ids = json.loads(basis_text or "[]")
        except Exception:
            basis_ids = []
        if not isinstance(payload, dict):
            payload = {}
        if not isinstance(basis_ids, list):
            basis_ids = []
        clean_basis = list(dict.fromkeys(str(nid or "").strip() for nid in basis_ids if str(nid or "").strip()))
        node_id = str(payload.get("node_id") or "").strip()
        title = self._short(payload.get("title") or payload.get("summary") or payload.get("name") or "", 96)
        schema = "current" if payload.get("schema_version") else "legacy"
        blockers = []
        if not node_id:
            blockers.append("missing_node_id")
        if not title:
            blockers.append("missing_title")
        if not str(payload.get("content") or "").strip():
            blockers.append("missing_content")
        if not clean_basis:
            blockers.append("missing_basis_ids")
        if not str(payload.get("reasoning") or "").strip():
            blockers.append("missing_line_reasoning")
        return schema, node_id, title, blockers

    def _proposals(self, conn, query: str, since: str, limit: int) -> str:
        if not self._has_table(conn, "pls_proposals"):
            return "pls_proposals 表不存在。"
        ps, pp = self._since("p", since)
        q = (query or "").strip()
        where = "WHERE 1=1" + ps
        params = list(pp)
        if q and q.lower() != "all":
            like = f"%{q}%"
            where += " AND (p.status = ? OR p.branch_id = ? OR p.proposal_type = ? OR p.proposal_id LIKE ? OR p.payload_json LIKE ?)"
            params.extend([q, q, q, like, like])
        rows = conn.execute(
            "SELECT p.proposal_id, p.parent_trace_id, p.parent_round_seq, p.branch_id, p.proposal_type, "
            "p.source, p.payload_json, p.basis_ids_json, p.status, p.merge_result, p.created_at "
            f"FROM pls_proposals p {where} ORDER BY p.created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        lines = ["=== PLS异步候选暂存 / proposals ==="]
        lines.append("说明：只读观察 staging；proposal 不是事实，不参与入线数，不触发消融。")
        if since:
            lines.append(f"window: {since} → now")
        if q:
            lines.append(f"filter: {self._short(q, 80)}")
        if not rows:
            return "\n".join(lines + ["(none)"])
        for r in rows:
            schema, node_id, title, blockers = self._proposal_payload_summary(r["payload_json"], r["basis_ids_json"])
            state = str(r["status"] or "pending")
            branch = str(r["branch_id"] or "")
            title_text = title or "(untitled direction)"
            lines.append(f"{r['created_at']} | {state} | {branch} | {r['proposal_id']} | {title_text}")
            lines.append(f"  type: {r['proposal_type']} | source: {r['source']} | schema: {schema}")
            if r["parent_trace_id"] or r["parent_round_seq"] is not None:
                lines.append(f"  parent: {r['parent_trace_id'] or '-'} / round={r['parent_round_seq']}")
            if node_id:
                lines.append(f"  candidate: {node_id}")
            if blockers:
                lines.append("  preview_blockers: " + ", ".join(blockers))
            if r["merge_result"]:
                lines.append(f"  review: {self._short(r['merge_result'], 140)}")
        return "\n".join(lines)

    def _impact(self, conn, node_id: str, limit: int, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> str:
        nid = (node_id or "").strip()
        if not nid:
            return "impact 模式需要 node_id 或 query。"
        row = conn.execute("SELECT node_id, title FROM knowledge_nodes WHERE node_id=?", [nid]).fetchone()
        if not row:
            return f"未找到节点: {nid}"
        rl_cond = self._active_rl_filter(include_same_round, include_hidden=include_hidden, include_virtual=include_virtual)
        rb_cond = self._active_rl_filter(include_same_round, alias="rb", new_alias="rb_new", basis_alias="rb_basis", include_hidden=include_hidden, include_virtual=include_virtual)
        edge_cond = self._active_edge_filter(include_hidden=include_hidden, include_virtual=include_virtual)
        queue = [(nid, 0)]
        visited = {nid}
        impacts = []
        while queue and len(impacts) < limit:
            current, depth = queue.pop(0)
            if depth >= 3:
                continue
            rows = conn.execute(f"""
                SELECT rl.new_point_id, n.title, rl.reasoning,
                       (SELECT COUNT(*)
                        FROM reasoning_lines rb
                        JOIN knowledge_nodes rb_new ON rb_new.node_id=rb.new_point_id
                        JOIN knowledge_nodes rb_basis ON rb_basis.node_id=rb.basis_point_id
                        WHERE rb.new_point_id=rl.new_point_id AND {rb_cond}) basis_count,
                       (SELECT COUNT(*)
                        FROM node_edges e
                        JOIN knowledge_nodes src ON src.node_id=e.source_id
                        JOIN knowledge_nodes dst ON dst.node_id=e.target_id
                        WHERE e.target_id=rl.new_point_id
                          AND LOWER(e.relation) IN ('contradicts','falsifies','falsify','contradict','rebuts','undercuts','supersedes','narrows_scope')
                          AND {edge_cond}) incoming_decay
                FROM reasoning_lines rl
                JOIN knowledge_nodes new_node ON new_node.node_id=rl.new_point_id
                JOIN knowledge_nodes basis_node ON basis_node.node_id=rl.basis_point_id
                LEFT JOIN knowledge_nodes n ON n.node_id=rl.new_point_id
                WHERE rl.basis_point_id=? AND {rl_cond}
                ORDER BY rl.created_at DESC
            """, [current]).fetchall()
            for r in rows:
                child = r["new_point_id"]
                if not child or child in visited:
                    continue
                visited.add(child)
                child_depth = depth + 1
                basis_count = int(r["basis_count"] or 0)
                incoming_decay = int(r["incoming_decay"] or 0)
                if child_depth == 1 and basis_count <= 1:
                    status = "needs_recheck"
                elif basis_count <= child_depth:
                    status = "dependency_risk"
                elif incoming_decay > 0:
                    status = "already_under_decay"
                else:
                    status = "still_supported"
                impacts.append((child_depth, status, child, r["title"], basis_count, r["reasoning"]))
                if len(impacts) >= limit:
                    break
                queue.append((child, child_depth))
        lines = ["=== PLS依赖影响审计 / impact ==="]
        lines.append(f"root: {nid} | {self._short(row['title'], 120)}")
        lines.append("说明：只读复查提示，不判定真伪，不自动删除或消融。")
        if not impacts:
            lines.append("(no dependents)")
            return "\n".join(lines)
        summary: Dict[str, int] = {}
        for _, status, *_ in impacts:
            summary[status] = summary.get(status, 0) + 1
        lines.append("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
        for depth, status, child, title, basis_count, reasoning in impacts[:limit]:
            lines.append(f"d={depth} | {status} | basis_set={basis_count} | {child} | {self._short(title, 72)}")
            if reasoning:
                lines.append(f"  because: {self._short(reasoning, 120)}")
        return "\n".join(lines)

    def _basin(self, conn, query: str, since: str, limit: int, include_hidden: bool = False, include_virtual: bool = False) -> str:
        q = (query or "").strip()
        if not q:
            return "basin 模式需要 query。"
        ns, np = self._since("k", since)
        node_scope = self._node_scope_filter("k", include_hidden, include_virtual)
        ri_cond = self._active_rl_filter(False, alias="ri", new_alias="ri_new", basis_alias="ri_basis", include_hidden=include_hidden, include_virtual=include_virtual)
        ro_cond = self._active_rl_filter(False, alias="ro", new_alias="ro_new", basis_alias="ro_basis", include_hidden=include_hidden, include_virtual=include_virtual)
        tokens = [t for t in re.findall(r"[\w\u4e00-\u9fff]+", q) if len(t) >= 2][:6]
        likes = [f"%{t}%" for t in tokens] or [f"%{q}%"]
        cond = " OR ".join(["k.title LIKE ? OR k.tags LIKE ? OR k.resolves LIKE ? OR c.full_content LIKE ?" for _ in likes])
        params = np + [x for like in likes for x in (like, like, like, like)]
        rows = conn.execute(f"""
            SELECT k.node_id, k.type, k.title, k.created_at, COALESCE(k.ablation_active,0) ablation_active,
                   (SELECT COUNT(*)
                    FROM reasoning_lines ri
                    JOIN knowledge_nodes ri_new ON ri_new.node_id=ri.new_point_id
                    JOIN knowledge_nodes ri_basis ON ri_basis.node_id=ri.basis_point_id
                    WHERE ri.basis_point_id=k.node_id AND {ri_cond}) incoming,
                   (SELECT COUNT(*)
                    FROM reasoning_lines ro
                    JOIN knowledge_nodes ro_new ON ro_new.node_id=ro.new_point_id
                    JOIN knowledge_nodes ro_basis ON ro_basis.node_id=ro.basis_point_id
                    WHERE ro.new_point_id=k.node_id AND {ro_cond}) rl_out
            FROM knowledge_nodes k LEFT JOIN node_contents c ON c.node_id=k.node_id
            WHERE {node_scope} {ns} AND ({cond})
            GROUP BY k.node_id
            ORDER BY incoming DESC, k.created_at DESC
            LIMIT ?
        """, params + [limit]).fetchall()
        ids = [r["node_id"] for r in rows]
        lines = [f"=== PLS盆地摘要 / basin: {q} ==="]
        lines.append("说明：只读中尺度地图，必须回到下列点线 provenance；不是新的“理”。")
        lines.append(f"matched_nodes: {len(ids)}")
        if not ids:
            return "\n".join(lines + ["(none)"])
        active = sum(1 for r in rows if int(r["ablation_active"] or 0) == 0)
        hidden = len(rows) - active
        incoming_sum = sum(int(r["incoming"] or 0) for r in rows)
        rl_out_sum = sum(int(r["rl_out"] or 0) for r in rows)
        lines.append(f"shape: active={active}, hidden={hidden}, incoming_sum={incoming_sum}, rl_out_sum={rl_out_sum}")
        lines.append("-- anchors / high-dependence points --")
        for r in rows[: min(8, limit)]:
            visibility = "hidden" if int(r["ablation_active"] or 0) > 0 else "active"
            lines.append(f"{visibility} | in={r['incoming']} out={r['rl_out']} | {r['node_id']} <{r['type']}> {self._short(r['title'])}")
        placeholders = ",".join("?" * len(ids))
        sat = conn.execute(f"""
            SELECT DISTINCT v.node_id, v.title, COALESCE(v.usage_count,0) usage_count
            FROM node_edges e JOIN knowledge_nodes v ON v.node_id=e.source_id OR v.node_id=e.target_id
            WHERE (e.source_id IN ({placeholders}) OR e.target_id IN ({placeholders})) AND COALESCE(v.is_virtual,0)=1
            ORDER BY usage_count DESC LIMIT 6
        """, ids + ids).fetchall()
        if sat:
            lines.append("-- saturation summary --")
            for r in sat:
                lines.append(f"usage={r['usage_count']} | {r['node_id']} {self._short(r['title'])}")
        debt = conn.execute(f"""
            SELECT k.node_id, k.title, k.created_at
            FROM knowledge_nodes k
            WHERE k.node_id IN ({placeholders})
              AND (k.title LIKE '%证伪%' OR k.title LIKE '%反驳%' OR k.title LIKE '%矛盾%' OR k.title LIKE '%失效%' OR LOWER(k.title) LIKE '%contradict%')
              AND NOT EXISTS (
                SELECT 1 FROM node_edges e
                WHERE e.source_id=k.node_id AND LOWER(e.relation) IN ('contradicts','falsifies','falsify','contradict')
              )
            ORDER BY k.created_at DESC LIMIT 6
        """, ids).fetchall()
        if debt:
            lines.append("-- contradiction debt --")
            for r in debt:
                lines.append(f"{r['created_at']} | {r['node_id']} {self._short(r['title'])}")
        if self._has_table(conn, "potential_samples"):
            has_triage = self._has_column(conn, "potential_samples", "triage_category")
            triage_expr = "COALESCE(triage_category, 'structural')" if has_triage else "'structural'"
            target_clause = " OR target_basin LIKE ?" if self._has_column(conn, "potential_samples", "target_basin") else ""
            target_params = [f"%{q}%"] if target_clause else []
            potential = conn.execute(f"""
                SELECT {triage_expr} triage_category, potential_type, title, created_at
                FROM potential_samples
                WHERE title LIKE ? OR detail LIKE ?{target_clause}
                ORDER BY created_at DESC LIMIT 6
            """, [f"%{q}%", f"%{q}%"] + target_params).fetchall()
            if potential:
                lines.append("-- exit/action signals --")
                for r in potential:
                    lines.append(f"{r['created_at']} | {r['triage_category']} / {r['potential_type']} | {self._short(r['title'])}")
        return "\n".join(lines)

    def _ablation(self, conn, since: str, limit: int) -> str:
        rows = conn.execute("""
            SELECT k.node_id, k.type, k.title, k.created_at, k.updated_at, COALESCE(k.ablation_active,0) ablation_active
            FROM knowledge_nodes k
            WHERE COALESCE(k.ablation_active,0)>0
            ORDER BY k.updated_at DESC LIMIT ?
        """, [limit]).fetchall()
        lines = ["=== PLS必要性消融 / ablation ==="]
        lines.append("-- integrity --")
        lines.append(f"active_without_baseline: {self._scalar(conn, 'SELECT COUNT(*) FROM knowledge_nodes k LEFT JOIN ablation_baselines a ON a.node_id=k.node_id WHERE COALESCE(k.ablation_active,0)>0 AND a.node_id IS NULL')}")
        lines.append(f"baseline_without_active: {self._scalar(conn, 'SELECT COUNT(*) FROM ablation_baselines a LEFT JOIN knowledge_nodes k ON k.node_id=a.node_id WHERE k.node_id IS NULL OR COALESCE(k.ablation_active,0)=0')}")
        lines.append("-- active hidden nodes --")
        for r in rows:
            lines.append(f"active={r['ablation_active']} | {r['node_id']} <{r['type']}> {self._short(r['title'])}")
        if not rows:
            lines.append("(none)")
        if self._has_table(conn, "ablation_baselines"):
            lines.append("-- baselines --")
            for r in conn.execute("""
                SELECT a.node_id, datetime(a.activated_at, 'unixepoch') activated_at, a.baseline_env_ratio, k.title
                FROM ablation_baselines a
                LEFT JOIN knowledge_nodes k ON k.node_id=a.node_id
                ORDER BY a.activated_at DESC LIMIT ?
            """, [limit]):
                lines.append(f"{r['activated_at']} | ratio={r['baseline_env_ratio']} | {r['node_id']} {self._short(r['title'])}")
        return "\n".join(lines)

    def _theme(self, conn, query: str, since: str, limit: int, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> str:
        q = (query or "").strip()
        if not q:
            return "theme 模式需要 query。"
        ns, np = self._since("k", since)
        node_scope = self._node_scope_filter("k", include_hidden, include_virtual)
        tokens = [t for t in re.findall(r"[\w\u4e00-\u9fff]+", q) if len(t) >= 2][:6]
        likes = [f"%{t}%" for t in tokens] or [f"%{q}%"]
        cond = " OR ".join(["k.title LIKE ? OR k.tags LIKE ? OR k.resolves LIKE ? OR c.full_content LIKE ?" for _ in likes])
        params = np + [x for like in likes for x in (like, like, like, like)]
        matched = conn.execute(f"""
            SELECT k.node_id, k.type, k.title, k.created_at, COALESCE(k.usage_count,0) usage_count
            FROM knowledge_nodes k LEFT JOIN node_contents c ON c.node_id=k.node_id
            WHERE {node_scope} {ns} AND ({cond})
            GROUP BY k.node_id ORDER BY k.created_at DESC LIMIT ?
        """, params + [limit]).fetchall()
        ids = [r['node_id'] for r in matched]
        lines = [f"=== PLS主题局部面 / theme: {q} ===", f"matched_preview: {len(ids)}"]
        if not ids:
            return "\n".join(lines + ["(none)"])
        for r in matched:
            m = self._node_metrics(conn, r['node_id'], include_same_round, include_hidden, include_virtual)
            lines.append(f"{r['created_at']} | in={m['incoming']} rl_out={m['rl_out']} edges={m['edge_out']}/{m['edge_in']} usage={r['usage_count']} | {r['node_id']} <{r['type']}> {self._short(r['title'])}")
        placeholders = ",".join("?" * len(ids))
        sat = conn.execute(f"""
            SELECT DISTINCT v.node_id, v.title, COALESCE(v.usage_count,0) usage_count
            FROM node_edges e JOIN knowledge_nodes v ON v.node_id=e.source_id OR v.node_id=e.target_id
            WHERE (e.source_id IN ({placeholders}) OR e.target_id IN ({placeholders})) AND COALESCE(v.is_virtual,0)=1
            ORDER BY usage_count DESC LIMIT 5
        """, ids + ids).fetchall()
        if sat:
            lines.append("-- nearby saturation --")
            for r in sat:
                lines.append(f"usage={r['usage_count']} | {r['node_id']} {self._short(r['title'])}")
        return "\n".join(lines)

    def _node(self, conn, node_id: str, limit: int, include_same_round: bool, include_hidden: bool = False, include_virtual: bool = False) -> str:
        nid = (node_id or "").strip()
        if not nid:
            return "node 模式需要 node_id。"
        row = conn.execute("SELECT k.*, c.full_content FROM knowledge_nodes k LEFT JOIN node_contents c ON c.node_id=k.node_id WHERE k.node_id=?", [nid]).fetchone()
        if not row:
            candidates = conn.execute("SELECT node_id, title FROM knowledge_nodes WHERE node_id LIKE ? ORDER BY updated_at DESC LIMIT 8", [nid + "%"]).fetchall()
            if candidates:
                return "未找到精确节点。候选:\n" + "\n".join(f"{r['node_id']} | {self._short(r['title'])}" for r in candidates)
            return f"未找到节点: {nid}"
        m = self._node_metrics(conn, nid, include_same_round, include_hidden, include_virtual)
        lines = [f"=== PLS单点详情 / node: {nid} ==="]
        lines.append(f"<{row['type']}> {self._short(row['title'], 140)}")
        lines.append(f"created={row['created_at']} updated={row['updated_at']} usage={row['usage_count']} virtual={row['is_virtual']} ablation={row['ablation_active']}")
        lines.append(f"incoming={m['incoming']} rl_out={m['rl_out']} node_edges(out/in)={m['edge_out']}/{m['edge_in']} contradicted_by={m['contradicted_by']}")
        if row['full_content']:
            lines.append("content: " + self._short(row['full_content'], 360))
        rl_cond = self._active_rl_filter(include_same_round, include_hidden=include_hidden, include_virtual=include_virtual)
        edge_cond = self._active_edge_filter(include_hidden=include_hidden, include_virtual=include_virtual)
        basis = conn.execute(f"""SELECT rl.basis_point_id, b.title, rl.reasoning
            FROM reasoning_lines rl
            JOIN knowledge_nodes new_node ON new_node.node_id=rl.new_point_id
            JOIN knowledge_nodes basis_node ON basis_node.node_id=rl.basis_point_id
            LEFT JOIN knowledge_nodes b ON b.node_id=rl.basis_point_id
            WHERE rl.new_point_id=? AND {rl_cond}
            ORDER BY rl.created_at DESC LIMIT ?""", [nid, limit]).fetchall()
        lines.append("-- basis lines (this node based_on old points) --")
        lines.extend([f"{r['basis_point_id']} | {self._short(r['title'], 58)} | {self._short(r['reasoning'], 120)}" for r in basis] or ["(none)"])
        dependents = conn.execute(f"""SELECT rl.new_point_id, n.title, rl.reasoning
            FROM reasoning_lines rl
            JOIN knowledge_nodes new_node ON new_node.node_id=rl.new_point_id
            JOIN knowledge_nodes basis_node ON basis_node.node_id=rl.basis_point_id
            LEFT JOIN knowledge_nodes n ON n.node_id=rl.new_point_id
            WHERE rl.basis_point_id=? AND {rl_cond}
            ORDER BY rl.created_at DESC LIMIT ?""", [nid, limit]).fetchall()
        lines.append("-- incoming dependents (new points based_on this node) --")
        lines.extend([f"{r['new_point_id']} | {self._short(r['title'], 58)} | {self._short(r['reasoning'], 120)}" for r in dependents] or ["(none)"])
        edges = conn.execute(f"""
            SELECT 'out' dir, e.relation, e.target_id nid, k.title
            FROM node_edges e
            JOIN knowledge_nodes src ON src.node_id=e.source_id
            JOIN knowledge_nodes dst ON dst.node_id=e.target_id
            LEFT JOIN knowledge_nodes k ON k.node_id=e.target_id
            WHERE e.source_id=? AND {edge_cond}
            UNION ALL
            SELECT 'in' dir, e.relation, e.source_id nid, k.title
            FROM node_edges e
            JOIN knowledge_nodes src ON src.node_id=e.source_id
            JOIN knowledge_nodes dst ON dst.node_id=e.target_id
            LEFT JOIN knowledge_nodes k ON k.node_id=e.source_id
            WHERE e.target_id=? AND {edge_cond}
            LIMIT ?
        """, [nid, nid, limit * 2]).fetchall()
        lines.append("-- node_edges --")
        lines.extend([f"{r['dir']} {r['relation']} {r['nid']} | {self._short(r['title'], 72)}" for r in edges] or ["(none)"])
        return "\n".join(lines)
