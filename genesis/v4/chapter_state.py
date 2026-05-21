"""
Genesis V4 — ChapterState 当前状态锚定层

职责：将当前运行上下文编译为类型化的章节状态，注入 prompt packet。
- 只渲染，不调度、不写库、不替代 PLS
- SourceLane[] -> ChapterState -> renderer -> LLM context packet

设计约束：
- 不直接查询 NodeVault（lane 由上游 collector 提供）
- 不写入 NodeVault
- 不决定任务执行
- 不替代 search_knowledge_nodes 或 PLS surface expansion
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Kill switch ──
import os
_CHAPTER_STATE_ENABLED = os.environ.get("GENESIS_CHAPTER_STATE", "1") not in ("0", "false", "no")


# ═══════════════════════════════════════════════════════════════
#  Data Model
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SourceLane:
    """上游 collector 提供的显式输入通道。Builder 消费 lane，不发现 lane。"""
    id: str
    kind: str          # canon_doc | user_correction | experiment_result | stale_action_candidate | deprecated_direction | chronological_history | diagnostics_snapshot
    text: str
    trust: float       # 0.0-1.0
    recency: str       # current_session | current_docs | stale_or_adversarial | historical
    source_path: str   # file path, runtime artifact path, node id, or conversation marker

    def ref(self, claim: str) -> dict[str, str]:
        return {"source": self.id, "claim": claim}


@dataclass
class ChapterState:
    """当前章节的类型化状态。"""
    canon: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    deprecated: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    stale_actions: list[str] = field(default_factory=list)
    active_question: str = ""
    source_refs: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChapterState":
        return cls(
            canon=_coerce_string_list(data, "canon"),
            evidence=_coerce_string_list(data, "evidence"),
            deprecated=_coerce_string_list(data, "deprecated"),
            boundaries=_coerce_string_list(data, "boundaries"),
            stale_actions=_coerce_string_list(data, "stale_actions"),
            active_question=_coerce_string(data, "active_question"),
            source_refs=_coerce_source_refs(data, "source_refs"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canon": self.canon,
            "evidence": self.evidence,
            "deprecated": self.deprecated,
            "boundaries": self.boundaries,
            "stale_actions": self.stale_actions,
            "active_question": self.active_question,
            "source_refs": self.source_refs,
        }

    @property
    def is_empty(self) -> bool:
        return not any([self.canon, self.evidence, self.deprecated,
                        self.boundaries, self.stale_actions, self.active_question])


def _coerce_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    return str(value).strip()


def _coerce_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip(" \t-") for line in value.splitlines() if line.strip(" \t-")]
    if value is None:
        return []
    return [str(value).strip()]


def _split_lane_text(text: str) -> list[str]:
    return [line.strip(" \t-") for line in str(text or "").splitlines() if line.strip(" \t-")]


def _coerce_source_refs(data: dict[str, Any], key: str) -> list[dict[str, str]]:
    value = data.get(key, [])
    refs = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                source = _coerce_string(item, "source")
                claim = _coerce_string(item, "claim")
                if source or claim:
                    refs.append({"source": source, "claim": claim})
    return refs


# ═══════════════════════════════════════════════════════════════
#  SourceLane Collector（从运行时上下文收集 lanes）
# ═══════════════════════════════════════════════════════════════

class SourceLaneCollector:
    """从 auto_mode 运行时上下文收集 SourceLanes。

    当前支持的 lane 类型：
    - diagnostics_snapshot: PipelineDiagnostics summary
    - stale_action_candidate: 连续重复的 action
    - deprecated_direction: 已标记为废弃的方向
    """

    def __init__(self):
        self._lanes: list[SourceLane] = []

    def add_diagnostics(self, diagnostics_summary: dict[str, Any]) -> None:
        if not diagnostics_summary:
            return
        firing_signals = []
        for name, sig in diagnostics_summary.get("signals", {}).items():
            if sig.get("firing"):
                firing_signals.append(f"{name}: rate={sig.get('rate', 0)}")
        if firing_signals:
            text = "诊断信号触发: " + "; ".join(firing_signals)
        else:
            text = "诊断信号正常，无触发。"
        self._lanes.append(SourceLane(
            id="diagnostics_snapshot",
            kind="diagnostics_snapshot",
            text=text,
            trust=0.9,
            recency="current_session",
            source_path="PipelineDiagnostics.summary()",
        ))

    def add_stale_actions(self, actions: list[str]) -> None:
        if not actions:
            return
        text = "\n".join(f"- {a}" for a in actions)
        self._lanes.append(SourceLane(
            id="stale_action_candidates",
            kind="stale_action_candidate",
            text=text,
            trust=0.7,
            recency="stale_or_adversarial",
            source_path="auto_mode.action_tracker",
        ))

    def add_deprecated_directions(self, directions: list[str]) -> None:
        if not directions:
            return
        text = "\n".join(f"- {d}" for d in directions)
        self._lanes.append(SourceLane(
            id="deprecated_directions",
            kind="deprecated_direction",
            text=text,
            trust=0.85,
            recency="historical",
            source_path="auto_mode.knowledge_state",
        ))

    def add_user_correction(self, correction: str) -> None:
        if not correction:
            return
        self._lanes.append(SourceLane(
            id="user_correction",
            kind="user_correction",
            text=correction,
            trust=1.0,
            recency="current_session",
            source_path="user_input",
        ))

    def add_progress_class(self, progress_class: str, progress_note: str = "") -> None:
        if not progress_class:
            return
        text = f"progress_class={progress_class}"
        if progress_note:
            text += f" note={progress_note}"
        self._lanes.append(SourceLane(
            id="progress_classification",
            kind="diagnostics_snapshot",
            text=text,
            trust=0.8,
            recency="current_session",
            source_path="auto_mode.progress_classifier",
        ))

    def _add_lane_items(self, lane_id: str, kind: str, items: list[str], trust: float, recency: str, source_path: str) -> None:
        cleaned = [str(item).strip() for item in items or [] if str(item).strip()]
        if not cleaned:
            return
        self._lanes.append(SourceLane(
            id=lane_id,
            kind=kind,
            text="\n".join(f"- {item}" for item in cleaned),
            trust=trust,
            recency=recency,
            source_path=source_path,
        ))

    def add_canon(self, items: list[str]) -> None:
        self._add_lane_items("canon", "canon_doc", items, 0.9, "current_docs", "auto_mode.chapter_state")

    def add_evidence(self, items: list[str]) -> None:
        self._add_lane_items("runtime_evidence", "runtime_evidence", items, 0.85, "current_session", "auto_mode.round_log")

    def add_boundaries(self, items: list[str]) -> None:
        self._add_lane_items("boundaries", "boundary", items, 0.9, "current_docs", "auto_mode.chapter_state")

    def add_active_question(self, question: str) -> None:
        text = str(question or "").strip()
        if not text:
            return
        self._lanes.append(SourceLane(
            id="active_question",
            kind="active_question",
            text=text,
            trust=0.9,
            recency="current_session",
            source_path="auto_mode.round_focus",
        ))

    @property
    def lanes(self) -> list[SourceLane]:
        return list(self._lanes)


# ═══════════════════════════════════════════════════════════════
#  ChapterStateBuilder（确定性编译，零 LLM）
# ═══════════════════════════════════════════════════════════════

class ChapterStateBuilder:
    """从 SourceLanes 确定性编译 ChapterState。

    不调用 LLM，不查询 NodeVault，不写入任何存储。
    """

    def build(self, lanes: list[SourceLane]) -> ChapterState:
        if not lanes:
            return ChapterState()

        canon: list[str] = []
        evidence: list[str] = []
        deprecated: list[str] = []
        boundaries: list[str] = []
        stale_actions: list[str] = []
        active_question = ""
        source_refs: list[dict[str, str]] = []

        for lane in lanes:
            if lane.kind in ("canon_doc",):
                canon.extend(_split_lane_text(lane.text))
                source_refs.append(lane.ref("canon source"))
            elif lane.kind == "user_correction":
                boundaries.append(lane.text)
                deprecated.append(lane.text)
                source_refs.append(lane.ref("user correction"))
            elif lane.kind == "deprecated_direction":
                deprecated.extend(_split_lane_text(lane.text))
                source_refs.append(lane.ref("deprecated direction"))
            elif lane.kind == "stale_action_candidate":
                stale_actions.extend(_split_lane_text(lane.text))
                source_refs.append(lane.ref("stale action candidate"))
            elif lane.kind == "runtime_evidence":
                evidence.extend(_split_lane_text(lane.text))
                source_refs.append(lane.ref("runtime evidence"))
            elif lane.kind == "boundary":
                boundaries.extend(_split_lane_text(lane.text))
                source_refs.append(lane.ref("boundary"))
            elif lane.kind == "active_question":
                if not active_question:
                    active_question = lane.text
                source_refs.append(lane.ref("active question"))
            elif lane.kind == "diagnostics_snapshot":
                # 诊断信号作为 evidence 注入（只观测，不命令）
                evidence.append(lane.text)
                source_refs.append(lane.ref("diagnostics snapshot"))

        return ChapterState(
            canon=canon,
            evidence=evidence,
            deprecated=deprecated,
            boundaries=boundaries,
            stale_actions=stale_actions,
            active_question=active_question,
            source_refs=source_refs,
        )


# ═══════════════════════════════════════════════════════════════
#  Renderer（prompt packet 渲染）
# ═══════════════════════════════════════════════════════════════

class ChapterStateRenderer:
    """将 ChapterState 渲染为 prompt packet 文本。

    渲染约束：
    - 区分事实、候选、推断、过期
    - 有长度上限（~800 chars）
    - 不把 operational count 变成 semantic mandate
    """

    MAX_CHARS = 800

    def render(self, state: ChapterState) -> str:
        if state.is_empty:
            return ""

        lines = ["[当前章节状态]"]
        char_budget = self.MAX_CHARS - len(lines[0])

        def _append_section(title: str, items: list[str], prefix: str = "-") -> int:
            nonlocal char_budget
            if not items or char_budget <= 0:
                return 0
            section_lines = [f"{title}:"]
            count = 0
            for item in items:
                line = f"  {prefix} {item}"
                if len(line) + len("\n".join(section_lines)) > char_budget:
                    break
                section_lines.append(line)
                count += 1
            if count > 0:
                lines.extend(section_lines)
                used = len("\n".join(section_lines))
                char_budget -= used
            return count

        _append_section("当前方向 (canon)", state.canon)
        _append_section("证据 (evidence)", state.evidence)
        _append_section("已废弃方向 (deprecated)", state.deprecated, "[X]")
        _append_section("边界 (boundaries)", state.boundaries, "[!]")
        _append_section("过期行动 (stale_actions)", state.stale_actions, "[stale]")

        if state.active_question and char_budget > 0:
            q_line = f"当前问题: {state.active_question}"
            if len(q_line) <= char_budget:
                lines.append(q_line)

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════

def build_chapter_state_packet(
    diagnostics_summary: Optional[dict[str, Any]] = None,
    stale_actions: Optional[list[str]] = None,
    deprecated_directions: Optional[list[str]] = None,
    canon: Optional[list[str]] = None,
    evidence: Optional[list[str]] = None,
    boundaries: Optional[list[str]] = None,
    active_question: str = "",
    user_correction: str = "",
    progress_class: str = "",
    progress_note: str = "",
) -> str:
    """一站式入口：收集 lanes → 编译 state → 渲染 prompt packet。

    如果 kill switch 关闭，返回空字符串。
    """
    if not _CHAPTER_STATE_ENABLED:
        return ""

    collector = SourceLaneCollector()
    if canon:
        collector.add_canon(canon)
    if evidence:
        collector.add_evidence(evidence)
    if boundaries:
        collector.add_boundaries(boundaries)
    if diagnostics_summary:
        collector.add_diagnostics(diagnostics_summary)
    if stale_actions:
        collector.add_stale_actions(stale_actions)
    if deprecated_directions:
        collector.add_deprecated_directions(deprecated_directions)
    if active_question:
        collector.add_active_question(active_question)
    if user_correction:
        collector.add_user_correction(user_correction)
    if progress_class:
        collector.add_progress_class(progress_class, progress_note)

    if not collector.lanes:
        return ""

    builder = ChapterStateBuilder()
    state = builder.build(collector.lanes)

    renderer = ChapterStateRenderer()
    return renderer.render(state)
