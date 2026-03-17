"""
Genesis Observability — 轻量级链路追踪
零外部依赖，SQLite 持久化，可选 Langfuse 上报。

使用方式:
    tracer = Tracer.get_instance()
    trace_id = tracer.start_trace(user_input)
    span_id  = tracer.start_span(trace_id, "G_PHASE", span_type="phase")
    llm_span = tracer.start_span(trace_id, "llm_call", span_type="llm_call", parent=span_id, meta={"model": "deepseek-chat"})
    tracer.end_span(llm_span, input_tokens=100, output_tokens=50)
    tracer.end_span(span_id)
    tracer.end_trace(trace_id)
"""

import os
import json
import time
import uuid
import sqlite3
import logging
import threading
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parent.parent.parent / "runtime"
_DB_PATH = _DB_DIR / "traces.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id        TEXT PRIMARY KEY,
    user_input      TEXT,
    started_at      REAL,
    ended_at        REAL,
    duration_ms     REAL,
    total_input_tokens  INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    phase_count     INTEGER DEFAULT 0,
    llm_call_count  INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'running',
    final_response_preview TEXT,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS spans (
    span_id         TEXT PRIMARY KEY,
    trace_id        TEXT,
    parent_span_id  TEXT,
    name            TEXT,
    span_type       TEXT,
    phase           TEXT,
    started_at      REAL,
    ended_at        REAL,
    duration_ms     REAL,
    model           TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    total_tokens    INTEGER,
    tool_name       TEXT,
    tool_args_preview   TEXT,
    tool_result_preview TEXT,
    metadata_json   TEXT,
    status          TEXT DEFAULT 'running',
    error           TEXT,
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
);

CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_type  ON spans(span_type);
CREATE INDEX IF NOT EXISTS idx_traces_time ON traces(started_at DESC);
"""


class Tracer:
    """线程安全的单例追踪器"""

    _instance: Optional["Tracer"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._conn: Optional[sqlite3.Connection] = None
        self._enabled = True
        self._langfuse = None
        self._init_db()
        self._try_init_langfuse()

    @classmethod
    def get_instance(cls) -> "Tracer":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── DB ────────────────────────────────────────────────
    def _init_db(self):
        try:
            _DB_DIR.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            logger.info(f"Tracer DB ready: {_DB_PATH}")
        except Exception as e:
            logger.warning(f"Tracer DB init failed (tracing disabled): {e}")
            self._enabled = False

    # ── Langfuse (optional) ───────────────────────────────
    def _try_init_langfuse(self):
        pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
        sk = os.environ.get("LANGFUSE_SECRET_KEY")
        host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        if not (pk and sk):
            return
        try:
            from langfuse import Langfuse
            self._langfuse = Langfuse(public_key=pk, secret_key=sk, host=host)
            logger.info(f"Langfuse connected: {host}")
        except ImportError:
            logger.info("Langfuse SDK not installed — local tracing only.")
        except Exception as e:
            logger.warning(f"Langfuse init failed: {e}")

    # ── Trace lifecycle ───────────────────────────────────
    def start_trace(self, user_input: str = "") -> str:
        trace_id = f"tr_{uuid.uuid4().hex[:12]}"
        if not self._enabled:
            return trace_id
        try:
            self._conn.execute(
                "INSERT INTO traces (trace_id, user_input, started_at) VALUES (?, ?, ?)",
                (trace_id, user_input[:500], time.time())
            )
            self._conn.commit()
        except Exception as e:
            logger.debug(f"Tracer write error: {e}")

        if self._langfuse:
            try:
                self._langfuse.trace(id=trace_id, input=user_input[:500])
            except Exception:
                pass
        return trace_id

    def end_trace(self, trace_id: str, *, status: str = "completed",
                  final_response: str = "", error: str = "",
                  input_tokens: int = 0, output_tokens: int = 0,
                  total_tokens: int = 0, phase_count: int = 0,
                  llm_call_count: int = 0, tool_call_count: int = 0):
        if not self._enabled:
            return
        now = time.time()
        try:
            self._conn.execute("""
                UPDATE traces SET
                    ended_at = ?, status = ?, error = ?,
                    final_response_preview = ?,
                    total_input_tokens = ?, total_output_tokens = ?, total_tokens = ?,
                    phase_count = ?, llm_call_count = ?, tool_call_count = ?,
                    duration_ms = (? - started_at) * 1000
                WHERE trace_id = ?
            """, (now, status, error or None,
                  (final_response or "")[:300],
                  input_tokens, output_tokens, total_tokens,
                  phase_count, llm_call_count, tool_call_count,
                  now, trace_id))
            self._conn.commit()
        except Exception as e:
            logger.debug(f"Tracer write error: {e}")

        if self._langfuse:
            try:
                self._langfuse.trace(id=trace_id, output=(final_response or "")[:300])
                self._langfuse.flush()
            except Exception:
                pass

    # ── Span lifecycle ────────────────────────────────────
    def start_span(self, trace_id: str, name: str, *,
                   span_type: str = "generic",
                   phase: str = "",
                   parent: str = None,
                   meta: Dict[str, Any] = None) -> str:
        span_id = f"sp_{uuid.uuid4().hex[:12]}"
        if not self._enabled:
            return span_id
        try:
            self._conn.execute(
                """INSERT INTO spans
                   (span_id, trace_id, parent_span_id, name, span_type, phase,
                    started_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (span_id, trace_id, parent, name, span_type, phase,
                 time.time(), json.dumps(meta or {}, ensure_ascii=False))
            )
            self._conn.commit()
        except Exception as e:
            logger.debug(f"Tracer write error: {e}")

        if self._langfuse:
            try:
                lf_type = "generation" if span_type == "llm_call" else "span"
                if lf_type == "generation":
                    self._langfuse.generation(
                        id=span_id, trace_id=trace_id, parent_observation_id=parent,
                        name=name, model=(meta or {}).get("model", ""),
                        metadata=meta
                    )
                else:
                    self._langfuse.span(
                        id=span_id, trace_id=trace_id, parent_observation_id=parent,
                        name=name, metadata=meta
                    )
            except Exception:
                pass
        return span_id

    def end_span(self, span_id: str, *,
                 status: str = "completed", error: str = "",
                 input_tokens: int = 0, output_tokens: int = 0,
                 total_tokens: int = 0, model: str = "",
                 tool_name: str = "", tool_args: Any = None,
                 tool_result: str = ""):
        if not self._enabled:
            return
        now = time.time()
        args_preview = ""
        if tool_args is not None:
            try:
                args_preview = json.dumps(tool_args, ensure_ascii=False)[:300]
            except Exception:
                args_preview = str(tool_args)[:300]

        try:
            self._conn.execute("""
                UPDATE spans SET
                    ended_at = ?, duration_ms = (? - started_at) * 1000,
                    status = ?, error = ?,
                    model = COALESCE(NULLIF(?, ''), model),
                    input_tokens = ?, output_tokens = ?, total_tokens = ?,
                    tool_name = COALESCE(NULLIF(?, ''), tool_name),
                    tool_args_preview = COALESCE(NULLIF(?, ''), tool_args_preview),
                    tool_result_preview = COALESCE(NULLIF(?, ''), tool_result_preview)
                WHERE span_id = ?
            """, (now, now, status, error or None,
                  model or "",
                  input_tokens, output_tokens, total_tokens,
                  tool_name or "", args_preview, (tool_result or "")[:500],
                  span_id))
            self._conn.commit()
        except Exception as e:
            logger.debug(f"Tracer write error: {e}")

        if self._langfuse:
            try:
                self._langfuse.span(id=span_id, end_time=now)
            except Exception:
                pass

    # ── Convenience helpers ───────────────────────────────
    def log_llm_call(self, trace_id: str, *, parent: str = None,
                     phase: str = "", model: str = "",
                     input_tokens: int = 0, output_tokens: int = 0,
                     total_tokens: int = 0, duration_ms: float = 0,
                     has_tool_calls: bool = False, error: str = ""):
        """一步记录完整的 LLM 调用（不需要 start/end 配对）"""
        if not self._enabled:
            return
        span_id = f"sp_{uuid.uuid4().hex[:12]}"
        now = time.time()
        name = f"llm:{model}" if model else "llm_call"
        meta = {"has_tool_calls": has_tool_calls}
        try:
            self._conn.execute(
                """INSERT INTO spans
                   (span_id, trace_id, parent_span_id, name, span_type, phase,
                    started_at, ended_at, duration_ms,
                    model, input_tokens, output_tokens, total_tokens,
                    metadata_json, status, error)
                   VALUES (?, ?, ?, ?, 'llm_call', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (span_id, trace_id, parent, name, phase,
                 now - (duration_ms / 1000), now, duration_ms,
                 model, input_tokens, output_tokens, total_tokens,
                 json.dumps(meta, ensure_ascii=False),
                 "error" if error else "completed", error or None)
            )
            self._conn.commit()
        except Exception as e:
            logger.debug(f"Tracer write error: {e}")

    def log_tool_call(self, trace_id: str, *, parent: str = None,
                      phase: str = "", tool_name: str = "",
                      tool_args: Any = None, tool_result: str = "",
                      duration_ms: float = 0, error: str = ""):
        """一步记录完整的 Tool 调用"""
        if not self._enabled:
            return
        span_id = f"sp_{uuid.uuid4().hex[:12]}"
        now = time.time()
        args_preview = ""
        if tool_args is not None:
            try:
                args_preview = json.dumps(tool_args, ensure_ascii=False)[:300]
            except Exception:
                args_preview = str(tool_args)[:300]
        try:
            self._conn.execute(
                """INSERT INTO spans
                   (span_id, trace_id, parent_span_id, name, span_type, phase,
                    started_at, ended_at, duration_ms,
                    tool_name, tool_args_preview, tool_result_preview,
                    status, error)
                   VALUES (?, ?, ?, ?, 'tool_call', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (span_id, trace_id, parent, f"tool:{tool_name}", phase,
                 now - (duration_ms / 1000), now, duration_ms,
                 tool_name, args_preview, (tool_result or "")[:500],
                 "error" if error else "completed", error or None)
            )
            self._conn.commit()
        except Exception as e:
            logger.debug(f"Tracer write error: {e}")

    # ── Query helpers (for diagnostics) ───────────────────
    def get_recent_traces(self, limit: int = 10) -> list:
        if not self._enabled:
            return []
        cur = self._conn.execute(
            "SELECT * FROM traces ORDER BY started_at DESC LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_trace_spans(self, trace_id: str) -> list:
        if not self._enabled:
            return []
        cur = self._conn.execute(
            "SELECT * FROM spans WHERE trace_id = ? ORDER BY started_at", (trace_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_slow_spans(self, min_duration_ms: float = 5000, limit: int = 20) -> list:
        if not self._enabled:
            return []
        cur = self._conn.execute(
            "SELECT * FROM spans WHERE duration_ms >= ? ORDER BY duration_ms DESC LIMIT ?",
            (min_duration_ms, limit))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
