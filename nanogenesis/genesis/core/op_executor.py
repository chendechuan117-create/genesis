"""
Genesis V2 - Op Executor
OpSpec → OpResult

[GENESIS_V2_SPEC.md 核心原则 #1 #5]
- 管道结构化：输入 OpSpec（typed），输出 OpResult（typed）
- 基础设施复用：使用 loop.py (ReAct 引擎) + entropy.py（卡死检测）
- 隔离原则：不传入对话历史，每次 op 全新启动
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from genesis.core.base import Tool
from genesis.core.contracts import OpResult, OpSpec
from genesis.core.loop import AgentLoop
from genesis.core.context import SimpleContextBuilder
from genesis.core.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ─── Virtual System Tools (loop.py 期望存在) ──────────────────────────────────

class _SystemReportFailureTool(Tool):
    """让 LLM 合法地报告失败并退出 op"""

    @property
    def name(self) -> str:
        return "system_report_failure"

    @property
    def description(self) -> str:
        return "Report that the task cannot be completed and explain why."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why the task cannot be completed"
                }
            },
            "required": ["reason"]
        }

    async def execute(self, reason: str = "unknown") -> str:
        return f"[FAILURE_REPORTED] {reason}"


# ─── Op Executor ───────────────────────────────────────────────────────────────

class OpExecutor:
    """
    op 执行单元。

    接收 OpSpec，用隔离的 ToolRegistry + loop.py 执行，返回 OpResult。

    隔离保证（[GENESIS_V2_SPEC.md 禁止行为]）：
    - ToolRegistry 仅包含 spec.tool_ids 指定的工具（不是全部工具）
    - context 不含对话历史
    - system_prompt 仅描述执行任务，不含 Genesis 人格
    """

    def __init__(self, full_registry: ToolRegistry, provider: Any):
        self._full_registry = full_registry
        self.provider = provider

    async def execute(self, spec: OpSpec, step_callback: Any = None) -> OpResult:
        """
        执行单个 op。

        Returns:
            OpResult — 结构化结果，Manager 据此判断成功/失败/重组
        """
        logger.info(
            f"⚙️ OpExecutor: attempt={spec.attempt_number} "
            f"tools={spec.tool_ids} objective='{spec.objective[:60]}'"
        )

        isolated_registry = self._build_isolated_registry(spec.tool_ids)
        context = self._build_isolated_context()
        instruction = self._format_instruction(spec)

        loop = AgentLoop(
            tools=isolated_registry,
            context=context,
            provider=self.provider,
            max_iterations=spec.max_iterations,
        )

        tool_outputs: List[Dict[str, Any]] = []

        async def _step_callback(step_type: str, data: Any) -> None:
            if step_type == "tool":
                tool_outputs.append({
                    "tool": data.get("name"),
                    "args": data.get("args"),
                    "result": None,
                })
            elif step_type == "tool_result":
                # Back-fill the result into the last matching entry
                name = data.get("name")
                for entry in reversed(tool_outputs):
                    if entry["tool"] == name and entry["result"] is None:
                        entry["result"] = data.get("result")
                        break
            if step_callback is not None:
                import asyncio
                if asyncio.iscoroutinefunction(step_callback):
                    await step_callback(step_type, data)
                else:
                    step_callback(step_type, data)

        try:
            response, metrics = await loop.run(
                user_input=instruction,
                step_callback=_step_callback,
            )
        except Exception as e:
            logger.error(f"OpExecutor loop crashed: {e}")
            return OpResult(
                success=False,
                matched_expected=False,
                tool_outputs=tool_outputs,
                final_output=None,
                attempt_number=spec.attempt_number,
                error=str(e),
                entropy_triggered=False,
                tokens_used=0,
            )

        return self._parse_result(response, metrics, spec, tool_outputs)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _build_isolated_registry(self, tool_ids: List[str]) -> ToolRegistry:
        """从完整注册表中提取指定工具，加入 system_report_failure。"""
        isolated = ToolRegistry()

        for name in tool_ids:
            tool = self._full_registry.get(name)
            if tool:
                isolated.register(tool)
            else:
                logger.warning(f"Tool '{name}' not found in registry, skipping")

        isolated.register(_SystemReportFailureTool())
        return isolated

    def _build_isolated_context(self) -> SimpleContextBuilder:
        """
        构建无历史的隔离 context。
        使用 SimpleContextBuilder 默认的 build_stateless_messages，
        该方法不包含任何对话历史。
        """
        return SimpleContextBuilder(max_history_messages=0)

    def _format_instruction(self, spec: OpSpec) -> str:
        """将 OpSpec 格式化为执行指令（传入 loop.run 的 user_input）"""
        facts_str = "\n".join(f"  - {f}" for f in spec.context_facts) if spec.context_facts else "  (none)"
        schema_str = json.dumps(spec.output_schema, ensure_ascii=False)

        return (
            f"OBJECTIVE: {spec.objective}\n"
            f"\n"
            f"AVAILABLE TOOLS: {spec.tool_ids}\n"
            f"\n"
            f"CONTEXT FACTS:\n{facts_str}\n"
            f"\n"
            f"STRATEGY: {spec.strategy_hint}\n"
            f"\n"
            f"OUTPUT FORMAT REQUIRED: {schema_str}\n"
            f"SUCCESS CRITERION: {spec.expected_output}\n"
            f"\n"
            f"Use the available tools to complete the objective. "
            f"When done, call system_task_complete with a summary. "
            f"If you cannot complete it, call system_report_failure with a reason."
        )

    def _parse_result(
        self,
        response: str,
        metrics: Any,
        spec: OpSpec,
        tool_outputs: List[Dict],
    ) -> OpResult:
        """将 loop 输出解析为 OpResult。"""
        entropy_triggered = (
            "[STRATEGIC_INTERRUPT]" in response or
            "[STRATEGIC_INTERRUPT_SIGNAL]" in response
        )

        failure_reported = (
            "[FAILURE_REPORTED]" in response or
            "[STATELESS_EXECUTOR_FAILURE]" in response
        )
        success_signal = "[STATELESS_EXECUTOR_SUCCESS]" in response
        loop_success = getattr(metrics, "success", False)

        success = success_signal or (loop_success and not failure_reported and not entropy_triggered)

        error: Optional[str] = None
        if not success:
            if "[STATELESS_EXECUTOR_FAILURE]" in response:
                error = response.split("[STATELESS_EXECUTOR_FAILURE]")[-1].strip()
            elif "[FAILURE_REPORTED]" in response:
                error = response.split("[FAILURE_REPORTED]")[-1].strip()
            elif entropy_triggered:
                error = "Execution loop detected (entropy triggered)"
            elif "[STATELESS_EXECUTOR_ERROR]" in response:
                error = response.split("[STATELESS_EXECUTOR_ERROR]")[-1].strip()
            else:
                error = response[:300] if response else "Unknown error"

        final_output: Any = None
        if success:
            if "[STATELESS_EXECUTOR_SUCCESS]" in response:
                summary = response.split("Summary:")[-1].strip() if "Summary:" in response else response
                final_output = {"summary": summary}
            else:
                final_output = {"summary": response[:500]}

        tokens_used = getattr(metrics, "total_tokens", 0) or 0

        return OpResult(
            success=success,
            matched_expected=success,
            tool_outputs=tool_outputs,
            final_output=final_output,
            attempt_number=spec.attempt_number,
            error=error,
            entropy_triggered=entropy_triggered,
            tokens_used=tokens_used,
        )
