"""
AdaptiveLearner v2 — LLM 驱动的自反思学习器
=============================================
核心转变：
  v1: 硬编码关键词 + 固定 delta → 给风格参数打分
  v2: 存储原始交互 → 每 N 次触发 LLM 自反思 → 生成 cognitive_insights

没有硬编码的关键词、阈值或调整幅度。
所有规律由 LLM 自身从交互历史中归纳，写入 cognitive_insights。
cognitive_insights 直接注入 system_prompt，形成行为指导。

使用方式：
  learner = AdaptiveLearner(storage_path="...", reflection_interval=5)
  
  # 记录一次交互（同步，轻量）
  learner.observe_interaction(user_message, assistant_response, user_reaction)
  
  # 每 N 次交互后，外部调用触发异步反思（需传入 LLM chat 函数）
  await learner.trigger_reflection(llm_chat_fn=cognition.chat)
  
  # 生成注入 system_prompt 的 insight 段落
  prompt_addon = learner.generate_adaptive_prompt()
"""

import json
import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveState:
    """
    精简后的自适应状态。
    不再维护打分参数，只保留：
      - 原始交互计数
      - LLM 自反思生成的 cognitive_insights
    """
    total_interactions: int = 0
    last_reflection_at: int = 0         # 上次反思时的 interaction 数量
    cognitive_insights: List[str] = field(default_factory=list)

    # 向后兼容：保留旧字段（不再使用，但避免加载旧 JSON 报错）
    prefers_concise: float = 0.5
    prefers_technical: float = 0.5
    prefers_proactive: float = 0.5
    uses_emoji: float = 0.0
    message_length_avg: float = 50.0
    formality: float = 0.5
    positive_signals: int = 0
    negative_signals: int = 0
    confidence: float = 0.0


class AdaptiveLearner:
    """
    LLM 驱动的自适应学习器。

    参数：
      storage_path        : JSON 状态文件路径
      reflection_interval : 每隔多少次交互触发一次 LLM 反思
      max_insights        : cognitive_insights 最大条数（FIFO 淘汰）
      history_window      : 每次反思参考最近 N 条原始交互
    """

    def __init__(
        self,
        storage_path: str = "./data/adaptive_learning.json",
        reflection_interval: int = 5,
        max_insights: int = 12,
        history_window: int = 10,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.reflection_interval = reflection_interval
        self.max_insights = max_insights
        self.history_window = history_window

        self.state = self._load()
        self.interaction_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe_interaction(
        self,
        user_message: str,
        assistant_response: str,
        user_reaction: Optional[str] = None,
    ) -> None:
        """
        记录一次交互（同步，轻量，无 LLM 调用）。
        仅存储原始数据，不做任何硬编码分析。
        """
        self.interaction_history.append({
            "timestamp": datetime.now().isoformat(),
            "user": user_message[:500],           # 截断防止过长
            "assistant": assistant_response[:500],
            "reaction": (user_reaction or "")[:200],
        })
        self.state.total_interactions += 1
        self._save()

    def should_reflect(self) -> bool:
        """判断是否到了触发 LLM 反思的时机"""
        due = self.state.total_interactions - self.state.last_reflection_at
        return due >= self.reflection_interval and len(self.interaction_history) >= 2

    async def trigger_reflection(
        self,
        llm_chat_fn: Callable[[List[Dict]], Awaitable[Any]],
    ) -> None:
        """
        触发 LLM 自反思：
          1. 取最近 N 条交互历史
          2. 构建反思 prompt
          3. 解析 LLM 输出为 insight 列表
          4. 追加到 cognitive_insights (FIFO)

        Args:
            llm_chat_fn: 接受 messages list、返回有 .content 属性的对象的异步函数
                         （与 cognition.chat 接口兼容）
        """
        if not self.should_reflect():
            return

        recent = self.interaction_history[-self.history_window:]
        history_text = self._format_history(recent)

        prompt = (
            f"你刚刚完成了 {len(recent)} 次对话交互，以下是记录：\n\n"
            f"{history_text}\n\n"
            "请从中归纳 3~5 条简洁的规律，涵盖：\n"
            "1. 这个用户的沟通偏好（语气、详细程度、技术深度等）\n"
            "2. 哪些执行方式/工具/策略有效，哪些需要避免\n"
            "3. 任何其他值得记住的行为模式\n\n"
            "格式：每条规律一行，以 - 开头，用中文，简短精炼（不超过 25 字/条）。\n"
            "直接输出规律列表，不要有前言或解释。"
        )

        try:
            resp = await llm_chat_fn([{"role": "user", "content": prompt}])
            raw = resp.content.strip() if resp else ""
            insights = self._parse_insights(raw)

            for insight in insights:
                self.add_cognitive_insight(insight)

            self.state.last_reflection_at = self.state.total_interactions
            self._save()
            logger.info(f"🧠 AdaptiveLearner 反思完成，新增 {len(insights)} 条 insight (共 {len(self.state.cognitive_insights)} 条)")

        except Exception as e:
            logger.warning(f"AdaptiveLearner 反思失败（跳过）: {e}")

    async def trigger_anchor_reflection(
        self,
        llm_chat_fn: Callable[[List[Dict]], Awaitable[Any]],
        decisions: List[Dict],
    ) -> None:
        """
        深度锚点反思 — 仅在锚点事件（回溯、失败）触发。
        
        两个维度：
          1. 认知原理提炼：从成功/失败对比提炼域无关的锚点选择原理（乘法）
          2. 工具效能审计：计算每个工具的成功率，标记高失败率工具（工具箱优化）

        Args:
            llm_chat_fn: 异步 LLM chat 函数
            decisions  : get_recent_decisions() 返回的决策记录列表
        """
        if not decisions:
            return

        # ── 1. 构建决策摘要（用于认知原理提炼）──────────────────────────────
        lines = []
        for d in decisions[:12]:
            outcome_emoji = "✅" if d["outcome"] == "success" else "❌"
            opts = ", ".join(d["anchor_options"][:4]) if d["anchor_options"] else "未记录"
            lines.append(
                f"{outcome_emoji} [{d['problem_type']}] 候选锚点: [{opts}] → 选择: {d['chosen_anchor'][:80]}"
            )
        decisions_text = "\n".join(lines)

        # ── 2. 计算每个工具的成功率（用于工具审计）───────────────────────────
        from collections import defaultdict
        tool_stats: dict = defaultdict(lambda: {"success": 0, "failed": 0, "backtracked": 0})
        for d in decisions:
            anchor = d["chosen_anchor"][:40].strip()
            outcome = d["outcome"]
            if outcome in tool_stats[anchor]:
                tool_stats[anchor][outcome] += 1
        
        # 只保留有足够样本（≥2次）的工具，并计算失败率
        audit_lines = []
        for tool, stats in tool_stats.items():
            total = stats["success"] + stats["failed"] + stats["backtracked"]
            if total < 2:
                continue
            fail_rate = (stats["failed"] + stats["backtracked"]) / total
            bar = "⚠️" if fail_rate > 0.5 else ("🔸" if fail_rate > 0.25 else "✅")
            audit_lines.append(
                f"{bar} [{tool}] 成功:{stats['success']} 失败:{stats['failed']} 回溯:{stats['backtracked']} "
                f"(失败率:{fail_rate:.0%})"
            )
        audit_text = "\n".join(audit_lines) if audit_lines else "（样本量不足，暂无工具审计数据）"

        # ── 3. 认知原理提炼 prompt ─────────────────────────────────────────
        principle_prompt = (
            "以下是我最近的决策记录：\n\n"
            f"{decisions_text}\n\n"
            "请归纳 2~3 条**与具体任务无关**的通用认知原理（关于'如何选择更好起点'的思维规律）。\n"
            "- 不要写'音频用PulseAudio'这种特定解法\n"
            "- 要写'失败锚点通常是从零构建而非寻找已有解'这种普适原理\n"
            "每条以 - 开头，中文，不超过 30 字。直接输出列表。"
        )

        # ── 4. 工具审计 prompt ────────────────────────────────────────────
        audit_prompt = (
            "以下是我各个工具/方法的近期执行成功率统计：\n\n"
            f"{audit_text}\n\n"
            "请基于这份数据，识别 1~2 个最值得关注的问题，用一句话指明：\n"
            "  ① 哪个工具失败率最高，可能需要改写或替换\n"
            "  ② 或者什么类型的锚点选择模式风险最高\n"
            "每条以 - 开头，中文，不超过 30 字。直接输出列表（没有问题则回复'暂无'）。"
        )

        try:
            # 并行两个独立 prompt（都是轻量级调用）
            import asyncio
            principle_task = asyncio.create_task(
                llm_chat_fn([{"role": "user", "content": principle_prompt}])
            )
            audit_task = asyncio.create_task(
                llm_chat_fn([{"role": "user", "content": audit_prompt}])
            )
            principle_resp, audit_resp = await asyncio.gather(principle_task, audit_task)

            # 存入认知原理
            principle_raw = principle_resp.content.strip() if principle_resp else ""
            for insight in self._parse_insights(principle_raw):
                self.add_cognitive_insight(f"[锚点认知] {insight}")

            # 存入工具审计
            audit_raw = audit_resp.content.strip() if audit_resp else ""
            if audit_raw and audit_raw != "暂无":
                for insight in self._parse_insights(audit_raw):
                    self.add_cognitive_insight(f"[工具审计] {insight}")

            self._save()
            logger.info(
                f"🔍 锚点深度反思完成 (共 {len(self.state.cognitive_insights)} 条 insight)"
            )

        except Exception as e:
            logger.warning(f"锚点反思失败（跳过）: {e}")

    def add_cognitive_insight(self, insight: str) -> None:
        """手动添加一条 insight（也可从外部调用，例如 backtrack 触发时）"""

        insight = insight.strip()
        if not insight or insight in self.state.cognitive_insights:
            return
        self.state.cognitive_insights.append(insight)
        if len(self.state.cognitive_insights) > self.max_insights:
            self.state.cognitive_insights.pop(0)  # FIFO 淘汰最旧的
        self._save()

    def generate_adaptive_prompt(self) -> str:
        """
        生成注入 system_prompt 的自适应段落。
        只提炼 cognitive_insights，不再有任何评分或硬编码表达。
        如果没有 insight，返回空字符串（不影响现有 prompt）。
        """
        insights = self.state.cognitive_insights
        if not insights:
            return ""

        lines = ["", "【📖 从历史交互归纳的行为规律（自动学习）】"]
        for insight in insights[-8:]:   # 只用最近 8 条，避免过长
            lines.append(f"- {insight}")
        lines.append("")
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """返回当前学习状态（调试用）"""
        return {
            "total_interactions": self.state.total_interactions,
            "last_reflection_at": self.state.last_reflection_at,
            "insight_count": len(self.state.cognitive_insights),
            "insights": self.state.cognitive_insights,
            "next_reflection_in": max(
                0, self.reflection_interval - (
                    self.state.total_interactions - self.state.last_reflection_at
                )
            ),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _format_history(self, interactions: List[Dict]) -> str:
        lines = []
        for i, item in enumerate(interactions, 1):
            lines.append(f"[{i}] 用户: {item.get('user', '')}")
            lines.append(f"    Genesis: {item.get('assistant', '')}")
            if item.get("reaction"):
                lines.append(f"    用户反应: {item['reaction']}")
        return "\n".join(lines)

    def _parse_insights(self, raw: str) -> List[str]:
        """从 LLM 输出中提取以 - 开头的 insight 行"""
        insights = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("-"):
                clean = line.lstrip("-").strip()
                if clean and len(clean) > 3:
                    insights.append(clean)
        return insights[:6]  # 最多取 6 条防止过载

    def _save(self) -> None:
        from dataclasses import asdict
        data = {
            "state": asdict(self.state),
            "last_updated": datetime.now().isoformat(),
        }
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"AdaptiveLearner 保存失败: {e}")

    def _load(self) -> AdaptiveState:
        if not self.storage_path.exists():
            return AdaptiveState()
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 兼容旧格式（v1 存的是 pattern 字段）
            raw = data.get("state") or data.get("pattern") or {}
            # 过滤掉 AdaptiveState 不认识的字段，防止 __init__ 报错
            valid_fields = AdaptiveState.__dataclass_fields__.keys()
            filtered = {k: v for k, v in raw.items() if k in valid_fields}
            return AdaptiveState(**filtered)
        except Exception as e:
            logger.warning(f"AdaptiveLearner 加载失败，重置: {e}")
            return AdaptiveState()
