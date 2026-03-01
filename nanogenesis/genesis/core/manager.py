"""
Genesis V2 - Manager (厂长)
核心认知组件：意图解析 → 车间检索 → OpSpec 组装 → op 调度 → 结果处理

[GENESIS_V2_SPEC.md 核心原则 #2]
AI 自主，不硬编码规则 — 厂长用 LLM 决策，不写 if task_type == X 分支。

职责：
  1. 首次启动时从 ToolRegistry 种子工具车间
  2. 查询车间索引（轻量元数据）
  3. LLM 决策：选择工具 / 事实 / 格式 / 策略
  4. 调用 op_assembler 组装 OpSpec
  5. 调度 OpExecutor 执行
  6. 处理 OpResult：成功→学习/返回，失败→重组或熔断
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from genesis.core.contracts import OpResult, OpSpec
from genesis.core.op_assembler import build_op_spec, describe_op_spec
from genesis.core.workshops import WorkshopLesson, WorkshopManager

logger = logging.getLogger(__name__)

# ─── Manager LLM Prompts ────────────────────────────────────────────────────────

_ASSEMBLY_SYSTEM = """\
You are the Manager. Your job is to select resources from workshops to build a task spec.
Output ONLY valid JSON. No explanation, no markdown fences.

Required JSON format:
{
  "tool_ids": ["<tool_name>", ...],
  "fact_ids": ["<fact_id>", ...],
  "format_name": "<format_name>",
  "strategy_hint": "<one sentence>",
  "expected_output": "<success criterion>"
}

Rules:
- tool_ids must be exact names from the TOOLS list
- fact_ids must be exact IDs from the FACTS list
- format_name must be exact name from FORMATS list
- Select only what is necessary. Do not include irrelevant tools.
"""

_ROUTE_SYSTEM = """\
You are the Genesis Manager. Decide: is the user REQUESTING you to take an action, or are they COMMUNICATING something to you?

Output ONLY valid JSON. No explanation, no markdown fences.

{"route": "chat" | "task", "response": "<reply if chat, null if task>"}

- "chat": the user is communicating — sharing information, expressing a preference, asking a question, or making conversation. You respond with language.
- "task": the user is explicitly requesting you to DO something that requires executing a tool.

Key distinction: "I usually use X" is communicating a preference — not a request to launch X.

For "chat": reply naturally in the user's language.
For "task": set response to null.
"""

_EXECUTION_FACTS_SYSTEM = """\
You are a fact extractor. Extract ONLY literal facts directly observed in these tool execution results.
Output ONLY valid JSON. No explanation, no markdown fences.

{"facts": [{"key": "...", "value": "...", "category": "...", "source": "<tool>:<command>"}]}

- key: stable snake_case identifier for this fact
- value: exact string from the tool output, truncated if very long
- category: choose a natural category that fits the fact
- source: which tool and command produced this value

Only include facts specific to this environment, user, or project — not general knowledge the LLM already knows.
If nothing concrete was observed, return {"facts": []}.
"""

_LEARNING_SYSTEM = """\
You are the Manager. Extract reusable knowledge from a completed task for storage in workshops.
Output ONLY valid JSON. No explanation, no markdown fences.

{
  "lessons": [
    {
      "lesson_type": "new_fact|correction|new_pattern",
      "target_workshop": "known_info|metacognition",
      "content": { ... },
      "confidence": 0.0-1.0
    }
  ]
}

- lesson_type / target_workshop must use the exact values above (schema constraint).
- For new_fact: content = {"key": "...", "category": "...", "value": "..."}
- For correction: content = {"key": "...", "value": "..."}
- For new_pattern: content = {"pattern_name": "...", "context_tags": [...], "approach": "..."}
- confidence: your honest estimate of how certain this lesson is (0.0–1.0).
- Only include lessons that are genuinely new or corrective. If nothing, return {"lessons": []}.
"""


# ─── Manager ────────────────────────────────────────────────────────────────────

class Manager:
    """
    厂长 — Genesis V2 核心认知组件。

    Usage:
        manager = Manager(workshops, provider, registry)
        manager.set_executor(op_executor)
        result = await manager.process("帮我整理桌面代码项目")
    """

    MAX_ATTEMPTS = 3

    def __init__(
        self,
        workshops: WorkshopManager,
        provider: Any,
        registry: Any,
    ):
        self.workshops = workshops
        self.provider = provider
        self.registry = registry
        self._executor: Optional[Any] = None

    def set_executor(self, executor: Any) -> None:
        """注入 OpExecutor（Phase 3 后调用）"""
        self._executor = executor

    # ─── Main Entry ──────────────────────────────────────────────────────────────

    async def process(self, user_intent: str, step_callback: Optional[Any] = None, recent_context: str = "") -> Dict[str, Any]:
        """
        用户意图 → 执行 → 结果

        熔断机制：最多 MAX_ATTEMPTS 次重组，超限后上报。
        """
        if self._executor is None:
            raise RuntimeError("OpExecutor not set. Call manager.set_executor() first.")

        self.workshops.seed_from_registry(self.registry)

        # 路由决策：厂长自己判断是否需要工具
        route, direct_response = await self._decide_route(user_intent, recent_context)
        if route == "chat":
            return {
                "success": True,
                "output": {"summary": direct_response},
                "path": "v2_chat",
                "tokens_used": 0,
                "attempts": 0,
            }

        last_error: Optional[str] = None

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            logger.info(f"🏭 Manager: attempt {attempt}/{self.MAX_ATTEMPTS} — '{user_intent[:60]}'")

            spec = await self.assemble_op(user_intent, attempt=attempt, last_error=last_error, recent_context=recent_context)
            logger.info(describe_op_spec(spec))

            result: OpResult = await self._executor.execute(spec, step_callback=step_callback)

            # Capability calibration: always, on success AND failure
            await self._update_capability_calibration(result.tool_outputs, result.success)

            if result.success:
                await self._learn_from_result(user_intent, spec, result)
                return {
                    "success": True,
                    "output": result.final_output,
                    "tokens_used": result.tokens_used,
                    "attempts": attempt,
                }

            last_error = result.error
            logger.warning(
                f"⚠️ op attempt {attempt} failed: {result.error} "
                f"(entropy={'yes' if result.entropy_triggered else 'no'})"
            )

            if result.entropy_triggered:
                logger.error("🔴 Entropy triggered — circuit broken")
                break

        return {
            "success": False,
            "output": None,
            "error": last_error,
            "circuit_broken": True,
            "message": f"已达最大重试次数（{self.MAX_ATTEMPTS}），需要用户介入",
        }

    # ─── Route Decision ───────────────────────────────────────────────────────────

    async def _decide_route(
        self, user_intent: str, recent_context: str = ""
    ) -> tuple:
        """
        厂长路由决策：判断是否需要工具执行。
        无硬编码规则，完全由 LLM 根据意图语义判断。

        Returns:
            ("chat", response_text) — 直接回复，不走工具链
            ("task", None)          — 需要工具，继续 OpSpec 流程
        """
        user_msg = user_intent[:500]
        if recent_context:
            user_msg = f"[Recent context]\n{recent_context[:400]}\n\n[User input]\n{user_intent[:500]}"

        data = await self._call_llm_json(
            system=_ROUTE_SYSTEM,
            user=user_msg,
            fallback={"route": "task", "response": None},
        )
        route = data.get("route", "task")
        response = data.get("response") or ""
        logger.debug(f"🗺️ Route decision: '{user_intent[:40]}' → {route}")
        return route, response

    # ─── Op Assembly ─────────────────────────────────────────────────────────────

    async def _update_capability_calibration(
        self, tool_outputs: List[Dict], op_succeeded: bool
    ) -> None:
        """
        纯统计路径：更新每个工具的执行可靠性数据。
        没有 LLM，只看工具返回内容中有没有错误信号。
        """
        _FAIL_SIGNALS = (
            "error:", "error executing", "exception:", "traceback",
            "timed out", "timeout", "permission denied", "not found",
            "failed:", "[stateless_executor_failure]",
        )
        for entry in tool_outputs:
            tool_name = entry.get("tool")
            if not tool_name:
                continue
            result_str = (entry.get("result") or "").lower()
            # Individual tool call success: no error signals in its own result
            tool_ok = not any(sig in result_str for sig in _FAIL_SIGNALS)
            failure_reason: Optional[str] = None
            if not tool_ok:
                failure_reason = (entry.get("result") or "")[:120]
            try:
                self.workshops.update_capability(tool_name, tool_ok, failure_reason)
            except Exception as e:
                logger.debug(f"Capability update skipped for {tool_name}: {e}")

    async def assemble_op(
        self,
        user_intent: str,
        attempt: int = 1,
        last_error: Optional[str] = None,
        recent_context: str = "",
    ) -> OpSpec:
        """
        查询车间索引 → LLM 选择 → op_assembler 组装 OpSpec
        """
        tool_index = self.workshops.get_tool_index()
        fact_index = self.workshops.get_fact_index()
        formats = self.workshops.list_formats()
        patterns = self.workshops.search_patterns(user_intent, limit=2)
        capability_profile = self.workshops.get_capability_profile()

        user_message = self._build_assembly_prompt(
            user_intent, tool_index, fact_index, formats, patterns,
            attempt, last_error, recent_context, capability_profile
        )

        selection = await self._call_llm_json(
            system=_ASSEMBLY_SYSTEM,
            user=user_message,
            fallback=self._default_selection(tool_index, formats),
        )

        spec = build_op_spec(
            objective=user_intent,
            selection=selection,
            workshops=self.workshops,
            attempt=attempt,
        )
        return spec

    def _build_assembly_prompt(
        self,
        intent: str,
        tool_index: List[Dict],
        fact_index: List[Dict],
        formats: List[Dict],
        patterns: List[Any],
        attempt: int,
        last_error: Optional[str],
        recent_context: str = "",
        capability_profile: Optional[List[Dict]] = None,
    ) -> str:
        tools_str = json.dumps(tool_index, ensure_ascii=False, indent=2)
        facts_str = json.dumps(fact_index, ensure_ascii=False, indent=2)
        formats_str = json.dumps(formats, ensure_ascii=False, indent=2)
        patterns_str = (
            "\n".join(f"- {p.pattern_name}: {p.approach}" for p in patterns)
            if patterns else "None"
        )

        parts = [
            f"USER INTENT: {intent}",
            f"",
            f"AVAILABLE TOOLS:\n{tools_str}",
            f"",
            f"AVAILABLE FACTS (metadata only):\n{facts_str}",
            f"",
            f"AVAILABLE OUTPUT FORMATS:\n{formats_str}",
            f"",
            f"RELEVANT PATTERNS:\n{patterns_str}",
        ]

        if capability_profile:
            lines = [
                f"  {p['capability']}: {p['reliability']:.0%} reliability "
                f"({p['successes']}/{p['total_calls']} calls"
                + (f", last failure: {p['common_failure'][:60]}" if p.get('common_failure') else "")
                + ")"
                for p in capability_profile
            ]
            parts += [
                "",
                "TOOL RELIABILITY (from execution history — prefer high-reliability tools):",
                *lines,
            ]

        if recent_context:
            parts += [
                f"",
                f"RECENT CONVERSATION CONTEXT (last few turns):",
                f"{recent_context[:800]}",
                f"Use this to understand what the user already discussed.",
            ]

        if attempt > 1 and last_error:
            parts += [
                f"",
                f"PREVIOUS ATTEMPT FAILED (attempt {attempt - 1}):",
                f"Error: {last_error}",
                f"Adjust your tool/fact selection to avoid this error.",
            ]

        return "\n".join(parts)

    def _default_selection(self, tool_index: List[Dict], formats: List[Dict]) -> Dict:
        """LLM 输出解析失败时的兜底选择：第一个工具 + plain_text 格式"""
        tool_ids = [tool_index[0]["name"]] if tool_index else []
        format_name = formats[0]["format_name"] if formats else "plain_text"
        return {
            "tool_ids": tool_ids,
            "fact_ids": [],
            "format_name": format_name,
            "strategy_hint": "",
            "expected_output": "",
        }

    # ─── Learning ────────────────────────────────────────────────────────────────

    async def _learn_from_result(
        self, intent: str, spec: OpSpec, result: OpResult
    ) -> None:
        """
        从成功的 op 结果中提取知识，写回车间。分两个独立路径：

        路径 A — 执行验证事实（直接写入稳定车间）：
            从 tool_outputs 的字面返回值提取，不做推断。
            来源可信度 = 工具执行结果本身，不依赖 LLM 判断。

        路径 B — LLM 推断 lesson（进待审队列）：
            从任务描述 + 执行摘要中提取策略模式。
            所有结果进 pending_lessons，需人工 approve 后才入库。
        """
        try:
            await self._extract_execution_facts(result.tool_outputs)
        except Exception as e:
            logger.warning(f"Execution fact extraction failed (non-critical): {e}")

        try:
            await self._extract_inference_lessons(intent, spec, result)
        except Exception as e:
            logger.warning(f"Inference lesson extraction failed (non-critical): {e}")

    async def _extract_execution_facts(self, tool_outputs: List[Dict]) -> None:
        """路径 A：从工具执行结果中提取字面事实，直接写入 known_info。"""
        if not tool_outputs:
            return

        # 只传原始 tool_outputs，不传任何推断材料
        tool_records = [
            {"tool": t["tool"], "args": t.get("args"), "result": t.get("result")}
            for t in tool_outputs if t.get("result")
        ]
        if not tool_records:
            return

        data = await self._call_llm_json(
            system=_EXECUTION_FACTS_SYSTEM,
            user=f"TOOL EXECUTION RECORDS:\n{json.dumps(tool_records, ensure_ascii=False, default=str)[:2000]}",
            fallback={"facts": []},
        )

        written = 0
        for f in data.get("facts", []):
            key = f.get("key", "").strip()
            value = f.get("value", "").strip()
            if key and value:
                self.workshops.add_verified_fact(
                    key=key,
                    value=value,
                    category=f.get("category", "execution"),
                    source=f.get("source", "tool_execution"),
                )
                written += 1

        if written:
            logger.info(f"✅ {written} execution-verified fact(s) written directly to known_info")

    async def _extract_inference_lessons(self, intent: str, spec: OpSpec, result: OpResult) -> None:
        """路径 B：LLM 从任务摘要推断策略 lesson，全部进待审队列。"""
        user_message = (
            f"TASK: {intent}\n"
            f"TOOLS USED: {spec.tool_ids}\n"
            f"RESULT: {json.dumps(result.final_output, ensure_ascii=False, default=str)}"
        )

        data = await self._call_llm_json(
            system=_LEARNING_SYSTEM,
            user=user_message,
            fallback={"lessons": []},
        )

        queued = 0
        for raw in data.get("lessons", []):
            try:
                lesson = WorkshopLesson(**raw)
                self.workshops.apply_lesson(lesson)  # always → pending_lessons
                queued += 1
            except Exception as e:
                logger.warning(f"Lesson parse error: {e} — skipped")

        if queued:
            logger.info(f"📥 {queued} inference lesson(s) queued for review")

    # ─── LLM Helper ──────────────────────────────────────────────────────────────

    async def _call_llm_json(
        self,
        system: str,
        user: str,
        fallback: Dict,
    ) -> Dict:
        """
        调用 LLM，期望返回 JSON。解析失败时返回 fallback。
        """
        try:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            response = await self.provider.chat(messages=messages)
            raw = response.content.strip()

            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(
                    line for line in lines
                    if not line.startswith("```")
                ).strip()

            return json.loads(raw)

        except json.JSONDecodeError as e:
            logger.warning(f"Manager LLM returned invalid JSON: {e}. Using fallback.")
            return fallback
        except Exception as e:
            logger.error(f"Manager LLM call failed: {e}. Using fallback.")
            return fallback
