from __future__ import annotations

import asyncio
import json
from pathlib import Path
import pytest
from genesis.core.registry import ToolRegistry
from genesis.v4.loop import V4Loop


class DummyProvider:
    async def chat(self, *args, **kwargs):
        return "mocked chat output"


@pytest.mark.asyncio
async def test_v6_silent_shadow_prediction_flow(tmp_path, monkeypatch):
    # 1. 设置临时 Shadow 日志路径，避免写生产日志
    temp_log_path = tmp_path / "v6_shadow_predictions.jsonl"
    monkeypatch.setattr("genesis.v6.signature_shadow.DEFAULT_LOG_PATH", temp_log_path)

    # 2. 实例化 V4Loop，模拟主思考循环，防止执行真正的外部 LLM 调用
    reg = ToolRegistry()
    loop = V4Loop(tools=reg, provider=DummyProvider())

    async def mock_run_main_loop(user_input, step_callback):
        return "mocked final agent response"

    monkeypatch.setattr(loop, "_run_main_loop", mock_run_main_loop)

    # 3. 运行 loop 触发异步 shadow mode
    user_input = "Need to troubleshoot and debug connection timeout and network failure on debian python runtime"
    response, metrics = await loop.run(user_input)

    # 4. 等待足够时间（异步线程运行完毕）
    for _ in range(30):
        await asyncio.sleep(0.05)
        if temp_log_path.exists():
            break

    # 5. 断言验证
    assert response == "mocked final agent response"
    assert temp_log_path.exists(), "Shadow prediction log was not created!"

    # 6. 读取并解析日志
    with temp_log_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["mode"] == "shadow_only"
    assert record["trace_id"] == loop.trace_id
    assert "predictions" in record
    assert "baseline" in record
    assert "error_kind" in record["predictions"]
    assert "runtime" in record["predictions"]
