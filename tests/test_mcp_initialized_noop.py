"""
最小测试：验证 MCP notifications/initialized 为安全 no-op，
且不阻断后续 tools/list 请求。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import genesis.mcp_server as mcp_server


def test_initialized_is_no_op_and_does_not_block_tools_list():
    """
    MCP 客户端在收到 initialize 响应后会发送 notifications/initialized
   （无 id 字段）。服务端必须将其视为安全 no-op，且后续请求正常处理。
    """
    sent = []

    def capture_response(req_id, result):
        sent.append({"id": req_id, "result": result})

    def capture_error(req_id, code, message):
        sent.append({"id": req_id, "error": {"code": code, "message": message}})

    # 暂换输出函数以便断言
    original_send_response = mcp_server.send_response
    original_send_error = mcp_server.send_error
    mcp_server.send_response = capture_response
    mcp_server.send_error = capture_error

    try:
        # 1) initialize 请求（有 id，需响应）
        mcp_server.handle_request(None, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
        })
        assert len(sent) == 1
        assert sent[0]["id"] == 1
        assert sent[0]["result"]["protocolVersion"] == "2024-11-05"
        assert "serverInfo" in sent[0]["result"]

        # 2) notifications/initialized（无 id，必须为 no-op）
        mcp_server.handle_request(None, {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        # 不应产生任何响应（无 id 且方法为通知）
        assert len(sent) == 1, "notifications/initialized 不应触发响应"

        # 3) 后续 tools/list 仍需正常工作
        mcp_server.handle_request(None, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        })
        assert len(sent) == 2
        assert sent[1]["id"] == 2
        assert "tools" in sent[1]["result"]

    finally:
        mcp_server.send_response = original_send_response
        mcp_server.send_error = original_send_error
