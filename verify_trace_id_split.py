import sys, os, sqlite3, json
sys.path.insert(0, '/workspace')
os.chdir('/workspace')

# 复现 trace_id 分裂
from genesis.core.tracer import Tracer

# 清理旧 trace DB
tracer = Tracer.get_instance()
if tracer._enabled:
    tracer._conn.execute("DELETE FROM traces")
    tracer._conn.execute("DELETE FROM spans")
    tracer._conn.commit()

# 模拟 agent.process() 调用
trace_id_agent = tracer.start_trace("test user input from API")
print(f"AGENT trace_id: {trace_id_agent}")

# 模拟 loop.run() 内部调用
trace_id_loop = tracer.start_trace("test user input from API")
print(f"LOOP  trace_id: {trace_id_loop}")

# 检查是否相同
print(f"SAME? {trace_id_agent == trace_id_loop}")

# 查看 traces 表
cur = tracer._conn.execute("SELECT trace_id, user_input, status FROM traces ORDER BY started_at")
for row in cur.fetchall():
    print(f"  DB: trace_id={row[0][:16]}... user_input={row[1][:30]!r} status={row[2]}")

# 模拟 API 返回的是 agent 的 trace_id，但 loop 的 trace_id 才是实际执行记录
print(f"\nAPI 返回 trace_id: {trace_id_agent}")
print(f"实际执行 trace_id: {trace_id_loop}")
print(f"用 API trace_id 查 spans: {tracer.get_trace_spans(trace_id_agent)}")
print(f"用 LOOP trace_id 查 spans: {len(tracer.get_trace_spans(trace_id_loop))} spans")
