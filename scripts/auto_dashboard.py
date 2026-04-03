#!/usr/bin/env python3
"""
Genesis Auto Dashboard — 本地 Web 观测台
读取 runtime/auto_reports/ 中的 JSON 文件，提供无字数限制的完整视图。

用法:
  python scripts/auto_dashboard.py          # 默认 http://localhost:7788
  python scripts/auto_dashboard.py --port 8080
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "runtime" / "auto_reports"

# ── HTML 模板 ──────────────────────────────────────────────────────────────

_CSS = """
body{font-family:system-ui,sans-serif;margin:0;background:#0d1117;color:#c9d1d9}
h1,h2,h3{color:#58a6ff}a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}
.container{max-width:1200px;margin:0 auto;padding:16px}
.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:16px;margin:12px 0}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600}
.badge-green{background:#1a4731;color:#3fb950}
.badge-red{background:#4d1b1b;color:#f85149}
.badge-gray{background:#21262d;color:#8b949e}
.badge-blue{background:#1a3a5c;color:#58a6ff}
pre{background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:12px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;font-size:13px;line-height:1.5}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid #30363d;font-size:13px}
th{background:#21262d;color:#8b949e;font-weight:600}
tr:hover{background:#1c2128}
.event-row{margin:4px 0;padding:6px 10px;border-left:3px solid #30363d;border-radius:0 4px 4px 0;font-size:12px}
.ev-blueprint{border-color:#58a6ff;background:#0d1a2d}
.ev-tool_start{border-color:#3fb950;background:#0d1a12}
.ev-tool_result{border-color:#56d364;background:#0d1e12}
.ev-thought{border-color:#d29922;background:#1f1a0d}
.ev-search_result{border-color:#a371f7;background:#160d2a}
.ev-lens_start,.ev-lens_analysis,.ev-lens_adoption{border-color:#79c0ff;background:#0d1a2d}
.node-new{color:#3fb950}
.node-updated{color:#d29922}
.stat{display:inline-block;margin:0 16px 0 0;font-size:14px}
.stat-val{font-size:22px;font-weight:700;color:#58a6ff}
"""

_PAGE_HEAD = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Genesis Auto Dashboard</title><style>{css}</style></head><body>
<div class="container">
<h1>🔭 Genesis Auto Dashboard</h1>
""".format(css=_CSS)

_PAGE_FOOT = "</div></body></html>"


def _badge(text: str, kind: str = "gray") -> str:
    return f'<span class="badge badge-{kind}">{text}</span>'


def _render_index() -> str:
    parts = [_PAGE_HEAD, '<p><a href="/">⟳ 刷新</a></p>']

    if not REPORTS_DIR.exists():
        parts.append('<div class="card">暂无报告（runtime/auto_reports/ 不存在）</div>')
        parts.append(_PAGE_FOOT)
        return "".join(parts)

    sessions = []
    for sj in sorted(REPORTS_DIR.glob("auto_*.json"), reverse=True):
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
            data["_file"] = sj.name
            sessions.append(data)
        except Exception:
            pass

    if not sessions:
        parts.append('<div class="card">暂无已完成的 session（仍在运行中的 session 在结束后出现）</div>')
        # 显示进行中的 sessions
        for rdir in sorted(REPORTS_DIR.iterdir(), reverse=True):
            if rdir.is_dir():
                rounds = sorted(rdir.glob("round_*.json"))
                if rounds:
                    parts.append(f'<div class="card"><b>🔄 进行中: {rdir.name}</b> — {len(rounds)} 轮已落盘 '
                                 f'<a href="/session/{rdir.name}">查看</a></div>')
    else:
        parts.append('<table><tr><th>Session</th><th>轮次</th><th>有产出</th><th>新节点</th><th>Token</th><th>停止原因</th><th></th></tr>')
        for s in sessions:
            sid = s.get("session_id", s["_file"])
            rounds = s.get("total_rounds", "?")
            prog = s.get("progress_rounds", 0)
            new_n = s.get("total_new_nodes", 0)
            tokens = s.get("total_tokens", 0)
            stop = s.get("stop_reason", "?")
            prog_badge = _badge(f"{prog}/{rounds}", "green" if prog > 0 else "gray")
            new_badge = _badge(f"+{new_n}", "green" if new_n > 0 else "gray")
            parts.append(
                f'<tr><td><code>{sid}</code></td><td>{rounds}</td>'
                f'<td>{prog_badge}</td><td>{new_badge}</td>'
                f'<td>{tokens:,}</td><td><code>{stop}</code></td>'
                f'<td><a href="/session/{sid}">详情</a></td></tr>'
            )
        parts.append('</table>')

        # 进行中
        for rdir in sorted(REPORTS_DIR.iterdir(), reverse=True):
            if rdir.is_dir() and not (REPORTS_DIR / f"auto_{rdir.name}.json").exists():
                rounds = sorted(rdir.glob("round_*.json"))
                if rounds:
                    parts.append(f'<div class="card">🔄 <b>进行中: {rdir.name}</b> — {len(rounds)} 轮 '
                                 f'<a href="/session/{rdir.name}">实时查看</a></div>')

    parts.append(_PAGE_FOOT)
    return "".join(parts)


def _render_session(session_id: str) -> str:
    rounds_dir = REPORTS_DIR / session_id
    session_json = REPORTS_DIR / f"auto_{session_id}.json"

    parts = [_PAGE_HEAD, f'<p><a href="/">← 返回列表</a> &nbsp; <a href="/session/{session_id}">⟳ 刷新</a></p>']
    parts.append(f'<h2>Session: <code>{session_id}</code></h2>')

    # 汇总卡片
    if session_json.exists():
        try:
            s = json.loads(session_json.read_text(encoding="utf-8"))
            prog = s.get("progress_rounds", 0)
            total = s.get("total_rounds", 0)
            parts.append(
                f'<div class="card">'
                f'<span class="stat"><span class="stat-val">{total}</span> 轮</span>'
                f'<span class="stat"><span class="stat-val" style="color:#3fb950">{prog}</span> 有产出</span>'
                f'<span class="stat"><span class="stat-val">{s.get("total_new_nodes",0)}</span> 新节点</span>'
                f'<span class="stat"><span class="stat-val">{s.get("total_updated_nodes",0)}</span> 更新</span>'
                f'<span class="stat"><span class="stat-val">{s.get("total_tokens",0):,}</span> tokens</span>'
                f'<br><br>停止原因: <code>{s.get("stop_reason","?")}</code>'
                f'</div>'
            )
        except Exception:
            pass

    if not rounds_dir.exists():
        parts.append('<div class="card">rounds 目录不存在</div>')
        parts.append(_PAGE_FOOT)
        return "".join(parts)

    round_files = sorted(rounds_dir.glob("round_*.json"))
    if not round_files:
        parts.append('<div class="card">暂无 round JSON 文件</div>')
        parts.append(_PAGE_FOOT)
        return "".join(parts)

    for rfile in round_files:
        try:
            r = json.loads(rfile.read_text(encoding="utf-8"))
        except Exception:
            continue

        rnum = r.get("round", "?")
        duration = r.get("duration_s", 0)
        tokens = r.get("tokens", 0)
        kb_sum = r.get("kb_delta_summary", "?")
        kb_changed = r.get("kb_changed", False)
        dry = r.get("consecutive_dry", 0)
        tele = r.get("node_telemetry", "")
        exc = r.get("exception")

        status_badge = _badge("有产出", "green") if kb_changed else _badge("dry", "gray")
        exc_badge = _badge("异常", "red") if exc else ""

        parts.append(f'<div class="card">')
        parts.append(
            f'<h3>第 {rnum} 轮 {status_badge} {exc_badge}</h3>'
            f'<p>{duration}s &nbsp;|&nbsp; {tokens:,} tokens &nbsp;|&nbsp; KB: <b>{kb_sum}</b> '
            f'&nbsp;|&nbsp; {tele} &nbsp;|&nbsp; dry={dry}</p>'
        )

        # KB delta
        kb = r.get("kb_delta", {})
        new_nodes = kb.get("new_nodes", [])
        upd_nodes = kb.get("updated_nodes", [])
        if new_nodes or upd_nodes:
            parts.append('<h4>📚 KB 变化</h4><table><tr><th>类型</th><th>状态</th><th>node_id</th><th>标题</th><th>conf</th><th>tier</th></tr>')
            for n in new_nodes:
                parts.append(
                    f'<tr><td>{n.get("type","?")}</td>'
                    f'<td class="node-new">新建</td>'
                    f'<td><code>{n.get("node_id","")[:40]}</code></td>'
                    f'<td>{n.get("title","")[:60]}</td>'
                    f'<td>{n.get("confidence_score","?")}</td>'
                    f'<td>{n.get("trust_tier","?")}</td></tr>'
                )
            for n in upd_nodes:
                parts.append(
                    f'<tr><td>{n.get("type","?")}</td>'
                    f'<td class="node-updated">更新</td>'
                    f'<td><code>{n.get("node_id","")[:40]}</code></td>'
                    f'<td>{n.get("title","")[:60]}</td>'
                    f'<td>{n.get("confidence_score","?")}</td>'
                    f'<td>{n.get("trust_tier","?")}</td></tr>'
                )
            parts.append('</table>')

        # 事件流
        events = r.get("events", [])
        if events:
            parts.append('<h4>🔗 思维链路</h4>')
            for ev in events:
                etype = ev.get("type", "unknown")
                t = ev.get("t", 0)
                css_class = f'ev-{etype}' if etype in (
                    "blueprint", "tool_start", "tool_result", "thought",
                    "search_result", "lens_start", "lens_analysis", "lens_adoption"
                ) else ""
                label = {
                    "blueprint": "📋 G计划",
                    "tool_start": "🟢 工具启动",
                    "tool_result": "↩️ 工具返回",
                    "thought": "💭 思考",
                    "search_result": "🔎 搜索结果",
                    "lens_start": "🔭 透镜启动",
                    "lens_analysis": "🔭 透镜分析",
                    "lens_adoption": "✅ 透镜采纳",
                }.get(etype, etype)

                content = ""
                if "content" in ev:
                    content = str(ev["content"])[:600]
                elif "result_preview" in ev:
                    content = str(ev["result_preview"])[:600]
                elif "data" in ev:
                    content = json.dumps(ev["data"], ensure_ascii=False)[:400]
                name_part = f' <code>{ev["name"]}</code>' if "name" in ev else ""

                parts.append(
                    f'<div class="event-row {css_class}">'
                    f'<b>[{t:.1f}s] {label}{name_part}</b>'
                    + (f'<pre>{content}</pre>' if content else '')
                    + '</div>'
                )

        # 完整 response
        response = r.get("response_full", "")
        if response:
            parts.append('<h4>📝 G 最终回复</h4>')
            parts.append(f'<pre>{response}</pre>')
        elif exc:
            parts.append(f'<h4>⚠️ 异常</h4><pre>{exc}</pre>')

        parts.append('</div>')  # card

    parts.append(_PAGE_FOOT)
    return "".join(parts)


# ── HTTP Handler ───────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 静默访问日志

    def _send_html(self, html: str, code: int = 200):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._send_html(_render_index())
        elif path.startswith("/session/"):
            sid = path[len("/session/"):]
            if not sid or ".." in sid:
                self._send_html("<h1>400</h1>", 400)
                return
            self._send_html(_render_session(sid))
        else:
            self._send_html("<h1>404</h1>", 404)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Genesis Auto Dashboard")
    parser.add_argument("--port", type=int, default=7788)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), DashboardHandler)
    print(f"Genesis Auto Dashboard → http://{args.host}:{args.port}")
    print(f"Reports dir: {REPORTS_DIR}")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
