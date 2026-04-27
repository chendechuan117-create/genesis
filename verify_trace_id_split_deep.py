import sys, os, sqlite3, json, time
sys.path.insert(0, '/workspace')
os.chdir('/workspace')

from genesis.core.tracer import Tracer

tracer = Tracer.get_instance()
if tracer._enabled:
    tracer._conn.execute("DELETE FROM traces")
    tracer._conn.execute("DELETE FROM spans")
    tracer._conn.commit()

# 模拟完整调用链
trace_id_agent = tracer.start_trace("user query")

# agent 调用 loop.run()，loop 又创建自己的 trace
# 模拟 loop 内部产生 spans
trace_id_loop = tracer.start_trace("user query")
span1 = tracer.start_span(trace_id_loop, "GP_PHASE", span_type="phase", phase="GP")
tracer.log_llm_call(trace_id_loop, parent=span1, phase="GP", model="gpt-5.1-codex", input_tokens=100, output_tokens=50, duration_ms=200)
tracer.log_tool_call(trace_id_loop, parent=span1, phase="GP", tool_name="shell", tool_args={"cmd":"ls"}, tool_result="ok", duration_ms=30)
tracer.end_span(span1)
tracer.end_trace(trace_id_loop, final_response="done", input_tokens=100, output_tokens=50)

# agent 结束自己的 trace
tracer.end_trace(trace_id_agent, final_response="done")

# 查询对比
print("=== AGENT trace ===")
agent_spans = tracer.get_trace_spans(trace_id_agent)
print(f"  spans count: {len(agent_spans)}")
for s in agent_spans:
    print(f"    {s['name']} ({s['span_type']})")

print("\n=== LOOP trace ===")
loop_spans = tracer.get_trace_spans(trace_id_loop)
print(f"  spans count: {len(loop_spans)}")
for s in loop_spans:
    print(f"    {s['name']} ({s['span_type']})")

print(f"\nAPI 返回 trace_id: {trace_id_agent}")
print(f"实际执行 trace_id: {trace_id_loop}")
print(f"\n结论: API 消费者拿着 {trace_id_agent} 去查 trace，只能看到 {len(agent_spans)} 个 spans")
print(f"         但真实执行在 {trace_id_loop} 里，有 {len(loop_spans)} 个 spans")
print(f"         端到端追踪断裂: {trace_id_agent != trace_id_loop and len(agent_spans) == 0 and len(loop_spans) > 0}")
