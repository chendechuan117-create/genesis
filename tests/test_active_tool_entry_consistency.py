import asyncio
import json

from genesis.core.base import Tool
from genesis.core.registry import ToolRegistry
from genesis.v4.loop import V4Loop
import genesis.mcp_server as mcp_server


class EchoProbeTool(Tool):
    def __init__(self):
        self.calls = []

    @property
    def name(self) -> str:
        return "echo_probe"

    @property
    def description(self) -> str:
        return "echo probe"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        }

    async def execute(self, message: str) -> str:
        self.calls.append({"message": message})
        return f"OK:{message}"


class DummyProvider:
    async def chat(self, *args, **kwargs):
        raise RuntimeError("not used")


def run(coro):
    return asyncio.run(coro)


def test_registry_and_loop_prepare_share_same_registry_gate_behavior():
    reg = ToolRegistry()
    tool = EchoProbeTool()
    reg.register(tool)
    loop = V4Loop(tools=reg, provider=DummyProvider())

    missing_registry = run(reg.execute("echo_probe", {}))
    missing_loop = run(reg.execute("echo_probe", loop._prepare_c_tool_args("echo_probe", {})))
    success_registry = run(reg.execute("echo_probe", {"message": "hi"}))
    success_loop = run(reg.execute("echo_probe", loop._prepare_c_tool_args("echo_probe", {"message": "hi"})))

    assert missing_registry == "Error: 工具 echo_probe 缺少必填字段: message"
    assert missing_loop == missing_registry
    assert success_registry == "OK:hi"
    assert success_loop == success_registry
    assert tool.calls == [{"message": "hi"}, {"message": "hi"}]


def test_mcp_tools_call_uses_same_registry_gate_after_adapter_patch(monkeypatch):
    reg = ToolRegistry()
    tool = EchoProbeTool()
    reg.register(tool)

    sent = []
    monkeypatch.setattr(mcp_server, "send_response", lambda req_id, result: sent.append((req_id, result)))
    monkeypatch.setattr(mcp_server, "send_error", lambda req_id, code, message: sent.append((req_id, {"error": {"code": code, "message": message}})))

    def registry_adapter(_conn, tool_args):
        name = tool_args.get("__tool_name__", "echo_probe")
        args = tool_args.get("__tool_arguments__", tool_args)
        return run(reg.execute(name, args))

    monkeypatch.setattr(mcp_server, "TOOL_DISPATCH", {"echo_probe": registry_adapter})

    mcp_server.handle_request(None, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "echo_probe", "arguments": {}},
    })
    mcp_server.handle_request(None, {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "echo_probe", "arguments": {"message": "hi"}},
    })

    assert sent[0][1]["content"][0]["text"] == "Error: 工具 echo_probe 缺少必填字段: message"
    assert sent[0][1]["isError"] is True
    assert sent[1][1]["content"][0]["text"] == "OK:hi"
    assert "isError" not in sent[1][1]
    assert tool.calls == [{"message": "hi"}]
