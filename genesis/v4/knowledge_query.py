"""
Knowledge Query Layer — 只读查询，为 G/Lens prompt 生成认知数据。

从 NodeVault (manager.py) 提取。与 NodeVault 共享 _conn，但不执行任何写操作。
职责边界：所有 SELECT-only 的 prompt 数据生成方法。
"""

import json
import os
import re
from collections import defaultdict
from typing import List, Dict, Any
import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def normalize_node_dict(d: dict) -> dict:
    """确保节点 dict 同时包含 'type' 和 'ntype' 键（一劳永逸消除 type/ntype 混淆）。
    
    DB 列名是 'type'，Python 惯用 'ntype' 避免遮蔽内置函数。
    SQL 有时用 'type AS ntype'（dict 只有 ntype），有时不用（dict 只有 type）。
    此函数确保无论哪种情况，两个键都存在且一致。
    """
    if 'type' in d and 'ntype' not in d:
        d['ntype'] = d['type']
    elif 'ntype' in d and 'type' not in d:
        d['type'] = d['ntype']
    return d


class KnowledgeQuery:
    """只读查询层：为 G/Lens prompt 生成认知摘要、知识地图、记忆等。"""

    # 噪声标签：系统自动打的来源标记，不代表主题
    _NOISE_TAGS = frozenset({"auto_managed", "tool", "skill", "scavenger", "meta_redesign_derivation"})
    _HEARTBEAT_STALE_AFTER_SECONDS = 3900
    _TYPE_SIGNAL_NOTE = "type=工具塑形schema字段，非语义角色/验证状态"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ─── G Prompt 数据 ───

    def get_digest(self, top_k: int = 4) -> str:
        """精简认知目录：类别计数 + 入线数拓扑 + 知识缺口"""
        type_rows = self._conn.execute(
            "SELECT type, COUNT(*) AS cnt FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' AND ablation_active = 0 AND COALESCE(is_virtual, 0) = 0 GROUP BY type ORDER BY cnt DESC"
        ).fetchall()
        type_counts = {r['type']: r['cnt'] for r in type_rows}
        total = sum(type_counts.values())

        # 入线数 TOP 节点（点线面价值信号：被多少新点基于它产生）
        top_incoming = self._conn.execute(
            """SELECT rl.basis_point_id, COUNT(*) as incoming, kn.type, kn.title
               FROM reasoning_lines rl
               JOIN knowledge_nodes kn ON rl.basis_point_id = kn.node_id
               WHERE kn.node_id NOT LIKE 'MEM_CONV%'
                 AND kn.ablation_active = 0
                 AND COALESCE(kn.is_virtual, 0) = 0
                 AND COALESCE(rl.same_round, 0) = 0
               GROUP BY rl.basis_point_id
               ORDER BY incoming DESC
               LIMIT ?""",
            (top_k,)
        ).fetchall()

        # 前沿节点：最近创建、尚未被后续作为 basis 引用（非验证状态）
        frontier_rows = self._conn.execute(
            """SELECT kn.node_id, kn.type, kn.title, kn.created_at
               FROM knowledge_nodes kn
               WHERE kn.node_id NOT LIKE 'MEM_CONV%'
                 AND kn.ablation_active = 0
                 AND COALESCE(kn.is_virtual, 0) = 0
                 AND kn.type IN ('LESSON', 'CONTEXT', 'DISCOVERY')
                 AND kn.node_id NOT IN (SELECT basis_point_id FROM reasoning_lines WHERE COALESCE(same_round, 0) = 0)
                 AND kn.node_id NOT IN (SELECT target_id FROM node_edges WHERE relation = 'CONTRADICTS')
               ORDER BY kn.created_at DESC
               LIMIT ?""",
            (top_k,)
        ).fetchall()

        # 知识缺口：从 void_tasks 队列读取
        void_rows = self.get_recent_voids(limit=3)

        cats = " | ".join(f"{t}:{c}" for t, c in type_counts.items() if c > 0)
        lines = [f"[认知目录] {total}节点 | {cats}", self._TYPE_SIGNAL_NOTE]
        if top_incoming:
            lines.append("基础候选（被频繁作为 basis 引用，非验证证明）:")
            for r in top_incoming:
                lines.append(f"- [{r['basis_point_id']}] <{r['type']}> {r['title']}")
        if frontier_rows:
            lines.append("前沿候选（尚未被后续作为 basis 引用，非验证状态）:")
            for r in frontier_rows:
                lines.append(f"- [{r['node_id']}] <{r['type']}> {r['title']}")
        if void_rows:
            lines.append("VOID (知识缺口):")
            for r in void_rows:
                lines.append(f"- [{r['void_id']}] {r['query']}")
        lines.append("需要细节时请使用 get_knowledge_node_content 读取具体节点。")
        return "\n".join(lines)

    def generate_map(self, max_clusters_per_type: int = 8, titles_per_cluster: int = 3) -> str:
        """生成分层标签地图：按 type → primary_tag 聚类，供 G prompt 注入。
        
        设计目标：让 G 看到知识全貌（~30-50 行，~1-2K tokens），
        解决"不知道搜什么→看不到→用不上"的发现问题。
        """
        rows = self._conn.execute(
            """SELECT type, title, tags FROM knowledge_nodes
               WHERE node_id NOT LIKE 'MEM_CONV%'
                 AND ablation_active = 0
                 AND COALESCE(is_virtual, 0) = 0
               ORDER BY type, usage_count DESC"""
        ).fetchall()
        if not rows:
            return "[Knowledge Map] 知识库为空"

        def _extract_topic(title: str) -> str:
            """从标题提取主题词（当标签无用时的回退）"""
            # 优先匹配开头的英文专有名词
            m = re.match(r'([A-Z][a-zA-Z0-9._-]+)', title)
            if m and len(m.group(1)) >= 3:
                return m.group(1)
            # 中文：取前 2-4 字
            m = re.match(r'([\u4e00-\u9fff]{2,4})', title)
            if m:
                return m.group(1)
            return "其他"

        # 按 type → primary_tag 聚类
        type_clusters = defaultdict(lambda: defaultdict(list))  # {type: {tag: [titles]}}
        type_totals = defaultdict(int)
        for r in rows:
            ntype = r['type'] or 'UNKNOWN'
            title = r['title'] or ''
            tags_raw = r['tags'] or ''
            # 跳过噪声标签，取第一个有意义的标签
            primary_tag = None
            if tags_raw.strip():
                for t in tags_raw.split(','):
                    t = t.strip()
                    if t and t.lower() not in self._NOISE_TAGS:
                        primary_tag = t
                        break
            # 无有意义标签时，从标题提取主题
            if not primary_tag:
                primary_tag = _extract_topic(title)
            type_clusters[ntype][primary_tag].append(title)
            type_totals[ntype] += 1

        total = sum(type_totals.values())

        # VOID 统计（增强版：按 source 分组 + 更多样本 + 签名标签）
        void_count = 0
        void_details = []  # [(query, sig_label)]
        void_source_counts = {}
        try:
            void_row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM void_tasks WHERE status = 'open'"
            ).fetchone()
            void_count = void_row['cnt'] if void_row else 0
            if void_count > 0:
                # 按 source 统计分布
                src_rows = self._conn.execute(
                    "SELECT source, COUNT(*) as cnt FROM void_tasks WHERE status = 'open' GROUP BY source ORDER BY cnt DESC"
                ).fetchall()
                void_source_counts = {r['source']: r['cnt'] for r in src_rows}
                # 取最近 6 条，含签名维度
                void_samples_rows = self._conn.execute(
                    "SELECT query, task_signature FROM void_tasks WHERE status = 'open' ORDER BY created_at DESC LIMIT 6"
                ).fetchall()
                for r in void_samples_rows:
                    query = r['query'][:60]
                    sig_label = ""
                    if r['task_signature']:
                        try:
                            sig = json.loads(r['task_signature']) if isinstance(r['task_signature'], str) else r['task_signature']
                            # 提取最有辨识度的签名维度作为标签
                            for dim in ("application", "runtime", "framework", "target_kind", "task_kind"):
                                val = sig.get(dim)
                                if val:
                                    sig_label = val if isinstance(val, str) else val[0] if isinstance(val, list) and val else ""
                                    break
                        except Exception:
                            pass
                    void_details.append((query, sig_label))
        except Exception:
            pass  # void_tasks 表可能不存在

        lines = [f"[Knowledge Map · {total} nodes · {void_count} VOID]", ""]

        # 按节点数降序排列 type
        sorted_types = sorted(type_totals.keys(), key=lambda t: type_totals[t], reverse=True)

        for ntype in sorted_types:
            clusters = type_clusters[ntype]
            type_total = type_totals[ntype]
            lines.append(f"{ntype} ({type_total}):")

            # 按簇大小降序，取前 max_clusters_per_type
            sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
            shown_clusters = sorted_clusters[:max_clusters_per_type]
            hidden_count = len(sorted_clusters) - len(shown_clusters)
            hidden_nodes = sum(len(titles) for _, titles in sorted_clusters[max_clusters_per_type:])

            for i, (tag, titles) in enumerate(shown_clusters):
                is_last = (i == len(shown_clusters) - 1) and hidden_count == 0
                prefix = "└─" if is_last else "├─"
                # 展示 top N 标题（已按 usage_count DESC 排序）
                shown_titles = [t[:25] for t in titles[:titles_per_cluster]]
                remaining = len(titles) - len(shown_titles)
                title_str = " | ".join(shown_titles)
                if remaining > 0:
                    title_str += f" | +{remaining}"
                lines.append(f"{prefix} {tag} ({len(titles)}): {title_str}")

            if hidden_count > 0:
                lines.append(f"└─ ... ({hidden_nodes} nodes in {hidden_count} other clusters)")

            lines.append("")

        # 基础候选（高入线数引用代理，非验证证明）——含被 CONTRADICTS 标记的节点
        top_incoming = self._conn.execute(
            """SELECT rl.basis_point_id, COUNT(*) as incoming, kn.type, kn.title,
                      CASE WHEN ne.target_id IS NOT NULL THEN 1 ELSE 0 END as has_contradiction
               FROM reasoning_lines rl
               JOIN knowledge_nodes kn ON rl.basis_point_id = kn.node_id
               LEFT JOIN (
                   SELECT DISTINCT target_id FROM node_edges WHERE relation = 'CONTRADICTS'
               ) ne ON kn.node_id = ne.target_id
               WHERE kn.node_id NOT LIKE 'MEM_CONV%'
                 AND kn.ablation_active = 0
                 AND COALESCE(kn.is_virtual, 0) = 0
                 AND COALESCE(rl.same_round, 0) = 0
               GROUP BY rl.basis_point_id
               ORDER BY incoming DESC
               LIMIT 4"""
        ).fetchall()
        if top_incoming:
            lines.append("基础候选（频繁被引用，非验证证明）:")
            for r in top_incoming:
                # PLS: 用矛盾边标记而非 usage 胜率
                contradiction_marker = " CONTRADICTS标记" if r['has_contradiction'] else ""
                lines.append(f"  {r['basis_point_id']} <{r['type']}> {r['title']}{contradiction_marker}")
            lines.append("")

        # 前沿候选（尚未被后续作为 basis 引用，非验证状态）
        frontier_rows = self._conn.execute(
            """SELECT kn.node_id, kn.type, kn.title,
                      CASE WHEN ne.target_id IS NOT NULL THEN 1 ELSE 0 END as has_contradiction
               FROM knowledge_nodes kn
               LEFT JOIN (
                   SELECT DISTINCT target_id FROM node_edges WHERE relation = 'CONTRADICTS'
               ) ne ON kn.node_id = ne.target_id
               WHERE kn.node_id NOT LIKE 'MEM_CONV%'
                 AND kn.ablation_active = 0
                 AND COALESCE(kn.is_virtual, 0) = 0
                 AND kn.type IN ('LESSON', 'CONTEXT', 'DISCOVERY')
                 AND kn.node_id NOT IN (SELECT basis_point_id FROM reasoning_lines WHERE COALESCE(same_round, 0) = 0)
               ORDER BY kn.created_at DESC
               LIMIT 4"""
        ).fetchall()
        if frontier_rows:
            lines.append("前沿候选（尚未被后续作为 basis 引用，非验证状态）:")
            for r in frontier_rows:
                contradiction_marker = " CONTRADICTS标记" if r['has_contradiction'] else ""
                lines.append(f"  {r['node_id']} <{r['type']}> {r['title']}{contradiction_marker}")
            lines.append("")

        # VOID 摘要（增强版：source 分布 + 签名标签 + 更多样本）
        if void_count > 0:
            src_str = ", ".join(f"{s}:{c}" for s, c in void_source_counts.items()) if void_source_counts else ""
            lines.append(f"[知识空洞] {void_count} VOID ({src_str})")
            for query, sig_label in void_details:
                tag = f" [{sig_label}]" if sig_label else ""
                lines.append(f"  🕳️ {query}{tag}")
            remaining_voids = void_count - len(void_details)
            if remaining_voids > 0:
                lines.append(f"  ... +{remaining_voids} more")
            lines.append("")

        # 饱和信号（虚点密集区域）
        saturation_rows = self._conn.execute(
            """SELECT substr(title, 4) as area_hint, COUNT(*) as count
               FROM knowledge_nodes
               WHERE type = 'CONTEXT' AND title LIKE '饱和:%'
               GROUP BY substr(title, 4)
               HAVING count >= 3
               ORDER BY count DESC
               LIMIT 3"""
        ).fetchall()
        if saturation_rows:
            lines.append("[饱和信号] 知识饱和区域:")
            for r in saturation_rows:
                lines.append(f"  🔬 {r['area_hint']} ({r['count']} 个虚点)")
            lines.append("")

        lines.append("→ get_knowledge_node_content(node_id=...) 获取某节点详情")
        return "\n".join(lines)

    def generate_l1_digest(self, max_nodes: int = 20) -> str:
        """L1 压缩知识摘要（PLS 版）：用引用拓扑代理选出节点。

        替代 generate_map 注入 GP prompt。目标 ~500-800 tokens。
        设计：
          - 内部按入线数降序排，但不向 GP 暴露具体数字
          - 按 type 分组，每组最多 6 个，每个节点一行
          - 附带 VOID 是否存在 + 最近 DISCOVERY
        """
        # 分层采样：每种类型取最近 30 条，避免单一类型垄断候选池
        type_names = self._conn.execute(
            "SELECT DISTINCT type FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' AND ablation_active = 0 AND COALESCE(is_virtual, 0) = 0"
        ).fetchall()
        all_candidates = []
        for tr in type_names:
            t = tr['type']
            type_rows = self._conn.execute(
                """SELECT kn.node_id, kn.type, kn.title, kn.tags,
                          kn.updated_at, kn.last_verified_at, kn.trust_tier,
                          CASE WHEN ne.target_id IS NOT NULL THEN 1 ELSE 0 END as has_contradiction
                   FROM knowledge_nodes kn
                   LEFT JOIN (
                       SELECT DISTINCT target_id FROM node_edges WHERE relation = 'CONTRADICTS'
                   ) ne ON kn.node_id = ne.target_id
                   WHERE kn.node_id NOT LIKE 'MEM_CONV%'
                     AND kn.ablation_active = 0
                     AND COALESCE(kn.is_virtual, 0) = 0
                     AND kn.type = ?
                   ORDER BY kn.updated_at DESC
                   LIMIT 30""", (t,)
            ).fetchall()
            all_candidates.extend(type_rows)

        if not all_candidates:
            return "[L1] 知识库为空"

        # PLS: 批量获取入线数，内部按引用代理排序；输出不暴露具体数字
        all_ids = [dict(r)['node_id'] for r in all_candidates]
        incoming_counts = self._conn.execute(
            """SELECT basis_point_id, COUNT(*) as incoming FROM reasoning_lines
               WHERE basis_point_id IN ({})
                 AND COALESCE(same_round, 0) = 0
               GROUP BY basis_point_id""".format(
                   ','.join('?' * len(all_ids))
               ), all_ids
        ).fetchall()
        inc_map = {r['basis_point_id']: r['incoming'] for r in incoming_counts}

        by_type_all = defaultdict(list)
        for r in all_candidates:
            d = dict(r)
            d['incoming'] = inc_map.get(d['node_id'], 0)
            by_type_all[d['type']].append(d)

        # 按类型分配配额：每种类型至少 1 个，剩余按比例
        for items in by_type_all.values():
            items.sort(key=lambda x: x['incoming'], reverse=True)
        n_types = len(by_type_all)
        remaining = max(0, max_nodes - n_types)
        total_candidates = sum(len(v) for v in by_type_all.values())
        by_type = defaultdict(list)
        for t, items in by_type_all.items():
            quota = 1 + int(remaining * len(items) / max(total_candidates, 1))
            by_type[t] = items[:quota]

        has_void = False
        try:
            vr = self._conn.execute("SELECT 1 FROM void_tasks WHERE status = 'open' LIMIT 1").fetchone()
            has_void = bool(vr)
        except Exception:
            pass

        void_label = "VOID队列存在" if has_void else "VOID队列未观察到开放项"
        lines = [f"[L1 Knowledge · proxy-safe summary · {void_label} · sampled by reference topology]", self._TYPE_SIGNAL_NOTE]

        type_order = ["LESSON", "CONTEXT", "DISCOVERY", "ASSET", "PATTERN", "EPISODE", "ENTITY", "EVENT", "ACTION", "TOOL"]
        seen_types = set()
        for t in type_order:
            if t in by_type:
                seen_types.add(t)
                self._render_l1_group(lines, t, by_type[t])
        for t in sorted(by_type.keys()):
            if t not in seen_types:
                self._render_l1_group(lines, t, by_type[t])

        lines.append("→ search_knowledge_nodes(keywords=[...]) 深入搜索；基础候选=引用代理，非验证证明")
        return "\n".join(lines)

    @staticmethod
    def _render_l1_group(lines: list, ntype: str, nodes: list, max_per_group: int = 6):
        """渲染 L1 单个类型分组（紧凑格式，PLS 版）"""
        shown = nodes[:max_per_group]
        lines.append(f"{ntype}:")
        for d in shown:
            # PLS: 拓扑角色 + CONTRADICTS 标记，不用 usage 胜率或具体入线数字
            inc = d.get('incoming', 0)
            role = "基础候选" if inc >= 2 else "前沿候选"
            contradiction_marker = " CONTRADICTS标记" if d.get('has_contradiction') else ""
            record = f"  {d['node_id']} {d['title'][:40]} ({role}{contradiction_marker})"
            lines.append(record)
        remaining = len(nodes) - len(shown)
        if remaining > 0:
            lines.append("  ... 还有未展开候选")

    # ─── 记忆与对话 ───

    @staticmethod
    def _compact_memory_line(text: str, limit: int = 360) -> str:
        compact = " ".join(str(text or "").split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    @classmethod
    def _compact_memory_user_part(cls, content: str) -> str:
        if str(content or "").lstrip().startswith("AutoSession:"):
            auto_part = content.split("AutoSession:", 1)[1].split("\nGenesis:", 1)[0].strip()
            return cls._compact_memory_line(auto_part, 320)
        if "用户:" not in content:
            return ""
        user_part = content.split("用户:", 1)[1].split("\nGenesis:", 1)[0].strip()
        if user_part.lstrip().startswith("[auto_session]"):
            return cls._compact_memory_line(user_part, 320)
        if "[GENESIS_USER_REQUEST_START]" in user_part:
            actual = user_part.split("[GENESIS_USER_REQUEST_START]", 1)[1]
            directive = ""
            if "## 用户方向" in actual:
                directive = actual.split("## 用户方向", 1)[1]
                for stop in ("\n\n", "\n上一轮工作记忆", "\n上一轮探索前沿", "\n当前信号", "\n当前系统信号"):
                    idx = directive.find(stop)
                    if idx >= 0:
                        directive = directive[:idx]
                        break
            auto_summary = "[auto_session]\nsource: auto_mode_injection\ndirective: " + cls._compact_memory_line(directive or actual, 260)
            return cls._compact_memory_line(auto_summary, 320)
        return cls._compact_memory_line(user_part, 260)

    def get_recent_memory(self, limit: int = 5) -> str:
        """拉取最近 N 条对话记忆 — G 的短期记忆，不压缩"""
        rows = self._conn.execute(
            "SELECT nc.full_content FROM knowledge_nodes kn "
            "JOIN node_contents nc ON kn.node_id = nc.node_id "
            "WHERE kn.node_id LIKE 'MEM_CONV%' "
            "ORDER BY kn.created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        if not rows:
            return ""
        lines = []
        for r in reversed(rows):  # 按时间正序
            content = r['full_content']
            user_summary = self._compact_memory_user_part(content)
            response_summary = self._extract_conversation_topic(content, max_chars=360)
            summary_parts = [part for part in (user_summary, response_summary) if part]
            lines.append("\n  ".join(summary_parts) if summary_parts else self._compact_memory_line(content, 420))
            lines.append("---")
        return "\n".join(lines)

    def get_conversation_digest(self, limit: int = 10) -> str:
        """对话摘要 digest：最近 N 次对话压缩成 1 行/条的话题概览。
        
        给 Multi-G 透镜提供 "似懂非懂" 级别的上下文——
        知道最近在讨论什么话题，但不知道细节，让 cognitive_frame 有素材可发散。
        """
        rows = self._conn.execute(
            "SELECT nc.full_content FROM knowledge_nodes kn "
            "JOIN node_contents nc ON kn.node_id = nc.node_id "
            "WHERE kn.node_id LIKE 'MEM_CONV%' "
            "ORDER BY kn.created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        if not rows:
            return ""
        summaries = []
        for r in reversed(rows):  # 时间正序
            content = r['full_content']
            summary = self._extract_conversation_topic(content)
            if summary:
                summaries.append(f"- {summary}")
        if not summaries:
            return ""
        return "\n".join(summaries)

    @staticmethod
    def _extract_conversation_topic(content: str, max_chars: int = 250) -> str:
        """从单条 MEM_CONV_* 中提取话题摘要（~250字符）。
        
        目标：40-60% 理解度。包含话题标题 + 关键发现/结论。
        """
        gen_part = ""
        if "\nGenesis:" in content:
            segments = content.split("\nGenesis:")
            gen_part = segments[-1].strip()
        
        if not gen_part:
            return ""
        
        # 噪音过滤器
        _noise_prefixes = ("✅", "🟢", "```", "---", "|")
        _transition_prefixes = ("完美", "现在我", "基于Op", "Op已经", "我看到Op", "让我基于", "好的", "我已经")
        
        def _is_noise(line: str) -> bool:
            if not line or len(line) < 6:
                return True
            if any(line.startswith(p) for p in _noise_prefixes):
                return True
            if any(line.startswith(p) for p in _transition_prefixes):
                return True
            return False
        
        def _clean_line(line: str) -> str:
            return line.lstrip("#").strip().strip("*").strip()
        
        # 收集有意义的行（标题 + 内容）
        useful_lines = []
        total_len = 0
        for line in gen_part.split("\n"):
            line = line.strip()
            if _is_noise(line):
                continue
            clean = _clean_line(line)
            if len(clean) < 6:
                continue
            # 截断单行过长内容
            if len(clean) > 80:
                clean = clean[:77] + "..."
            useful_lines.append(clean)
            total_len += len(clean)
            if total_len >= max_chars:
                break
        
        if not useful_lines:
            # fallback：从用户部分提取
            if "用户:" in content:
                user_part = content.split("用户:", 1)[1].split("\nGenesis:", 1)[0].strip()
                if "[GENESIS_USER_REQUEST_START]" in user_part:
                    actual = user_part.split("[GENESIS_USER_REQUEST_START]", 1)[1].strip()
                    if actual:
                        return actual[:max_chars]
            return ""
        
        return "\n  ".join(useful_lines)

    # ─── 节点元数据查询 ───

    def translate_nodes(self, node_ids: List[str]) -> Dict[str, str]:
        """返回 B 面人类翻译"""
        if not node_ids:
            return {}
        placeholders = ','.join('?' * len(node_ids))
        rows = self._conn.execute(
            f"SELECT node_id, human_translation FROM knowledge_nodes WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        ).fetchall()
        return {r['node_id']: r['human_translation'] for r in rows}

    def get_node_briefs(self, node_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not node_ids:
            return {}
        placeholders = ','.join('?' * len(node_ids))
        rows = self._conn.execute(
            f"SELECT node_id, type AS ntype, title, human_translation, tags, prerequisites, resolves, metadata_signature, usage_count, usage_success_count, usage_fail_count, last_verified_at, verification_source, updated_at, trust_tier FROM knowledge_nodes WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        ).fetchall()
        return {r['node_id']: normalize_node_dict(dict(r)) for r in rows}

    # ─── VOID 读取 ───

    def get_recent_voids(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取最近的 VOID 任务（供 digest 展示，最新优先）"""
        rows = self._conn.execute(
            "SELECT void_id, query, status, created_at FROM void_tasks WHERE status = 'open' ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── 心跳 / 守护进程状态 ───

    @staticmethod
    def _parse_heartbeat_timestamp(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _pid_is_alive(pid) -> bool:
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            return False
        if pid_int <= 0:
            return False
        try:
            os.kill(pid_int, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass
        except OSError:
            return False
        # PID 复用防护：验证 /proc/<pid>/cmdline 包含 genesis 相关进程标记
        try:
            with open(f"/proc/{pid_int}/cmdline", "rb") as f:
                cmdline = f.read()
            # 检查是否包含 genesis 或 python 相关标记
            cmdline_str = cmdline.decode("utf-8", errors="replace").lower()
            if any(marker in cmdline_str for marker in ("genesis", "python", "yogg")):
                return True
            return False
        except (FileNotFoundError, PermissionError, OSError):
            return False

    def get_heartbeats(self) -> List[Dict[str, Any]]:
        """读取所有进程心跳状态，含 PID 复用防护。
        
        状态分类:
        - running: 心跳新鲜 + PID 存活且进程身份匹配
        - stale: 心跳过期但 PID 仍存活（进程可能卡死）
        - dead: PID 不存在或进程身份不匹配（已崩溃/已重启）
        - unknown: 无心跳记录或无 PID
        """
        rows = self._conn.execute(
            "SELECT process_name, status, last_heartbeat, last_summary, pid FROM process_heartbeat ORDER BY last_heartbeat DESC"
        ).fetchall()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = []
        for r in rows:
            beat = dict(r)
            heartbeat_at = self._parse_heartbeat_timestamp(beat.get("last_heartbeat"))
            age_seconds = int(max(0, (now - heartbeat_at).total_seconds())) if heartbeat_at else None
            heartbeat_stale = age_seconds is None or age_seconds > self._HEARTBEAT_STALE_AFTER_SECONDS
            pid_alive = self._pid_is_alive(beat.get("pid"))
            # 三级状态分类（替代二元 stale_snapshot）
            if not pid_alive:
                effective_status = "dead"
            elif heartbeat_stale:
                effective_status = "stale"
            else:
                effective_status = "running"
            beat["heartbeat_age_seconds"] = age_seconds
            beat["heartbeat_stale"] = heartbeat_stale
            beat["pid_alive"] = pid_alive
            beat["effective_status"] = effective_status
            beat["state_signal_kind"] = "heartbeat_snapshot"
            result.append(beat)
        return result

    def get_daemon_status_summary(self) -> str:
        """给 G 的守护进程状态摘要"""
        beats = self.get_heartbeats()
        if not beats:
            return ""
        lines = ["[守护进程状态]"]
        for b in beats:
            ts = b.get("last_heartbeat", "?")
            name = b.get("process_name", "?")
            status = b.get("effective_status") or b.get("status", "?")
            summary = b.get("last_summary", "")
            summary_preview = summary[:80] if summary else ""
            age = b.get("heartbeat_age_seconds")
            age_text = f" age={age}s" if age is not None else ""
            lines.append(f"- {name}: {status}{age_text} (last: {ts}) {summary_preview}")
        return "\n".join(lines)
