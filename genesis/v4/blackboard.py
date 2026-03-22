"""
Genesis Multi-G 黑板模块 (Blackboard)

双轨制共享数据结构：
  A. 证据支撑型: (框架, 证据节点列表, 最小验证动作)
  B. 纯假设型:   (框架, 推理链, 建议搜索方向)

确定性坍缩：基于 NodeVault 已有的信任评分体系，零 LLM 判断。
"""

import re
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─── 信任层权重（与 NodeVault TRUST_TIERS 对齐）───
TIER_WEIGHT = {
    "HUMAN": 1.5,
    "REFLECTION": 1.2,
    "FERMENTED": 1.0,
    "SCAVENGED": 0.6,
    "CONVERSATION": 0.3,
}

# 纯假设型条目的基础权重（与单个中等证据节点 0.5*0.6=0.3 对齐后上浮，
# 使优质假设能与弱证据竞争）
BASE_HYPOTHESIS_WEIGHT = 0.45

# 假设型搜索方向加分：每个具体搜索方向表示透镜发散了认知
HYPOTHESIS_DIRECTION_BONUS = 0.15

# 验证动作具体性加分
SPECIFICITY_BONUS_HIGH = 0.5
SPECIFICITY_BONUS_LOW = 0.1

# 多样性加分
EXCLUSIVE_NODE_BONUS = 0.3    # 每个独占节点的加分
NTYPE_COVERAGE_BONUS = 0.2    # 每多覆盖一种 ntype 的加分

# 收敛度阈值：超过此值则知识库在该领域缺乏多样性
CONVERGENCE_VOID_THRESHOLD = 0.5

# 自然衰竭：连续 N 秒无新条目则停止
EXHAUSTION_TIMEOUT_SECS = 10

# 具体性检测正则：文件路径、shell 命令、测试名等
_SPECIFICITY_PATTERNS = [
    re.compile(r'[/\\][\w\-\.]+\.\w+'),       # 文件路径 e.g. /foo/bar.py
    re.compile(r'`[^`]*(?:test|run|cat|grep|python|node|npm|pip|curl|ls|cd)[^`]*`', re.IGNORECASE),  # 代码块中的命令
    re.compile(r'pytest|unittest|jest|mocha|cargo test', re.IGNORECASE),  # 测试框架关键词
    re.compile(r'(?:^|\s)(?:python|bash|sh|node)\s+\S+', re.MULTILINE),  # 直接命令调用
]


@dataclass
class EvidenceEntry:
    """证据支撑型条目"""
    persona: str
    framework: str
    evidence_node_ids: List[str]
    verification_action: str
    timestamp: float = field(default_factory=time.time)
    
    @property
    def entry_type(self) -> str:
        return "evidence"


@dataclass
class HypothesisEntry:
    """纯假设型条目"""
    persona: str
    framework: str
    reasoning_chain: str
    suggested_search_directions: List[str]
    timestamp: float = field(default_factory=time.time)
    
    @property
    def entry_type(self) -> str:
        return "hypothesis"


BoardEntry = EvidenceEntry | HypothesisEntry


def _check_verification_specificity(action_text: str) -> float:
    """检查验证动作的具体性，返回 bonus 分数"""
    if not action_text or not action_text.strip():
        return 0.0
    for pattern in _SPECIFICITY_PATTERNS:
        if pattern.search(action_text):
            return SPECIFICITY_BONUS_HIGH
    # 有文本但不够具体
    return SPECIFICITY_BONUS_LOW


class Blackboard:
    """
    Multi-G 共享黑板
    
    线程安全说明：asyncio 单线程事件循环天然无锁，
    各透镜协程通过 await 交替写入，不会真正并发写入。
    """
    
    # ── Persona 在线学习（进程级累积，跨重启持久化到 SQLite） ──
    # 全局统计：{persona: {"wins": int, "losses": int}}
    _persona_stats: Dict[str, Dict[str, int]] = {}
    # 按 task_kind 细分：{(persona, task_kind): {"wins": int, "losses": int}}
    _persona_task_stats: Dict[str, Dict[str, int]] = {}
    _db_loaded: bool = False
    
    @classmethod
    def load_from_db(cls):
        """启动时从 NodeVault 加载 persona 学习数据，恢复跨重启记忆"""
        if cls._db_loaded:
            return
        try:
            from genesis.v4.manager import NodeVault
            vault = NodeVault()
            global_stats, task_stats = vault.load_persona_stats()
            if global_stats:
                cls._persona_stats.update(global_stats)
            if task_stats:
                cls._persona_task_stats.update(task_stats)
            cls._db_loaded = True
        except Exception as e:
            logger.debug(f"PersonaStats: DB load skipped: {e}")

    @classmethod
    def _persist_to_db(cls):
        """将当前 persona 统计写入 SQLite"""
        try:
            from genesis.v4.manager import NodeVault
            vault = NodeVault()
            vault.save_persona_stats(cls._persona_stats, cls._persona_task_stats)
        except Exception as e:
            logger.debug(f"PersonaStats: DB save skipped: {e}")

    @classmethod
    def record_persona_outcome(cls, personas: List[str], success: bool, task_kind: str = ""):
        """Arena 反馈后调用：记录参与本次任务的 persona 的胜负，并持久化"""
        for p in personas:
            if p not in cls._persona_stats:
                cls._persona_stats[p] = {"wins": 0, "losses": 0}
            if success:
                cls._persona_stats[p]["wins"] += 1
            else:
                cls._persona_stats[p]["losses"] += 1
            # 按 task_kind 细分统计（用于动态激活映射）
            if task_kind:
                tk_key = f"{p}:{task_kind}"
                if tk_key not in cls._persona_task_stats:
                    cls._persona_task_stats[tk_key] = {"wins": 0, "losses": 0}
                if success:
                    cls._persona_task_stats[tk_key]["wins"] += 1
                else:
                    cls._persona_task_stats[tk_key]["losses"] += 1
        cls._persist_to_db()
    
    @classmethod
    def get_persona_multiplier(cls, persona: str) -> float:
        """基于历史胜率计算 persona 的评分乘数。
        
        - 无数据: 1.0（中性）
        - 胜率高: 最高 1.3（+30% 分数放大）
        - 胜率低: 最低 0.7（-30% 分数衰减）
        - 使用 Laplace 平滑避免小样本偏差（+1 伪样本）
        """
        stats = cls._persona_stats.get(persona)
        if not stats:
            return 1.0
        wins = stats["wins"]
        losses = stats["losses"]
        n = wins + losses
        if n == 0:
            return 1.0
        # Laplace 平滑胜率
        win_rate = (wins + 1) / (n + 2)
        # 线性映射 [0, 1] → [0.7, 1.3]
        return 0.7 + 0.6 * win_rate

    @classmethod
    def get_persona_win_rate(cls, persona: str, task_kind: str = "") -> Optional[float]:
        """获取 persona 在指定 task_kind 上的 Laplace 平滑胜率（无数据返回 None）"""
        if task_kind:
            stats = cls._persona_task_stats.get(f"{persona}:{task_kind}")
        else:
            stats = cls._persona_stats.get(persona)
        if not stats:
            return None
        n = stats["wins"] + stats["losses"]
        if n == 0:
            return None
        return (stats["wins"] + 1) / (n + 2)

    _PERSONA_DEMOTION_THRESHOLD = 0.3   # 胜率低于此值考虑淘汰
    _PERSONA_MIN_SAMPLES = 5            # 最少样本数才触发淘汰

    @classmethod
    def suggest_persona_swap(cls, base_personas: List[str], task_kind: str, all_personas: List[str]) -> List[str]:
        """基于 task_kind 胜率，淘汰表现差的 persona 并用高胜率候补替换。
        
        规则：
        - 至少保留 2 个原始 persona（不全部淘汰，保底多样性）
        - 只在样本数 >= _PERSONA_MIN_SAMPLES 时淘汰
        - 候补从 all_personas 中选胜率最高的未激活 persona
        """
        if not task_kind or not cls._persona_task_stats:
            return base_personas
        
        # 评估每个 base persona 在此 task_kind 上的表现
        demote_candidates = []
        for p in base_personas:
            wr = cls.get_persona_win_rate(p, task_kind)
            stats = cls._persona_task_stats.get(f"{p}:{task_kind}")
            n = (stats["wins"] + stats["losses"]) if stats else 0
            if wr is not None and wr < cls._PERSONA_DEMOTION_THRESHOLD and n >= cls._PERSONA_MIN_SAMPLES:
                demote_candidates.append(p)
        
        # 保底：不淘汰超过 base 的 1/3（至少保留 2 个）
        max_demotions = max(0, len(base_personas) - 2)
        demote_candidates = demote_candidates[:max_demotions]
        
        if not demote_candidates:
            return base_personas
        
        # 寻找候补：在 all_personas 中不在 base 里的，按该 task_kind 胜率排序
        current_set = set(base_personas)
        candidates = []
        for p in all_personas:
            if p in current_set:
                continue
            wr = cls.get_persona_win_rate(p, task_kind)
            if wr is not None:
                candidates.append((p, wr))
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 执行替换
        result = [p for p in base_personas if p not in demote_candidates]
        for p, wr in candidates:
            if len(result) >= len(base_personas):
                break
            result.append(p)
            logger.info(f"Persona swap: demoted from {task_kind}, promoted {p} (wr={wr:.3f})")
        
        # 如果候补不够，保留被淘汰的（宁可用差的也不减少数量）
        for p in demote_candidates:
            if len(result) >= len(base_personas):
                break
            result.append(p)
        
        if result != base_personas:
            logger.info(f"Persona dynamic map: {task_kind} {base_personas} → {result}")
        
        return result
    
    @classmethod
    def get_persona_stats(cls) -> Dict[str, Any]:
        """供 heartbeat / 外部监控获取 persona 表现"""
        result = {}
        for p, stats in cls._persona_stats.items():
            n = stats["wins"] + stats["losses"]
            win_rate = (stats["wins"] + 1) / (n + 2) if n > 0 else None
            result[p] = {"wins": stats["wins"], "losses": stats["losses"], "win_rate": round(win_rate, 3) if win_rate is not None else None}
        return result
    
    def __init__(self):
        self.entries: List[BoardEntry] = []
        self._last_entry_time: float = time.time()
        self._search_voids: List[Dict[str, Any]] = []
    
    def add_evidence(
        self,
        persona: str,
        framework: str,
        evidence_node_ids: List[str],
        verification_action: str = ""
    ) -> EvidenceEntry:
        """添加证据支撑型条目"""
        entry = EvidenceEntry(
            persona=persona,
            framework=framework,
            evidence_node_ids=evidence_node_ids,
            verification_action=verification_action
        )
        self.entries.append(entry)
        self._last_entry_time = time.time()
        logger.info(f"Blackboard: +evidence from {persona}, nodes={evidence_node_ids}, action={verification_action[:60]}")
        return entry
    
    def add_hypothesis(
        self,
        persona: str,
        framework: str,
        reasoning_chain: str,
        suggested_search_directions: List[str] = None
    ) -> HypothesisEntry:
        """添加纯假设型条目"""
        entry = HypothesisEntry(
            persona=persona,
            framework=framework,
            reasoning_chain=reasoning_chain,
            suggested_search_directions=suggested_search_directions or []
        )
        self.entries.append(entry)
        self._last_entry_time = time.time()
        logger.info(f"Blackboard: +hypothesis from {persona}, directions={entry.suggested_search_directions}")
        return entry
    
    def record_search_void(self, persona: str, query: str, signature: Optional[Dict] = None):
        """记录搜索空洞（透镜搜索返回空结果）"""
        self._search_voids.append({
            "persona": persona,
            "query": query,
            "signature": signature,
            "timestamp": time.time()
        })
        logger.debug(f"Blackboard: search void from {persona}: {query}")
    
    def is_exhausted(self, timeout_secs: float = EXHAUSTION_TIMEOUT_SECS) -> bool:
        """检查是否自然衰竭（无新条目超过指定时间）"""
        return (time.time() - self._last_entry_time) > timeout_secs
    
    @property
    def entry_count(self) -> int:
        return len(self.entries)
    
    @property
    def search_voids(self) -> List[Dict[str, Any]]:
        return self._search_voids
    
    def get_all_suggested_search_directions(self) -> List[str]:
        """从所有假设型条目中收集建议搜索方向"""
        directions = []
        for entry in self.entries:
            if isinstance(entry, HypothesisEntry):
                directions.extend(entry.suggested_search_directions)
        return directions
    
    def collapse(self, vault) -> List[Dict[str, Any]]:
        """
        确定性坡缩：对所有条目评分并排序。
        
        评分维度：
        1. 基础分：节点 confidence × tier_weight + 验证动作具体性
        2. 多样性加分：独占节点(别的透镜没引用) + ntype 覆盖广度
        3. 收敛度感知：全局收敛过高时自动记录软空洞
        
        返回 [{"entry": BoardEntry, "score": float, "detail": str}, ...] 按分数降序。
        """
        if not self.entries:
            return []
        
        # ── 预计算全局节点引用统计（用于多样性加分）──
        from collections import Counter
        global_node_refs = Counter()
        for entry in self.entries:
            if isinstance(entry, EvidenceEntry) and entry.evidence_node_ids:
                global_node_refs.update(entry.evidence_node_ids)
        
        scored = []
        
        for entry in self.entries:
            if isinstance(entry, EvidenceEntry):
                score, detail = self._score_evidence(entry, vault, global_node_refs)
            else:
                score, detail = self._score_hypothesis(entry)
            # Persona 在线学习乘数：历史胜率高的 persona 获得评分放大
            persona_mult = self.get_persona_multiplier(entry.persona)
            if persona_mult != 1.0:
                detail += f" × persona={persona_mult:.2f}"
                score *= persona_mult
            scored.append({
                "entry": entry,
                "score": score,
                "detail": detail
            })
        
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        # ── 人格多样性重排：确保不同认知视角进入 top-K ──
        scored = self._diversity_rerank(scored)
        
        # ── 收敛度感知：检测知识库多样性不足 ──
        total_refs = sum(global_node_refs.values())
        unique_nodes = len(global_node_refs)
        if total_refs > 0:
            convergence = 1.0 - unique_nodes / total_refs
            if convergence > CONVERGENCE_VOID_THRESHOLD and len(self.entries) >= 3:
                logger.info(f"Blackboard: high convergence={convergence:.2f} → soft void")
                self._search_voids.append({
                    "persona": "_blackboard",
                    "query": f"知识库多样性不足(convergence={convergence:.2f}, {unique_nodes}独立/{total_refs}总引用)",
                    "source": "convergence_detection"
                })
        
        if scored:
            winner = scored[0]
            logger.info(
                f"Blackboard collapse: winner={winner['entry'].persona} "
                f"score={winner['score']:.3f} ({winner['detail']})"
            )
        
        return scored
    
    def _score_evidence(self, entry: EvidenceEntry, vault, global_node_refs=None) -> tuple[float, str]:
        """对证据支撑型条目评分（含多样性加分）"""
        evidence_score = 0.0
        node_details = []
        ntypes_seen = set()
        exclusive_count = 0
        
        if entry.evidence_node_ids:
            briefs = vault.get_node_briefs(entry.evidence_node_ids)
            for nid in entry.evidence_node_ids:
                brief = briefs.get(nid)
                if not brief:
                    continue
                conf = brief.get("confidence_score") or 0.5
                tier = brief.get("trust_tier") or "SCAVENGED"
                weight = TIER_WEIGHT.get(tier, 0.6)
                node_score = conf * weight
                evidence_score += node_score
                node_details.append(f"{nid}({conf:.2f}*{weight})")
                ntypes_seen.add((brief.get("type") or "UNKNOWN").upper())
                # 独占节点：只被这一个透镜引用
                if global_node_refs and global_node_refs.get(nid, 0) <= 1:
                    exclusive_count += 1
        
        specificity = _check_verification_specificity(entry.verification_action)
        
        # 多样性加分
        diversity_bonus = exclusive_count * EXCLUSIVE_NODE_BONUS
        ntype_bonus = max(0, len(ntypes_seen) - 1) * NTYPE_COVERAGE_BONUS  # 多于1种才加分
        
        total = evidence_score + specificity + diversity_bonus + ntype_bonus
        
        detail = (f"evidence={evidence_score:.2f}[{','.join(node_details)}]"
                  f" + spec={specificity:.1f}"
                  f" + div={diversity_bonus:.1f}({exclusive_count}独占)"
                  f" + ntype={ntype_bonus:.1f}({len(ntypes_seen)}种)")
        return total, detail
    
    def _score_hypothesis(self, entry: HypothesisEntry) -> tuple[float, str]:
        """对纯假设型条目评分
        
        评分维度：
        - 基础分 0.45（与单个中等证据节点对齐）
        - 推理链质量奖励（长度 + 具体性）
        - 搜索方向数量加分（发散认知的直接证据）
        """
        chain_bonus = min(0.15, len(entry.reasoning_chain) / 1500)
        # 推理链中包含具体性信号（文件路径、命令等）额外加分
        chain_specificity = _check_verification_specificity(entry.reasoning_chain)
        # 每个搜索方向 = 认知发散的直接证据
        direction_bonus = min(0.45, len(entry.suggested_search_directions) * HYPOTHESIS_DIRECTION_BONUS)
        total = BASE_HYPOTHESIS_WEIGHT + chain_bonus + chain_specificity + direction_bonus
        detail = (f"hyp_base={BASE_HYPOTHESIS_WEIGHT}"
                  f" + chain={chain_bonus:.3f}"
                  f" + spec={chain_specificity:.1f}"
                  f" + dirs={direction_bonus:.2f}({len(entry.suggested_search_directions)}个)")
        return total, detail
    
    @staticmethod
    def _diversity_rerank(scored: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """人格多样性重排：确保 top-K 中不同 persona 都有代表。
        
        算法：贪心选择。依次从 scored 中取最高分条目，但如果该 persona
        已在 top-K 中出现过，则降低其优先级（跳过，放到末尾）。
        这不改变总数，只改变排列顺序。
        """
        if len(scored) <= top_k:
            return scored
        
        reranked = []
        remaining = list(scored)
        seen_personas = set()
        
        # 第一轮：每个 persona 取最高分的一条
        for item in list(remaining):
            persona = item["entry"].persona
            if persona not in seen_personas:
                seen_personas.add(persona)
                reranked.append(item)
                remaining.remove(item)
                if len(reranked) >= top_k:
                    break
        
        # 第二轮：如果 top-K 还没满（persona 数 < top_k），按原始分数填充
        for item in remaining:
            reranked.append(item)
        
        return reranked

    def render_for_g(self, collapse_results: List[Dict[str, Any]] = None, top_k: int = 5) -> str:
        """将黑板内容渲染为 G 可读的文本摘要。
        
        如果提供了 collapse_results，只渲染 top-K 条目（避免垃圾注入 G 上下文）。
        未提供时渲染全部（向后兼容）。
        """
        if collapse_results is not None:
            render_entries = [item["entry"] for item in collapse_results[:top_k]]
        else:
            render_entries = self.entries
        
        if not render_entries:
            return "[黑板为空]"
        
        total = len(self.entries)
        shown = len(render_entries)
        header = f"[透镜侦察黑板] 共 {total} 条条目" + (f"，展示 top-{shown}：" if shown < total else "：")
        lines = [header]
        
        for i, entry in enumerate(render_entries, 1):
            if isinstance(entry, EvidenceEntry):
                nodes_str = ", ".join(entry.evidence_node_ids) if entry.evidence_node_ids else "无"
                action_preview = (entry.verification_action[:80] + "...") if len(entry.verification_action) > 80 else entry.verification_action
                lines.append(
                    f"{i}. [{entry.persona}] (证据型) 框架: {entry.framework}\n"
                    f"   证据节点: {nodes_str}\n"
                    f"   验证动作: {action_preview or '未提供'}"
                )
            else:
                dirs = ", ".join(entry.suggested_search_directions) if entry.suggested_search_directions else "无"
                lines.append(
                    f"{i}. [{entry.persona}] (假设型) 框架: {entry.framework}\n"
                    f"   推理链: {entry.reasoning_chain[:120]}{'...' if len(entry.reasoning_chain) > 120 else ''}\n"
                    f"   建议搜索: {dirs}"
                )
        
        return "\n".join(lines)
    
    def render_voids_for_c(self) -> str:
        """将搜索空洞渲染为 C-Process 可读的文本"""
        all_voids = list(self._search_voids)
        # 追加假设型条目的建议搜索方向
        for entry in self.entries:
            if isinstance(entry, HypothesisEntry) and entry.suggested_search_directions:
                for d in entry.suggested_search_directions:
                    all_voids.append({
                        "persona": entry.persona,
                        "query": d,
                        "source": "hypothesis_suggestion"
                    })
        
        if not all_voids:
            return ""
        
        lines = [f"[信息空洞报告] 共 {len(all_voids)} 条搜索未命中/建议方向："]
        for v in all_voids:
            persona = v.get("persona", "unknown")
            query = v.get("query", "")
            source = v.get("source", "search_miss")
            lines.append(f"- [{persona}] ({source}) query=\"{query}\"")
        
        return "\n".join(lines)
