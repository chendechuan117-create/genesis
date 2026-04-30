#!/usr/bin/env python3
"""Verify PLS V2 deployment on Yogg — run AFTER tar extract."""
import sys

errors = []

# 1. Core infrastructure
try:
    from genesis.core.base import Tool
    assert hasattr(Tool, "is_concurrency_safe"), "Tool.is_concurrency_safe missing"
    print("OK  Tool.is_concurrency_safe")
except Exception as e:
    errors.append(f"core.base: {e}")
    print(f"FAIL core.base: {e}")

try:
    from genesis.core.registry import ToolRegistry
    assert hasattr(ToolRegistry, "is_concurrency_safe"), "ToolRegistry.is_concurrency_safe missing"
    print("OK  ToolRegistry.is_concurrency_safe")
except Exception as e:
    errors.append(f"core.registry: {e}")
    print(f"FAIL core.registry: {e}")

# 2. V2 PLS tools
try:
    from genesis.tools.node_tools import RecordPointTool, RecordLineTool, RecordLessonNodeTool
    rp = RecordPointTool()
    rl = RecordLineTool()
    assert rp.name == "record_point", f"RecordPointTool.name={rp.name}"
    assert rl.name == "record_line", f"RecordLineTool.name={rl.name}"
    print(f"OK  RecordPointTool.name={rp.name}")
    print(f"OK  RecordLineTool.name={rl.name}")
except Exception as e:
    errors.append(f"node_tools V2: {e}")
    print(f"FAIL node_tools V2: {e}")

# 3. Manager PLS methods
try:
    from genesis.v4.manager import NodeVault
    assert hasattr(NodeVault, "_ensure_concept_seeds"), "NodeVault._ensure_concept_seeds missing"
    assert hasattr(NodeVault, "create_reasoning_line"), "NodeVault.create_reasoning_line missing"
    assert hasattr(NodeVault, "record_node_creation_context"), "NodeVault.record_node_creation_context missing"
    assert hasattr(NodeVault, "get_same_round_ids"), "NodeVault.get_same_round_ids missing"
    print("OK  NodeVault._ensure_concept_seeds")
    print("OK  NodeVault.create_reasoning_line")
    print("OK  NodeVault.record_node_creation_context")
    print("OK  NodeVault.get_same_round_ids")
except Exception as e:
    errors.append(f"manager: {e}")
    print(f"FAIL manager: {e}")

# 4. Loop
try:
    from genesis.v4.loop import V4Loop
    print("OK  V4Loop import")
except Exception as e:
    errors.append(f"loop: {e}")
    print(f"FAIL loop: {e}")

# 5. C-Phase
try:
    from genesis.v4.c_phase import CPhaseMixin
    print("OK  CPhaseMixin import")
except Exception as e:
    errors.append(f"c_phase: {e}")
    print(f"FAIL c_phase: {e}")

# 6. Full agent creation (tool registration)
try:
    from factory import create_agent
    agent = create_agent()
    tool_names = sorted(agent.tools.list_tools())
    has_rp = "record_point" in tool_names
    has_rl = "record_line" in tool_names
    print(f"OK  create_agent: {len(tool_names)} tools, record_point={has_rp}, record_line={has_rl}")
    if not has_rp:
        errors.append("record_point not registered")
        print("FAIL record_point not in tool list")
    if not has_rl:
        errors.append("record_line not registered")
        print("FAIL record_line not in tool list")
except Exception as e:
    errors.append(f"create_agent: {e}")
    print(f"FAIL create_agent: {e}")

# 7. Scope gate
try:
    from genesis.auto_mode import CRITICAL_SELF_EVOLUTION_FILES
    print(f"OK  CRITICAL_SELF_EVOLUTION_FILES: {len(CRITICAL_SELF_EVOLUTION_FILES)} files")
except Exception as e:
    errors.append(f"scope_gate: {e}")
    print(f"FAIL scope_gate: {e}")

# Summary
print()
if errors:
    print(f"FAILED: {len(errors)} errors")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
