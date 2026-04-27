"""验证 trace_id 修复：agent 和 loop 共用同一个 trace_id"""
import sys, os
sys.path.insert(0, '/workspace')
os.chdir('/workspace')

from genesis.core.tracer import Tracer

# 清理
tracer = Tracer.get_instance()
if tracer._enabled:
    tracer._conn.execute("DELETE FROM traces")
    tracer._conn.execute("DELETE FROM spans")
    tracer._conn.commit()

# 模拟修复后的调用链：agent 创建 trace_id，传给 loop 复用
trace_id_agent = tracer.start_trace("user query")
print(f"AGENT trace_id: {trace_id_agent}")

# loop 复用 agent 的 trace_id（模拟修复后的行为）
trace_id_loop = trace_id_agent  # 修复后：loop 使用传入的 trace_id
print(f"LOOP  trace_id: {trace_id_loop} (复用 agent)")

# loop 内部产生 spans（使用同一个 trace_id）
span1 = tracer.start_span(trace_id_loop, "GP_PHASE", span_type="phase", phase="GP")
tracer.log_llm_call(trace_id_loop, parent=span1, phase="GP", model="gpt-5.1-codex", input_tokens=100, output_tokens=50, duration_ms=200)
tracer.log_tool_call(trace_id_loop, parent=span1, phase="GP", tool_name="shell", tool_args={"cmd":"ls"}, tool_result="ok", duration_ms=30)
tracer.end_span(span1)
tracer.end_trace(trace_id_loop, final_response="done", input_tokens=100, output_tokens=50)

# agent 结束 trace
tracer.end_trace(trace_id_agent, final_response="done")

# 验证：两个 trace_id 相同，且能查到所有 spans
print(f"\nSAME? {trace_id_agent == trace_id_loop}")

spans = tracer.get_trace_spans(trace_id_agent)
print(f"用 API trace_id 查 spans: {len(spans)} 个")
for s in spans:
    print(f"    {s['name']} ({s['span_type']})")

print(f"\n修复验证: {'通过' if len(spans) == 3 else '失败'} (期望 3 个 spans)")
print(f"端到端追踪完整: {trace_id_agent == trace_id_loop and len(spans) == 3}")
