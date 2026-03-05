"""
Genesis V2 - Op Assembler
从 LLM 的选择结果 + 车间内容 → 结构化 OpSpec

纯数据转换，无 LLM 调用，可独立测试。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from genesis.core.contracts import OpSpec
from genesis.core.workshops import WorkshopManager

logger = logging.getLogger(__name__)


def build_op_spec(
    objective: str,
    selection: Dict[str, Any],
    workshops: WorkshopManager,
    attempt: int = 1,
) -> OpSpec:
    """
    将 Manager LLM 的选择 JSON + 车间内容 组装为 OpSpec。

    Args:
        objective:   用户意图或本次 op 的目标描述
        selection:   Manager LLM 输出的 JSON，结构见下方说明
        workshops:   WorkshopManager 实例，用于加载选中条目的完整内容
        attempt:     重组次数（熔断计数）

    Selection JSON 期望结构：
    {
        "tool_ids":       ["shell", "read_file"],   # 工具名称列表
        "fact_ids":       ["abc12345"],             # 已知信息车间条目 ID
        "format_name":    "file_operation",         # 输出格式规范名称
        "strategy_hint":  "先列举再操作",            # 策略提示
        "expected_output": "success=true"           # 成功判断标准
    }

    Returns:
        OpSpec — 结构化的 op 执行指令
    """
    tool_ids: List[str] = selection.get("tool_ids") or []
    fact_ids: List[str] = selection.get("fact_ids") or []
    format_name: str = selection.get("format_name") or "plain_text"
    strategy_hint: str = selection.get("strategy_hint") or ""
    expected_output: str = selection.get("expected_output") or ""

    # 验证 tool_ids（只保留车间中已存在的工具）
    valid_tool_ids: List[str] = []
    for tid in tool_ids:
        entry = workshops.get_tool(tid)
        if entry:
            valid_tool_ids.append(entry.name)
        else:
            logger.warning(f"工具车间中未找到 '{tid}'，已跳过")

    # 加载选中 facts 的完整 value
    context_facts: List[str] = []
    for fid in fact_ids:
        fact = workshops.get_fact(fid)
        if fact:
            context_facts.append(f"{fact.key}: {fact.value}")
        else:
            logger.warning(f"已知信息车间中未找到 ID '{fid}'，已跳过")

    # 加载输出格式规范
    fmt = workshops.get_format(format_name)
    if fmt:
        output_schema = fmt.output_schema
    else:
        logger.warning(f"输出格式车间中未找到 '{format_name}'，使用空 schema")
        output_schema = {}

    spec = OpSpec(
        objective=objective,
        tool_ids=valid_tool_ids,
        context_facts=context_facts,
        output_schema=output_schema,
        strategy_hint=strategy_hint,
        expected_output=expected_output,
        attempt_number=attempt,
    )

    logger.debug(
        f"OpSpec assembled: tools={valid_tool_ids}, "
        f"facts={len(context_facts)}, attempt={attempt}"
    )
    return spec


def describe_op_spec(spec: OpSpec) -> str:
    """返回 OpSpec 的人类可读摘要，用于日志/调试"""
    return (
        f"[OpSpec] attempt={spec.attempt_number}\n"
        f"  objective:   {spec.objective}\n"
        f"  tools:       {spec.tool_ids}\n"
        f"  facts:       {len(spec.context_facts)} items\n"
        f"  format:      {list(spec.output_schema.keys())}\n"
        f"  strategy:    {spec.strategy_hint}\n"
        f"  expected:    {spec.expected_output}"
    )
