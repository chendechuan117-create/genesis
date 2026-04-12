"""
Community Detector — 从实体关系图中检测功能社区

使用 Louvain 算法（networkx 内置）对 CO_OCCURS 关系图做社区检测。
每个社区代表一组经常在同一 session 中一起出现的实体——即一个"功能集群"。

例如：
  - v2ray 集群: v2raya, v2ray, config.json, .proxy_env, .bashrc, .profile
  - docker 集群: docker, genesis-doctor, doctor.sh, entrypoint.sh
  - provider 集群: provider_manager.py, config.py, .env

社区标签通过启发式从成员中推导（最高频实体 + 类型组合）。
"""

import sqlite3
import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path
from collections import Counter

import networkx as nx
from networkx.algorithms.community import louvain_communities

from .entity_store import TraceEntityStore

logger = logging.getLogger(__name__)

_ENTITY_DB = Path(__file__).resolve().parent.parent.parent.parent / "runtime" / "trace_entities.db"

# 社区存储 schema
_COMMUNITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_communities (
    community_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    label           TEXT NOT NULL,           -- 启发式标签
    member_count    INTEGER NOT NULL,
    total_evidence  INTEGER DEFAULT 0,       -- 社区内边的总证据数
    avg_confidence  REAL DEFAULT 0.0,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    resolution      REAL DEFAULT 1.0         -- Louvain resolution 参数
);

CREATE TABLE IF NOT EXISTS community_members (
    community_id    INTEGER NOT NULL,
    entity_id       INTEGER NOT NULL,
    entity_type     TEXT NOT NULL,
    value           TEXT NOT NULL,
    centrality      REAL DEFAULT 0.0,        -- 在社区内的中心度
    PRIMARY KEY (community_id, entity_id),
    FOREIGN KEY (community_id) REFERENCES entity_communities(community_id),
    FOREIGN KEY (entity_id) REFERENCES canonical_entities(entity_id)
);

CREATE INDEX IF NOT EXISTS idx_cm_entity ON community_members(entity_id);
"""

# 只用高信号类型建图（排除 COMMAND / EXIT_CODE 噪声太大）
_GRAPH_ENTITY_TYPES = frozenset(["FILE", "SERVICE", "ERROR", "PACKAGE", "DIRECTORY", "URL"])

# 社区最小成员数（太小的没意义）
_MIN_COMMUNITY_SIZE = 3


class TraceCommunityDetector:
    """从 CO_OCCURS 关系图检测功能社区"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _ENTITY_DB
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=5)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_schema(self):
        conn = self._get_conn()
        conn.executescript(_COMMUNITY_SCHEMA)
        conn.commit()

    def _build_graph(self) -> Tuple[nx.Graph, Dict[int, Dict]]:
        """从 CO_OCCURS 关系构建 networkx 图。返回 (graph, node_info_map)。"""
        conn = self._get_conn()

        # 获取所有高信号类型的 CO_OCCURS 关系
        type_list = ','.join(f"'{t}'" for t in _GRAPH_ENTITY_TYPES)
        edges = conn.execute(f"""
            SELECT er.source_entity_id, er.target_entity_id,
                   er.evidence_count, er.confidence
            FROM entity_relationships er
            JOIN canonical_entities ce1 ON ce1.entity_id = er.source_entity_id
            JOIN canonical_entities ce2 ON ce2.entity_id = er.target_entity_id
            WHERE er.rel_type = 'CO_OCCURS'
              AND ce1.entity_type IN ({type_list})
              AND ce2.entity_type IN ({type_list})
              AND er.evidence_count >= 2
        """).fetchall()

        # 获取节点信息
        entity_ids = set()
        for e in edges:
            entity_ids.add(e["source_entity_id"])
            entity_ids.add(e["target_entity_id"])

        node_info = {}
        if entity_ids:
            placeholders = ','.join('?' * len(entity_ids))
            entities = conn.execute(f"""
                SELECT entity_id, entity_type, value, occurrence_count, session_count
                FROM canonical_entities
                WHERE entity_id IN ({placeholders})
            """, list(entity_ids)).fetchall()
            for ent in entities:
                node_info[ent["entity_id"]] = dict(ent)

        G = nx.Graph()
        for eid, info in node_info.items():
            G.add_node(eid, **info)

        for e in edges:
            G.add_edge(
                e["source_entity_id"], e["target_entity_id"],
                weight=e["evidence_count"],
                confidence=e["confidence"]
            )

        return G, node_info

    def _generate_label(self, members: List[Dict]) -> str:
        """为社区生成启发式标签"""
        # 按 occurrence_count 排序，取前 2 个最具代表性的
        sorted_members = sorted(members, key=lambda m: m.get("occurrence_count", 0), reverse=True)

        # 优先用 SERVICE 类型的名字
        services = [m for m in sorted_members if m["entity_type"] == "SERVICE"]
        if services:
            primary = services[0]["value"]
            types = Counter(m["entity_type"] for m in members)
            type_summary = "+".join(f"{cnt}{t[:3]}" for t, cnt in types.most_common(3))
            return f"{primary} ({type_summary})"

        # 否则用最高频实体的值（取文件名部分）
        if sorted_members:
            val = sorted_members[0]["value"]
            # 从路径中提取文件名
            if "/" in val:
                val = val.rsplit("/", 1)[-1]
            if len(val) > 30:
                val = val[:27] + "..."
            types = Counter(m["entity_type"] for m in members)
            type_summary = "+".join(f"{cnt}{t[:3]}" for t, cnt in types.most_common(3))
            return f"{val} ({type_summary})"

        return "unknown"

    def detect(self, resolution: float = 1.0, min_size: int = _MIN_COMMUNITY_SIZE) -> Dict[str, Any]:
        """
        运行社区检测。清除旧社区，写入新结果。
        resolution: Louvain 分辨率，>1 产生更多小社区，<1 产生更少大社区。
        """
        conn = self._get_conn()
        now = time.time()

        # 构建图
        G, node_info = self._build_graph()
        if G.number_of_nodes() < min_size:
            return {"status": "insufficient_data", "nodes": G.number_of_nodes()}

        logger.info(f"Community detection: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

        # Louvain 社区检测
        communities = louvain_communities(G, weight='weight', resolution=resolution, seed=42)

        # 过滤太小的社区
        valid_communities = [c for c in communities if len(c) >= min_size]

        # 清除旧数据
        conn.execute("DELETE FROM community_members")
        conn.execute("DELETE FROM entity_communities")

        # 计算中心度
        try:
            degree_centrality = nx.degree_centrality(G)
        except Exception:
            degree_centrality = {}

        # 写入新社区
        results = []
        for community_set in valid_communities:
            members = []
            total_evidence = 0
            total_conf = 0.0
            edge_count = 0

            for eid in community_set:
                info = node_info.get(eid, {})
                members.append({
                    "entity_id": eid,
                    "entity_type": info.get("entity_type", "?"),
                    "value": info.get("value", "?"),
                    "occurrence_count": info.get("occurrence_count", 0),
                    "centrality": degree_centrality.get(eid, 0.0),
                })

            # 计算社区内边的统计
            subgraph = G.subgraph(community_set)
            for _, _, data in subgraph.edges(data=True):
                total_evidence += data.get("weight", 1)
                total_conf += data.get("confidence", 0.5)
                edge_count += 1

            avg_conf = total_conf / edge_count if edge_count > 0 else 0.0
            label = self._generate_label(members)

            cursor = conn.execute(
                "INSERT INTO entity_communities "
                "(label, member_count, total_evidence, avg_confidence, "
                "created_at, updated_at, resolution) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (label, len(members), total_evidence, round(avg_conf, 3),
                 now, now, resolution)
            )
            cid = cursor.lastrowid

            for m in members:
                conn.execute(
                    "INSERT INTO community_members "
                    "(community_id, entity_id, entity_type, value, centrality) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (cid, m["entity_id"], m["entity_type"], m["value"],
                     round(m["centrality"], 4))
                )

            results.append({
                "community_id": cid,
                "label": label,
                "member_count": len(members),
                "total_evidence": total_evidence,
                "avg_confidence": round(avg_conf, 3),
            })

        conn.commit()

        logger.info(
            f"Community detection done: {len(valid_communities)} communities "
            f"(filtered {len(communities) - len(valid_communities)} < {min_size} members)"
        )

        return {
            "status": "ok",
            "graph_nodes": G.number_of_nodes(),
            "graph_edges": G.number_of_edges(),
            "total_communities": len(communities),
            "valid_communities": len(valid_communities),
            "filtered_small": len(communities) - len(valid_communities),
            "communities": sorted(results, key=lambda x: -x["total_evidence"]),
        }

    # ── Query API ──────────────────────────────────────────────────────

    def get_communities(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取所有社区（按证据强度排序）"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM entity_communities ORDER BY total_evidence DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_community_members(self, community_id: int) -> List[Dict[str, Any]]:
        """获取社区成员（按中心度排序）"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM community_members WHERE community_id = ? ORDER BY centrality DESC",
            (community_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def find_entity_community(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """查找某实体所属社区"""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT ec.* FROM entity_communities ec
            JOIN community_members cm ON cm.community_id = ec.community_id
            WHERE cm.entity_id = ?
        """, (entity_id,)).fetchone()
        return dict(row) if row else None

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
