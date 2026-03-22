#!/usr/bin/env python3
"""
Genesis Code Metainfo MCP Server (stdio JSON-RPC 2.0)

Applies Genesis's metadata methodology to code understanding.
Instead of querying Genesis's knowledge base, this gives Cascade its own
"code nervous system" — structured observations anchored to verified facts.

Core concepts (borrowed from Genesis):
- Typed observations: CONSTRAINT, COUPLING, FRAGILITY, TRADEOFF, LESSON, PATTERN
- Metadata signatures for scoping (component, concern_type, etc.)
- Confidence scores with verify/invalidate lifecycle
- Digest for situational awareness before diving into code

No external dependencies — pure stdlib.
"""
import json
import sys
import os
import sqlite3
import time
import hashlib
import traceback
from pathlib import Path
from datetime import datetime

# ─── Database Setup ───

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / ".cascade"
DB_PATH = DB_DIR / "code_observations.db"

VALID_TYPES = {"CONSTRAINT", "COUPLING", "FRAGILITY", "TRADEOFF", "LESSON", "PATTERN"}
VALID_SOURCES = {"inference", "code_review", "runtime_test", "bug_fix", "user_report"}


def _init_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS code_observations (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            why_important TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            function_name TEXT DEFAULT '',
            signature TEXT DEFAULT '{}',
            confidence REAL DEFAULT 0.8,
            source TEXT DEFAULT 'inference',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            status TEXT DEFAULT 'active'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS observation_edges (
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            PRIMARY KEY (source_id, target_id, relation)
        )
    """)
    conn.commit()
    return conn


def _gen_id(obs_type: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = hashlib.md5(f"{time.time_ns()}".encode()).hexdigest()[:4]
    return f"{obs_type}_{ts}_{suffix}"


# ─── Tool Implementations ───

def record_code_observation(conn, args):
    obs_type = (args.get("type") or "").upper()
    if obs_type not in VALID_TYPES:
        return f"Invalid type '{obs_type}'. Must be one of: {', '.join(sorted(VALID_TYPES))}"

    title = (args.get("title") or "").strip()
    content = (args.get("content") or "").strip()
    if not title or not content:
        return "Both 'title' and 'content' are required."

    obs_id = _gen_id(obs_type)
    signature = json.dumps(args.get("signature") or {}, ensure_ascii=False)
    source = args.get("source", "inference")
    if source not in VALID_SOURCES:
        source = "inference"
    confidence = max(0.1, min(1.0, float(args.get("confidence", 0.8))))

    conn.execute(
        """INSERT INTO code_observations
           (id, type, title, content, why_important, file_path, function_name, signature, confidence, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (obs_id, obs_type, title, content,
         args.get("why_important", ""),
         args.get("file_path", ""),
         args.get("function_name", ""),
         signature, confidence, source)
    )
    conn.commit()
    return json.dumps({"id": obs_id, "status": "recorded", "type": obs_type, "confidence": confidence}, ensure_ascii=False)


def search_code_observations(conn, args):
    query = (args.get("query") or "").strip()
    obs_type = (args.get("type") or "").upper() or None
    file_path = (args.get("file_path") or "").strip() or None
    component = (args.get("component") or "").strip() or None
    status = args.get("status", "active")

    conditions = ["status = ?"]
    params = [status]

    if obs_type and obs_type in VALID_TYPES:
        conditions.append("type = ?")
        params.append(obs_type)
    if file_path:
        conditions.append("file_path LIKE ?")
        params.append(f"%{file_path}%")
    if component:
        conditions.append("(signature LIKE ? OR file_path LIKE ? OR function_name LIKE ?)")
        params.extend([f"%{component}%"] * 3)
    if query:
        conditions.append("(title LIKE ? OR content LIKE ? OR why_important LIKE ?)")
        params.extend([f"%{query}%"] * 3)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT id, type, title, content, why_important, file_path, function_name,
                   signature, confidence, source, created_at, updated_at
            FROM code_observations WHERE {where}
            ORDER BY confidence DESC, updated_at DESC LIMIT 20""",
        params
    ).fetchall()

    if not rows:
        return "No observations found matching your criteria."

    results = []
    for r in rows:
        sig = json.loads(r["signature"]) if r["signature"] else {}
        sig_text = ", ".join(f"{k}={v}" for k, v in sig.items()) if sig else "-"
        entry = f"[{r['type']}] {r['title']}  (id: {r['id']})\n"
        entry += f"  confidence={r['confidence']:.2f} | source={r['source']} | file={r['file_path'] or 'N/A'}"
        if r["function_name"]:
            entry += f" | func={r['function_name']}"
        entry += f"\n  sig: {sig_text}\n"
        entry += f"  {r['content'][:300]}{'...' if len(r['content']) > 300 else ''}"
        if r["why_important"]:
            entry += f"\n  WHY: {r['why_important'][:200]}"
        results.append(entry)

    return f"Found {len(rows)} observations:\n\n" + "\n\n".join(results)


def get_observation(conn, args):
    obs_id = (args.get("id") or "").strip()
    if not obs_id:
        return "Parameter 'id' is required."

    row = conn.execute("SELECT * FROM code_observations WHERE id = ?", (obs_id,)).fetchone()
    if not row:
        return f"Observation '{obs_id}' not found."

    result = {k: row[k] for k in row.keys()}
    result["signature"] = json.loads(result["signature"]) if result["signature"] else {}

    edges = conn.execute(
        "SELECT source_id, target_id, relation FROM observation_edges WHERE source_id = ? OR target_id = ?",
        (obs_id, obs_id)
    ).fetchall()
    if edges:
        result["related"] = [{"from": e["source_id"], "to": e["target_id"], "relation": e["relation"]} for e in edges]

    return json.dumps(result, ensure_ascii=False, indent=2)


def verify_observation(conn, args):
    obs_id = (args.get("id") or "").strip()
    if not obs_id:
        return "Parameter 'id' is required."

    row = conn.execute("SELECT id, confidence FROM code_observations WHERE id = ?", (obs_id,)).fetchone()
    if not row:
        return f"Observation '{obs_id}' not found."

    new_conf = min(1.0, row["confidence"] + 0.1)
    source = args.get("source", "code_review")
    conn.execute(
        "UPDATE code_observations SET confidence = ?, source = ?, status = 'active', updated_at = datetime('now') WHERE id = ?",
        (new_conf, source, obs_id)
    )
    conn.commit()
    return json.dumps({"id": obs_id, "old_confidence": row["confidence"], "new_confidence": new_conf, "status": "verified"})


def invalidate_observation(conn, args):
    obs_id = (args.get("id") or "").strip()
    reason = args.get("reason", "code changed")
    if not obs_id:
        return "Parameter 'id' is required."

    row = conn.execute("SELECT id FROM code_observations WHERE id = ?", (obs_id,)).fetchone()
    if not row:
        return f"Observation '{obs_id}' not found."

    conn.execute(
        "UPDATE code_observations SET status = 'invalidated', confidence = confidence * 0.3, updated_at = datetime('now') WHERE id = ?",
        (obs_id,)
    )
    conn.commit()
    return json.dumps({"id": obs_id, "status": "invalidated", "reason": reason})


def get_code_digest(conn, _args):
    total = conn.execute("SELECT COUNT(*) FROM code_observations WHERE status = 'active'").fetchone()[0]
    if total == 0:
        return "No observations recorded yet. Use record_code_observation to document code facts."

    type_rows = conn.execute(
        "SELECT type, COUNT(*) as cnt, ROUND(AVG(confidence),2) as avg_conf FROM code_observations WHERE status = 'active' GROUP BY type ORDER BY cnt DESC"
    ).fetchall()

    file_rows = conn.execute(
        "SELECT file_path, COUNT(*) as cnt FROM code_observations WHERE status = 'active' AND file_path != '' GROUP BY file_path ORDER BY cnt DESC LIMIT 10"
    ).fetchall()

    top = conn.execute(
        "SELECT id, type, title, confidence, file_path, function_name FROM code_observations WHERE status = 'active' ORDER BY confidence DESC LIMIT 10"
    ).fetchall()

    lines = [f"=== Code Observations Digest ===", f"Total: {total} active\n"]

    type_parts = [f"{r['type']}({r['cnt']}, avg:{r['avg_conf']})" for r in type_rows]
    lines.append(f"By Type: {' | '.join(type_parts)}\n")

    if file_rows:
        file_parts = [f"{Path(r['file_path']).name}({r['cnt']})" for r in file_rows]
        lines.append(f"By File: {' | '.join(file_parts)}\n")

    lines.append("Top Observations:")
    for r in top:
        loc = r["function_name"] or (Path(r["file_path"]).name if r["file_path"] else "N/A")
        lines.append(f"  [{r['confidence']:.2f}] [{r['type']}] {r['title']} ({loc})")

    return "\n".join(lines)


def get_file_observations(conn, args):
    file_path = (args.get("file_path") or "").strip()
    if not file_path:
        return "Parameter 'file_path' is required."

    fname = Path(file_path).name
    rows = conn.execute(
        """SELECT id, type, title, content, why_important, function_name, confidence, source
           FROM code_observations
           WHERE (file_path LIKE ? OR file_path LIKE ?) AND status = 'active'
           ORDER BY confidence DESC""",
        (f"%{file_path}%", f"%{fname}%")
    ).fetchall()

    if not rows:
        return f"No observations for '{file_path}'."

    results = []
    for r in rows:
        entry = f"[{r['confidence']:.2f}] [{r['type']}] {r['title']}  (id: {r['id']})"
        if r["function_name"]:
            entry += f"\n  func: {r['function_name']}"
        entry += f"\n  {r['content'][:300]}{'...' if len(r['content']) > 300 else ''}"
        if r["why_important"]:
            entry += f"\n  WHY: {r['why_important'][:200]}"
        results.append(entry)

    return f"=== {file_path} ({len(rows)} observations) ===\n\n" + "\n\n".join(results)


def link_observations(conn, args):
    src = (args.get("source_id") or "").strip()
    tgt = (args.get("target_id") or "").strip()
    rel = (args.get("relation") or "RELATED_TO").upper()

    if not src or not tgt:
        return "Both 'source_id' and 'target_id' are required."

    valid_rels = {"RELATED_TO", "CONTRADICTS", "SUPERSEDES", "DEPENDS_ON"}
    if rel not in valid_rels:
        return f"Invalid relation. Must be one of: {', '.join(sorted(valid_rels))}"

    for oid in [src, tgt]:
        if not conn.execute("SELECT 1 FROM code_observations WHERE id = ?", (oid,)).fetchone():
            return f"Observation '{oid}' not found."

    conn.execute("INSERT OR REPLACE INTO observation_edges (source_id, target_id, relation) VALUES (?, ?, ?)", (src, tgt, rel))
    conn.commit()
    return json.dumps({"source": src, "target": tgt, "relation": rel, "status": "linked"})


# ─── MCP Tool Definitions ───

TOOLS = [
    {
        "name": "record_code_observation",
        "description": "Record a verified fact about the codebase: hidden constraints, implicit coupling, design tradeoffs, fragile patterns, or lessons from debugging. Anchors understanding to real code behavior, not semantic guesses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["CONSTRAINT", "COUPLING", "FRAGILITY", "TRADEOFF", "LESSON", "PATTERN"],
                         "description": "CONSTRAINT=implicit rule, COUPLING=hidden dependency, FRAGILITY=brittle code, TRADEOFF=intentional design cost, LESSON=learned from debugging, PATTERN=recurring idiom"},
                "title": {"type": "string", "description": "One-line summary"},
                "content": {"type": "string", "description": "Detail with code references (file:line)"},
                "why_important": {"type": "string", "description": "What breaks if someone doesn't know this"},
                "file_path": {"type": "string", "description": "Primary file path"},
                "function_name": {"type": "string", "description": "Primary function/method"},
                "signature": {"type": "object", "description": "Scoping metadata: {language, framework, component, concern_type, ...}",
                              "additionalProperties": True},
                "confidence": {"type": "number", "description": "0.0-1.0 certainty (default 0.8)"},
                "source": {"type": "string", "enum": ["inference", "code_review", "runtime_test", "bug_fix", "user_report"]}
            },
            "required": ["type", "title", "content"]
        }
    },
    {
        "name": "search_code_observations",
        "description": "Search known observations. Use BEFORE modifying code to check for known constraints and traps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text search across title/content/why_important"},
                "type": {"type": "string", "enum": ["CONSTRAINT", "COUPLING", "FRAGILITY", "TRADEOFF", "LESSON", "PATTERN"]},
                "file_path": {"type": "string", "description": "Filter by file (partial match)"},
                "component": {"type": "string", "description": "Filter by component (searches signature, file, function)"},
                "status": {"type": "string", "enum": ["active", "invalidated", "superseded"], "default": "active"}
            }
        }
    },
    {
        "name": "get_observation",
        "description": "Get full details of an observation by ID, including related observations.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"]
        }
    },
    {
        "name": "verify_observation",
        "description": "Confirm an observation is still valid. Boosts confidence +0.1 (max 1.0).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "source": {"type": "string", "enum": ["code_review", "runtime_test", "bug_fix"]}
            },
            "required": ["id"]
        }
    },
    {
        "name": "invalidate_observation",
        "description": "Mark an observation as no longer valid (code refactored, bug fixed, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "reason": {"type": "string", "description": "Why invalidated"}
            },
            "required": ["id", "reason"]
        }
    },
    {
        "name": "get_code_digest",
        "description": "Overview of all known code observations. Use at START of session to see what's already known.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_file_observations",
        "description": "All known observations for a file. Use BEFORE modifying a file.",
        "inputSchema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"]
        }
    },
    {
        "name": "link_observations",
        "description": "Create a relationship between two observations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string"},
                "target_id": {"type": "string"},
                "relation": {"type": "string", "enum": ["RELATED_TO", "CONTRADICTS", "SUPERSEDES", "DEPENDS_ON"]}
            },
            "required": ["source_id", "target_id", "relation"]
        }
    },
]

TOOL_DISPATCH = {
    "record_code_observation": record_code_observation,
    "search_code_observations": search_code_observations,
    "get_observation": get_observation,
    "verify_observation": verify_observation,
    "invalidate_observation": invalidate_observation,
    "get_code_digest": get_code_digest,
    "get_file_observations": get_file_observations,
    "link_observations": link_observations,
}

# ─── MCP JSON-RPC Protocol ───

def send_response(req_id, result):
    msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def send_error(req_id, code, message):
    msg = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_request(conn, req: dict):
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        send_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "genesis-nodevault", "version": "2.0.0"},
        })
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send_response(req_id, {"tools": TOOLS})
    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = TOOL_DISPATCH.get(tool_name)
        if not handler:
            send_error(req_id, -32601, f"Unknown tool: {tool_name}")
            return
        try:
            result_text = handler(conn, tool_args)
            send_response(req_id, {"content": [{"type": "text", "text": result_text}]})
        except Exception as e:
            send_response(req_id, {
                "content": [{"type": "text", "text": f"Error: {e}\n{traceback.format_exc()}"}],
                "isError": True,
            })
    elif method == "ping":
        send_response(req_id, {})
    else:
        if req_id is not None:
            send_error(req_id, -32601, f"Method not found: {method}")


def main():
    conn = _init_db()
    sys.stderr.write(f"Genesis Code Metainfo MCP Server v2.0 started. DB: {DB_PATH}\n")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            handle_request(conn, req)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"JSON parse error: {e}\n")
        except Exception as e:
            sys.stderr.write(f"Unhandled error: {e}\n{traceback.format_exc()}\n")
    conn.close()


if __name__ == "__main__":
    main()
