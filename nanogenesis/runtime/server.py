
import http.server
import socketserver
import json
import asyncio
import logging
import sys
import time
import threading
import uuid
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.agent import NanoGenesis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("server")

agent = None

# ═══════════════════════════════════════════════
# 异步任务管理器
# ═══════════════════════════════════════════════
class TaskManager:
    """管理所有异步推理任务"""
    def __init__(self):
        self.tasks = {}       # task_id -> task_info
        self.lock = threading.Lock()
    
    def create(self, message):
        task_id = str(uuid.uuid4())[:8]
        task = {
            "id": task_id,
            "message": message,
            "status": "queued",     # queued -> thinking -> done / error
            "created": time.time(),
            "result": None,
            "error": None,
            "reasoning_log": None,
            "metrics": None,
        }
        with self.lock:
            self.tasks[task_id] = task
        return task_id
    
    def update(self, task_id, **kwargs):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)
    
    def get(self, task_id):
        with self.lock:
            return self.tasks.get(task_id, {}).copy()
    
    def process_async(self, task_id):
        """在后台线程中执行推理"""
        t = threading.Thread(target=self._run, args=(task_id,), daemon=True)
        t.start()
    
    def _run(self, task_id):
        task = self.get(task_id)
        if not task:
            return
        
        self.update(task_id, status="thinking")
        activity_log.push("EXECUTION", f"📨 开始处理: {task['message'][:60]}...")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Step Callback (透明化执行过程)
        def on_step(step_type, data):
            with self.lock:
                t = self.tasks[task_id]
                if "steps" not in t: t["steps"] = []
                t["steps"].append({
                    "ts": time.time(),
                    "type": step_type,
                    "data": data
                })
        
        try:
            result = loop.run_until_complete(
                asyncio.wait_for(agent.process(task["message"], step_callback=on_step), timeout=1200)
            )
            
            reasoning_log = agent.get_reasoning_log()
            agent.clear_reasoning_log()
            
            self.update(task_id,
                status="done",
                result=result.get("response", ""),
                reasoning_log=reasoning_log,
                metrics={
                    "tokens": result['metrics'].total_tokens if result.get('metrics') else 0,
                    "time": result['metrics'].total_time if result.get('metrics') else 0
                }
            )
            activity_log.push("EXECUTION", f"✅ 任务 {task_id} 完成")
            
        except asyncio.TimeoutError:
            user_msg = task.get("message", "")
            self.update(task_id, status="error", error="推理超时（20分钟限制）")
            activity_log.push("ERROR", f"⏰ 任务 {task_id} 超时")
            
            # 将超时事件写入记忆，让 Genesis 下次知道自己超时过
            try:
                import datetime
                from pathlib import Path
                now = datetime.datetime.now()
                timeout_entry = (
                    f"## {now.strftime('%H:%M:%S')} [⏰ 超时]\n\n"
                    f"**用户**: {user_msg}\n\n"
                    f"**Genesis**: ⚠️ 处理此请求时超时（20分钟限制）。"
                    f"未能完成回复。\n\n---\n\n"
                )
                log_dir = Path.home() / ".nanogenesis" / "conversations"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / f"{now.strftime('%Y-%m-%d')}.md"
                if not log_file.exists():
                    log_file.write_text(
                        f"# Genesis 对话日志 - {now.strftime('%Y年%m月%d日')}\n\n",
                        encoding='utf-8'
                    )
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(timeout_entry)
                
                # 也写入 QmdMemory
                timeout_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(timeout_loop)
                try:
                    timeout_loop.run_until_complete(agent.memory.add(
                        content=f"用户: {user_msg}\nGenesis: ⚠️ 此请求处理超时（20分钟），未完成回复。",
                        path=f"conversations/{now.strftime('%Y-%m-%d/%H%M%S')}_timeout",
                        collection="conversations",
                        title=f"[超时] {user_msg[:50]}",
                        metadata={"type": "timeout", "timestamp": now.isoformat()}
                    ))
                finally:
                    timeout_loop.close()
                    
            except Exception as mem_err:
                logging.warning(f"超时记忆写入失败: {mem_err}")
                
        except Exception as e:
            self.update(task_id, status="error", error=str(e))
            activity_log.push("ERROR", f"❌ 任务 {task_id} 失败: {str(e)[:80]}")
        finally:
            loop.close()

task_manager = TaskManager()

# ═══════════════════════════════════════════════
# 实时活动日志广播器 (SSE)
# ═══════════════════════════════════════════════
class ActivityLog:
    def __init__(self, maxlen=200):
        self.history = deque(maxlen=maxlen)
        self.subscribers = []
        self.lock = threading.Lock()
    
    def push(self, event_type, message):
        entry = {
            "ts": time.time(),
            "type": event_type,
            "msg": message
        }
        with self.lock:
            self.history.append(entry)
            dead = []
            for q in self.subscribers:
                try:
                    q.append(entry)
                except:
                    dead.append(q)
            for d in dead:
                self.subscribers.remove(d)
    
    def subscribe(self):
        q = deque(maxlen=500)
        with self.lock:
            for h in self.history:
                q.append(h)
            self.subscribers.append(q)
        return q
    
    def unsubscribe(self, q):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

activity_log = ActivityLog()

class ActivityLogHandler(logging.Handler):
    KEYWORDS = {
        '洞察完成': 'AWARENESS', '战略蓝图': 'STRATEGY',
        '工具调用': 'TOOL', '已注册': 'SYSTEM', '已加载': 'SYSTEM',
        '收到请求': 'EXECUTION', '记忆': 'MEMORY', '决策流形': 'MEMORY',
    }
    def emit(self, record):
        msg = self.format(record)
        etype = 'SYSTEM'
        for kw, et in self.KEYWORDS.items():
            if kw in msg:
                etype = et
                break
        if record.levelno >= logging.ERROR:
            etype = 'ERROR'
        activity_log.push(etype, msg)

_handler = ActivityLogHandler()
_handler.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger().addHandler(_handler)


# ═══════════════════════════════════════════════
# HTTP 处理器
# ═══════════════════════════════════════════════
class NanoGenesisHandler(http.server.SimpleHTTPRequestHandler):
    
    def log_message(self, format, *args):
        pass  # 静默 HTTP 日志
    
    def do_GET(self):
        if self.path == '/':
            self._serve_html()
        elif self.path == '/api/logs':
            self._serve_sse()
        elif self.path.startswith('/api/task/'):
            self._serve_task_status()
        elif self.path == '/api/status':
            self._send_json({"alive": True, "tasks": len(task_manager.tasks)})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/api/chat':
            content_length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(content_length).decode('utf-8'))
            message = data.get('message', '')
            
            if not message:
                self._send_json({"error": "empty message"}, 400)
                return
            
            # 立即返回 task_id，不阻塞
            task_id = task_manager.create(message)
            task_manager.process_async(task_id)
            
            self._send_json({"task_id": task_id, "status": "queued"})
        else:
            self.send_error(404)

    def _serve_html(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        html_path = Path(__file__).parent / "web" / "index.html"
        with open(html_path, 'rb') as f:
            self.wfile.write(f.read())

    def _serve_sse(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
        
        q = activity_log.subscribe()
        try:
            while True:
                while q:
                    entry = q.popleft()
                    data = json.dumps(entry, ensure_ascii=False)
                    self.wfile.write(f"data: {data}\n\n".encode('utf-8'))
                    self.wfile.flush()
                time.sleep(0.5)
                self.wfile.write(b": hb\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            activity_log.unsubscribe(q)

    def _serve_task_status(self):
        task_id = self.path.split('/')[-1]
        task = task_manager.get(task_id)
        if not task:
            self._send_json({"error": "task not found"}, 404)
        else:
            self._send_json(task)

    def _send_json(self, data, status=200):
        try:
            self.send_response(status)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except BrokenPipeError:
            pass

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    global agent
    print("🚀 初始化 NanoGenesis Web Server (异步任务模式)...")
    activity_log.push('SYSTEM', '🚀 NanoGenesis 异步服务正在启动...')
    
    try:
        agent = NanoGenesis(enable_optimization=True)
        activity_log.push('SYSTEM', '✅ Agent 核心就绪')
        
        activity_log.push('SYSTEM', '🧠 正在预加载元认知语义模型...')
        if agent.memory:
            asyncio.run(agent.memory.search("init", limit=1))
        activity_log.push('SYSTEM', '✅ 模型预加载完成')
        
        PORT = 8000
        with ThreadedTCPServer(("0.0.0.0", PORT), NanoGenesisHandler) as httpd:
            activity_log.push('SYSTEM', f'🌍 异步服务已启动: http://localhost:{PORT}')
            print(f"\n🌍 异步任务服务已启动:")
            print(f"   http://localhost:{PORT}")
            print(f"   POST /api/chat → 提交任务 (立即返回)")
            print(f"   GET  /api/task/{{id}} → 轮询结果")
            print(f"   GET  /api/logs → SSE 实时日志")
            print("\n按 Ctrl+C 停止")
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n👋 停止")
    except Exception as e:
        logger.error(f"崩溃: {e}", exc_info=True)

if __name__ == "__main__":
    main()
