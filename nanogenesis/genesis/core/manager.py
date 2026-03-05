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
from typing import Any, Dict, List, Optional, Union

from genesis.core.contracts import OpResult, OpSpec, SensoryPacket, SensoryItem
from genesis.core.op_assembler import build_op_spec, describe_op_spec
from genesis.core.workshops import PatternEntry, WorkshopLesson, WorkshopManager

logger = logging.getLogger(__name__)

# ─── Manager LLM Prompts ────────────────────────────────────────────────────────

_DIMENSION_SYSTEM = """\
Classify this user request into dimensional tags for metadata lookup.
Output ONLY valid JSON. No explanation.

{"scope": "...", "action": "...", "target": "...", "route": "chat|task"}

- scope: local | network | user | project | web | meta
- action: install | query | create | modify | delete | monitor | execute | configure | analyze
- target: software | file | service | data | config | tool | media
- route: "chat" if answerable from knowledge alone, "task" if external action needed (including reading attached files)

Only include dimensions that clearly apply. Omit uncertain ones.
"""

_ASSEMBLY_SYSTEM = """\
You are the Genesis Manager (厂长) — the cognitive core of Genesis, a local AI agent.
You have a digest of your workshops and dimension-matched metadata below.

Think first. You can answer most questions from your own knowledge and the matched facts.
Tools are for tasks that genuinely require external action.

**INPUT SENSORY DATA:**
The user has provided the following inputs (Text + Files).
If files are present (images, audio, code), you MUST select appropriate tools to process them.
- Images: Use `visual` tool (analyze_image).
- Text Files: Use `read_file`.
- Audio: Use `audio_tool` (if available).

Output ONLY valid JSON. No explanation, no markdown fences.

Chat reply — you can fully address this from your own thinking + matched facts:
{"route": "chat", "response": "<reply in user's language>"}

Task delegation — external action genuinely required:
{
  "route": "task",
  "tool_ids": ["<exact tool name from matched tools>", ...],
  "fact_ids": ["<fact key from matched facts>", ...],
  "format_name": "<format name>",
  "strategy_hint": "<one sentence>",
  "expected_output": "<success criterion>"
}

If work needs doing, delegate it now — do not describe planned actions in a chat reply.
"""


_EXECUTION_FACTS_SYSTEM = """\
You are a fact extractor. Extract ONLY durable state changes from tool execution results.
Output ONLY valid JSON. No explanation, no markdown fences.

{"facts": [{"key": "...", "value": "...", "category": "...", "source": "<tool>:<command>"}]}

Durable state changes = things that persist after this session:
- Software installed/removed (package name + version)
- Files created/deleted/modified (path)
- Config changed (what was set to what)
- User accounts/permissions changed

Do NOT extract:
- Transient query results (search results, directory listings, disk usage numbers)
- Information the system already knows (OS name, package manager)
- One-time command output that won't be relevant next time

If no durable state changed, return {"facts": []}.
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

_PACKAGING_SYSTEM = """\
You are the Genesis Manager (厂长). Your worker just returned raw execution results.
Synthesize them into a natural, thoughtful response for the user.

- Address the user's original request directly.
- Extract the most relevant findings; discard noise.
- Add your own analysis and judgment — you are a thinker, not a relay.
- Maintain the conversation's flow and tone.
- Reply in the user's language.
"""

_META_EVAL_SYSTEM = """\
You are the Genesis Manager reflecting on an execution trajectory.
Your task: identify the WRONG ASSUMPTION that led to any detour or failure in the trajectory.

Do not describe what happened. Ask yourself: "Why did I choose that wrong path? What did I assume
that turned out to be false?" The answer is the principle to remember.

Output ONLY valid JSON. No explanation, no markdown fences.

{
  "pattern_name": "...",
  "context_tags": [...],
  "wrong_assumption": "...",
  "approach": "..."
}

- pattern_name: short snake_case identifier for the corrected assumption
- wrong_assumption: what false belief led to the detour (e.g. "assumed n8n is a system package")
- approach: the corrected principle (e.g. "n8n is a Node.js app — check software type before choosing package manager")
- context_tags: when this principle applies
- If no wrong assumption was made (clean execution), return {}
"""

_CHAT_LEARNING_SYSTEM = """\
You are the Genesis Manager. The user just said something in a chat turn (no tool was used).
Extract any user-shared facts worth storing long-term (name, preferences, habits, identity).
Output ONLY valid JSON. No explanation, no markdown fences.

{
  "facts": [
    {"key": "...", "category": "user_profile", "value": "...", "source": "user_stated"}
  ]
}

- Only extract facts the user EXPLICITLY stated about themselves.
- Do not infer or guess. If nothing was shared, return {"facts": []}.
- category must be "user_profile".
"""

_FAILURE_LEARNING_SYSTEM = """\
You are the Genesis Manager. An op just failed. Extract what went wrong as reusable patterns.
Output ONLY valid JSON. No explanation, no markdown fences.

{
  "lessons": [
    {
      "lesson_type": "new_pattern|correction",
      "target_workshop": "metacognition",
      "content": {"pattern_name": "...", "context_tags": [...], "approach": "..."},
      "confidence": 0.0-1.0
    }
  ]
}

- Focus on assembly strategy: wrong tool choice, missing context, bad strategy_hint.
- Do NOT blame the user or external services.
- Only target_workshop: "metacognition" is valid here.
- If no pattern can be extracted, return {"lessons": []}.
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

    async def process(self, user_intent: Union[str, SensoryPacket], step_callback: Optional[Any] = None, recent_context: str = "") -> Dict[str, Any]:
        """
        用户意图 → 执行 → 结果
        Supports both string (legacy) and SensoryPacket (multimodal) inputs.
        """
        if self._executor is None:
            raise RuntimeError("OpExecutor not set. Call manager.set_executor() first.")

        # Normalize input to SensoryPacket if it's a string
        if isinstance(user_intent, str):
            from genesis.core.sensory import SensoryCortex
            # We don't have attachments here, just text
            packet = await SensoryCortex().perceive(text_input=user_intent)
        else:
            packet = user_intent

        text_query = packet.text_content()
        self.workshops.seed_from_registry(self.registry)

        last_error: Optional[str] = None

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            logger.info(f"🏷️ Manager: attempt {attempt}/{self.MAX_ATTEMPTS} — '{text_query[:60]}'")

            result_or_chat = await self.assemble_op(packet, attempt=attempt, last_error=last_error, recent_context=recent_context)

            # 厂长决定直接回复（这是厂长的主观判断）
            if isinstance(result_or_chat, dict) and result_or_chat.get("route") == "chat":
                logger.info(f"💬 Manager chat: '{text_query[:40]}'")
                await self._learn_from_chat(text_query)
                return {
                    "success": True,
                    "output": {"summary": result_or_chat.get("response", "")},
                    "path": "v2_chat",
                    "tokens_used": 0,
                    "attempts": attempt,
                }

            spec = result_or_chat
            logger.info(describe_op_spec(spec))

            result: OpResult = await self._executor.execute(spec, step_callback=step_callback)

            # Capability calibration: always, on success AND failure
            await self._update_capability_calibration(result.tool_outputs, result.success)

            if result.success:
                await self._learn_from_result(text_query, spec, result)
                await self._meta_evaluate(text_query, spec, result)
                await self._optimize_dimensions()
                packaged = await self._package_result(text_query, result, recent_context)
                return {
                    "success": True,
                    "output": {"summary": packaged},
                    "tokens_used": result.tokens_used,
                    "attempts": attempt,
                }

            last_error = result.error
            logger.warning(
                f"⚠️ op attempt {attempt} failed: {result.error} "
                f"(entropy={'yes' if result.entropy_triggered else 'no'})"
            )
            await self._learn_from_failure(text_query, spec, result)
            await self._meta_evaluate(text_query, spec, result)

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

    async def _translate_intent(self, user_intent: str) -> Dict[str, str]:
        """将用户意图翻译为维度地址（轻量 LLM 调用，~200 tokens）。"""
        return await self._call_llm_json(
            system=_DIMENSION_SYSTEM,
            user=user_intent,
            fallback={"scope": "local", "action": "execute", "target": "data", "route": "task"},
        )

    async def assemble_op(
        self,
        packet: SensoryPacket,
        attempt: int = 1,
        last_error: Optional[str] = None,
        recent_context: str = "",
    ) -> Union[Dict, OpSpec]:
        """
        维度翻译 → 按维度查车间 → LLM 组装 OpSpec。
        不再全量扫描索引——只看维度匹配的元数据。
        """
        user_intent = packet.text_content()
        
        # Step 1: 翻译意图为维度地址（轻量）
        dims = await self._translate_intent(user_intent)
        route = dims.pop("route", "task")
        logger.info(f"📐 Dimensions: {dims} (route={route})")

        # Step 2: 按维度查匹配的元数据
        matched_facts = self.workshops.get_by_dimensions("known_info_workshop", dims)
        matched_tools = self.workshops.get_by_dimensions("tool_workshop", dims)
        patterns = self.workshops.search_patterns(user_intent, limit=2)
        formats = self.workshops.list_formats()
        digest = self.workshops.get_digest()

        # Step 3: 组装 assembly prompt（只含匹配结果，不含全量索引）
        user_message = self._build_assembly_prompt(
            packet, matched_facts, matched_tools, formats, patterns,
            attempt, last_error, recent_context, digest
        )

        # 全量工具索引作为 fallback（维度匹配可能漏工具）
        all_tools = self.workshops.get_tool_index()
        selection = await self._call_llm_json(
            system=_ASSEMBLY_SYSTEM,
            user=user_message,
            fallback=self._default_selection(all_tools, formats),
        )

        if selection.get("route") == "chat":
            logger.debug(f"💬 Assembly routed to chat: '{user_intent[:40]}'")
            return selection

        spec = build_op_spec(
            objective=user_intent,
            selection=selection,
            workshops=self.workshops,
            attempt=attempt,
        )
        return spec

    def _build_assembly_prompt(
        self,
        packet: SensoryPacket,
        matched_facts: List[Dict],
        matched_tools: List[Dict],
        formats: List[Dict],
        patterns: List[Any],
        attempt: int,
        last_error: Optional[str],
        recent_context: str = "",
        digest: str = "",
    ) -> str:
        intent = packet.text_content()
        parts = [f"USER INTENT: {intent}", ""]

        # ─── Sensory Data Section ───
        # List all non-text items (files, images, etc)
        attachments = [item for item in packet.items if item.type != 'text']
        if attachments:
            parts.append("ATTACHMENTS (You MUST handle these):")
            for item in attachments:
                meta_str = ", ".join(f"{k}={v}" for k, v in item.metadata.items())
                parts.append(f"- [{item.type.upper()}] {item.content} ({item.mime_type}) {meta_str}")
            parts.append("")

        # 馆藏概览（固定 ~20 行，不随数据量增长）
        if digest:
            parts += [digest, ""]

        if recent_context:
            parts += [
                "RECENT CONVERSATION:",
                f"{recent_context[:2000]}",
                "",
            ]

        # 维度匹配的事实（只有相关的，不是全量）
        if matched_facts:
            facts_lines = [f"  {f['key']}: {str(f.get('value', ''))[:80]}" for f in matched_facts]
            parts += [
                f"MATCHED FACTS ({len(matched_facts)} items):",
                *facts_lines,
                "",
            ]

        if patterns:
            patterns_str = "\n".join(f"  - {p.pattern_name}: {p.approach[:100]}" for p in patterns)
            parts += [
                "STRATEGY PATTERNS:",
                patterns_str,
                "",
            ]

        # 维度匹配的工具 + 全量工具列表（确保不漏）
        if matched_tools:
            tool_names = [t["name"] for t in matched_tools]
            parts.append(f"DIMENSION-MATCHED TOOLS: {tool_names}")

        # 始终提供全量工具列表（作为兜底）
        all_tools = self.workshops.get_tool_index()
        all_names = [t["name"] for t in all_tools]
        parts += [f"ALL AVAILABLE TOOLS: {all_names}", ""]

        parts.append(f"OUTPUT FORMATS: {[f['format_name'] for f in formats]}")

        if attempt > 1 and last_error:
            parts += [
                "",
                f"PREVIOUS ATTEMPT FAILED (attempt {attempt - 1}):",
                f"Error: {last_error}",
            ]

        return "\n".join(parts)

    def _default_selection(self, tool_index: List[Dict], formats: List[Dict]) -> Dict:
        """LLM 输出解析失败时的底而选择：保守地走 task 路径"""
        tool_ids = [tool_index[0]["name"]] if tool_index else []
        format_name = formats[0]["format_name"] if formats else "plain_text"
        return {
            "route": "task",
            "tool_ids": tool_ids,
            "fact_ids": [],
            "format_name": format_name,
            "strategy_hint": "",
            "expected_output": "",
        }

    # ─── Learning ────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_trajectory(tool_outputs: List[Dict]) -> str:
        """将 tool_outputs 格式化为编号步骤序列，供厂长“以史为鉴”。"""
        if not tool_outputs:
            return "(no steps)"
        lines = []
        for i, step in enumerate(tool_outputs, 1):
            tool = step.get("tool", "?")
            args = step.get("args", {})
            result_str = str(step.get("result", ""))[:200]
            # 判断步骤成败与否
            fail_signals = ("error", "fail", "exception", "timeout", "denied", "not found")
            failed = any(s in result_str.lower() for s in fail_signals)
            status = "✗ FAIL" if failed else "✓ OK"
            # 简化 args 展示
            args_brief = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items()) if isinstance(args, dict) else str(args)[:80]
            lines.append(f"Step {i}: {tool}({args_brief}) → {status}: {result_str[:120]}")
        return "\n".join(lines)

    async def _meta_evaluate(
        self, intent: str, spec: OpSpec, result: OpResult
    ) -> None:
        """
        元认知循环——厂长读执行轨迹，从步骤转换中学习。
        只在轨迹有“弯路”时触发（失败重试、多步绕行、entropy）。
        直接写入 metacognition_workshop。
        """
        trajectory = self._format_trajectory(result.tool_outputs)
        step_count = len(result.tool_outputs)

        # 只在有弯路时触发分析
        has_failure = "✗ FAIL" in trajectory
        has_detour = step_count > 3 or spec.attempt_number > 1 or result.entropy_triggered
        if not has_failure and not has_detour:
            return

        try:
            user_message = (
                f"TASK: {intent}\n"
                f"SUCCESS: {result.success}\n"
                f"TRAJECTORY ({step_count} steps):\n{trajectory}"
            )
            data = await self._call_llm_json(
                system=_META_EVAL_SYSTEM,
                user=user_message,
                fallback={},
            )
            pattern_name = data.get("pattern_name", "").strip()
            wrong_assumption = data.get("wrong_assumption", "").strip()
            approach = data.get("approach", "").strip()
            if pattern_name and approach:
                # 把错误假设和修正原则合并存储
                full_approach = f"[错误假设] {wrong_assumption} → [修正] {approach}" if wrong_assumption else approach
                self.workshops.add_pattern(PatternEntry(
                    pattern_name=pattern_name,
                    context_tags=data.get("context_tags", []),
                    approach=full_approach,
                ))
                logger.info(f"🧠 Reflection: '{pattern_name}' — assumption: {wrong_assumption[:60]}")
        except Exception as e:
            logger.warning(f"Meta-evaluation failed (non-critical): {e}")

    async def _optimize_dimensions(self) -> None:
        """
        维度自优化：扫描 known_info 中 dimensions='{}' 的条目，
        用 _CATEGORY_TO_DIMS 回填已知映射，对未知 category 用 LLM 生成新映射。
        """
        from genesis.core.workshops import WorkshopManager
        try:
            with self.workshops._conn() as conn:
                # 找到所有空维度的条目
                rows = conn.execute(
                    "SELECT DISTINCT category FROM known_info_workshop WHERE dimensions = '{}'"
                ).fetchall()

            if not rows:
                return

            unmapped = []
            for r in rows:
                cat = r["category"]
                if cat in self.workshops._CATEGORY_TO_DIMS:
                    # 已知映射，直接回填
                    dims = self.workshops._CATEGORY_TO_DIMS[cat]
                    with self.workshops._conn() as conn:
                        conn.execute(
                            "UPDATE known_info_workshop SET dimensions = ? WHERE category = ? AND dimensions = '{}'",
                            (json.dumps(dims), cat)
                        )
                else:
                    unmapped.append(cat)

            if not unmapped:
                return

            # 对未知 category 用 LLM 建议维度映射
            data = await self._call_llm_json(
                system=(
                    "Assign dimension tags to these metadata categories.\n"
                    "Output ONLY valid JSON: {\"mappings\": {\"category\": {\"scope\": \"...\", \"target\": \"...\"}, ...}}\n"
                    "scope: local|network|user|project|web|meta\n"
                    "target: software|file|service|data|config|tool|media"
                ),
                user=f"Categories to map: {unmapped}",
                fallback={"mappings": {}},
            )

            mappings = data.get("mappings", {})
            with self.workshops._conn() as conn:
                for cat, dims in mappings.items():
                    if isinstance(dims, dict) and cat in unmapped:
                        conn.execute(
                            "UPDATE known_info_workshop SET dimensions = ? WHERE category = ? AND dimensions = '{}'",
                            (json.dumps(dims), cat)
                        )
                        # 更新运行时映射表（扩展"语言"）
                        self.workshops._CATEGORY_TO_DIMS[cat] = dims
                        logger.info(f"📐 Dimension extended: '{cat}' → {dims}")

        except Exception as e:
            logger.debug(f"Dimension optimization skipped: {e}")

    async def _learn_from_chat(self, user_intent: str) -> None:
        """
        用户在 chat 路径分享了信息时，提取并存入 known_info_workshop。
        只提取用户明确陈述的事实（姓名、偏好、习惯），不做推断。
        """
        try:
            data = await self._call_llm_json(
                system=_CHAT_LEARNING_SYSTEM,
                user=f"USER SAID: {user_intent}",
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
                        category=f.get("category", "user_profile"),
                        source="user_stated",
                    )
                    written += 1
            if written:
                logger.info(f"👤 {written} user fact(s) stored from chat turn")
        except Exception as e:
            logger.warning(f"Chat learning failed (non-critical): {e}")

    async def _learn_from_failure(
        self, intent: str, spec: OpSpec, result: OpResult
    ) -> None:
        """
        从失败的 op 中提取组装策略教训，进 pending_lessons。
        执行层客观信号（capability calibration）已在外层处理，
        这里只做 LLM 推断的模式提取。
        """
        try:
            user_message = (
                f"TASK: {intent}\n"
                f"TOOLS CHOSEN: {spec.tool_ids}\n"
                f"STRATEGY HINT: {spec.strategy_hint}\n"
                f"ERROR: {result.error}\n"
                f"ENTROPY TRIGGERED: {result.entropy_triggered}"
            )
            data = await self._call_llm_json(
                system=_FAILURE_LEARNING_SYSTEM,
                user=user_message,
                fallback={"lessons": []},
            )
            queued = 0
            for raw in data.get("lessons", []):
                try:
                    lesson = WorkshopLesson(**raw)
                    self.workshops.apply_lesson(lesson)
                    queued += 1
                except Exception as e:
                    logger.warning(f"Failure lesson parse error: {e} — skipped")
            if queued:
                logger.info(f"📥 {queued} failure lesson(s) queued for review")
        except Exception as e:
            logger.warning(f"Failure learning step failed (non-critical): {e}")

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
        """路径 A：只提取持久化状态变更（安装/删除/配置变更），不提取瞬时查询结果。"""
        if not tool_outputs:
            return

        trajectory = self._format_trajectory(tool_outputs)

        data = await self._call_llm_json(
            system=_EXECUTION_FACTS_SYSTEM,
            user=f"EXECUTION TRAJECTORY:\n{trajectory}",
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
            logger.info(f"✅ {written} durable fact(s) written to known_info")

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

    async def _package_result(
        self, user_intent: str, result: OpResult, recent_context: str = ""
    ) -> str:
        """厂长消化 op 原始结果，输出连贯的对话回复。"""
        raw = str(result.final_output)[:3000]
        user_msg = f"User's request: {user_intent}\n\nRaw execution results:\n{raw}"
        if recent_context:
            user_msg += f"\n\nRecent conversation:\n{recent_context[:1000]}"
        try:
            return await self._call_llm_text(
                system=_PACKAGING_SYSTEM, user=user_msg, fallback=raw
            )
        except Exception as e:
            logger.warning(f"Packaging failed: {e}")
            return raw

    # ─── LLM Helper ────────────────────────────────────────────────────────────

    async def _call_llm_text(
        self, system: str, user: str, fallback: str = ""
    ) -> str:
        """调用 LLM，返回纯文本。失败时返回 fallback。"""
        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
            )
            return response.content.strip()
        except Exception as e:
            logger.error(f"Manager LLM text call failed: {e}")
            return fallback

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
