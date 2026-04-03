"""
契约测试：DispatchTool

验证：
1. Tool 接口契约（name, description, parameters, to_schema）
2. Schema 结构完整性
3. execute() 拦截防护（应抛 RuntimeError）
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from genesis.tools.dispatch_tool import DispatchTool


def test_tool_name():
    tool = DispatchTool()
    assert tool.name == "dispatch_to_op"


def test_tool_description_nonempty():
    tool = DispatchTool()
    assert len(tool.description) > 20, "Description too short"


def test_parameters_structure():
    tool = DispatchTool()
    params = tool.parameters
    assert params["type"] == "object"
    props = params["properties"]
    assert "op_intent" in props
    assert "instructions" in props
    assert "active_nodes" in props
    assert params["required"] == ["op_intent", "instructions"]


def test_to_schema_structure():
    tool = DispatchTool()
    schema = tool.to_schema()
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "dispatch_to_op"
    assert "description" in fn
    assert "parameters" in fn


def test_execute_raises_runtime_error():
    tool = DispatchTool()
    raised = False
    try:
        asyncio.run(tool.execute(op_intent="test", instructions="test"))
    except RuntimeError as e:
        raised = True
        assert "intercepted" in str(e).lower(), f"Wrong error message: {e}"
    assert raised, "Should have raised RuntimeError"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  ✅ {t.__name__}")
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
