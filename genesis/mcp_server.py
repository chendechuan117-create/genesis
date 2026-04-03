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
from collections import Counter
from typing import Any, Dict

# ─── Database Setup ───

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / ".cascade"
DB_PATH = DB_DIR / "code_observations.db"

VALID_TYPES = {"CONSTRAINT", "COUPLING", "FRAGILITY", "TRADEOFF", "LESSON", "PATTERN"}
VALID_SOURCES = {"inference", "code_review", "runtime_test", "bug_fix", "user_report"}

METADATA_SCHEMA_VERSION = "2"
METADATA_SCHEMA_VERSION_FIELD = "metadata_schema_version"

_VALIDATION_STATUS_ALIASES = {
    "validated": "validated",
    "verified": "validated",
    "tested": "validated",
    "unverified": "unverified",
    "partial": "partial",
    "partial_information": "partial",
    "content-analyzed": "partial",
    "outdated": "outdated",
    "stale": "outdated",
    "low_quality": "low_quality",
}

_KNOWLEDGE_STATE_ALIASES = {
    "current": "current",
    "active": "current",
    "latest": "current",
    "historical": "historical",
    "history": "historical",
    "outdated": "historical",
    "stale": "historical",
    "superseded": "historical",
    "archived": "historical",
    "unverified": "unverified",
    "tentative": "unverified",
    "experimental": "unverified",
    "hypothesis": "unverified",
}

_INVALIDATION_REASON_ALIASES = {
    "superseded_env": "superseded_env",
    "superseded_epoch": "superseded_env",
    "environment_superseded": "superseded_env",
    "audit_outdated": "audit_outdated",
    "audited_outdated": "audit_outdated",
    "verifier_outdated": "audit_outdated",
    "manual_outdated": "manual_outdated",
    "manual": "manual_outdated",
}

_ENVIRONMENT_SCOPE_ALIASES = {
    "doctor": "doctor_workspace",
    "doctor sandbox": "doctor_workspace",
    "doctor_sandbox": "doctor_workspace",
    "doctor-workspace": "doctor_workspace",
    "doctor workspace": "doctor_workspace",
    "workspace": "doctor_workspace",
}

_SIGNATURE_RENDER_ORDER = (
    "component",
    "language",
    "framework",
    "runtime",
    METADATA_SCHEMA_VERSION_FIELD,
    "observed_environment_scope",
    "applies_to_environment_scope",
    "validation_status",
    "knowledge_state",
    "invalidation_reason",
)

_DIGEST_SIGNATURE_KEYS = (
    "component",
    "language",
    "framework",
    "runtime",
    "applies_to_environment_scope",
    "observed_environment_scope",
    "validation_status",
    "invalidation_reason",
)

_QUERY_SIGNATURE_KEYS = (
    "signature",
    "observed_environment_scope",
    "applies_to_environment_scope",
    "validation_status",
    "knowledge_state",
    "invalidation_reason",
)


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


def _clean_metadata_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key or "").strip()
            if not key_text:
                continue
            item_value = _clean_metadata_value(item)
            if item_value in ("", [], {}):
                continue
            cleaned[key_text] = item_value
        return cleaned
    if isinstance(value, (list, tuple, set)):
        cleaned_items = []
        for item in value:
            item_value = _clean_metadata_value(item)
            if item_value in ("", [], {}):
                continue
            cleaned_items.append(item_value)
        return cleaned_items
    return str(value).strip()


def _normalize_environment_scope(scope: Any) -> str:
    value = str(scope or "").strip().lower()
    if not value:
        return ""
    return _ENVIRONMENT_SCOPE_ALIASES.get(value, value)


def _signature_scalar_value(signature: Dict[str, Any], key: str) -> str:
    value = (signature or {}).get(key)
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = str(item or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def _resolve_validation_status(signature: Dict[str, Any]) -> str:
    value = _signature_scalar_value(signature, "validation_status").lower()
    if not value:
        return ""
    return _VALIDATION_STATUS_ALIASES.get(value, value)


def _resolve_knowledge_state(signature: Dict[str, Any]) -> str:
    value = _signature_scalar_value(signature, "knowledge_state").lower()
    if not value:
        return ""
    return _KNOWLEDGE_STATE_ALIASES.get(value, value)


def _resolve_invalidation_reason(signature: Dict[str, Any]) -> str:
    value = _signature_scalar_value(signature, "invalidation_reason").lower()
    if not value:
        return ""
    return _INVALIDATION_REASON_ALIASES.get(value, value)


def _bind_environment_aliases(signature: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(signature or {})
    observed_scope = _normalize_environment_scope(normalized.get("observed_environment_scope"))
    observed_epoch = _signature_scalar_value(normalized, "observed_environment_epoch")
    applicable_scope = _normalize_environment_scope(
        normalized.get("applies_to_environment_scope") or normalized.get("environment_scope")
    )
    applicable_epoch = _signature_scalar_value(normalized, "applies_to_environment_epoch") or _signature_scalar_value(normalized, "environment_epoch")

    if observed_scope:
        normalized["observed_environment_scope"] = observed_scope
        if observed_epoch:
            normalized["observed_environment_epoch"] = observed_epoch
        else:
            normalized.pop("observed_environment_epoch", None)
    else:
        normalized.pop("observed_environment_scope", None)
        normalized.pop("observed_environment_epoch", None)

    if applicable_scope:
        normalized["applies_to_environment_scope"] = applicable_scope
        normalized["environment_scope"] = applicable_scope
        if applicable_epoch:
            normalized["applies_to_environment_epoch"] = applicable_epoch
            normalized["environment_epoch"] = applicable_epoch
        else:
            normalized.pop("applies_to_environment_epoch", None)
            normalized.pop("environment_epoch", None)
    else:
        normalized.pop("applies_to_environment_scope", None)
        normalized.pop("applies_to_environment_epoch", None)
        normalized.pop("environment_scope", None)
        normalized.pop("environment_epoch", None)
    return normalized


def _normalize_signature(signature: Dict[str, Any], status: str = "active", for_query: bool = False) -> Dict[str, Any]:
    normalized = {}
    for key, value in (signature or {}).items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        cleaned = _clean_metadata_value(value)
        if cleaned in ("", [], {}):
            continue
        normalized[key_text] = cleaned

    status_token = str(status or "").strip().lower()
    if not normalized and (for_query or status_token not in {"invalidated", "superseded"}):
        return {}

    normalized = _bind_environment_aliases(normalized)

    validation_status = _resolve_validation_status(normalized)
    knowledge_state = _resolve_knowledge_state(normalized)
    invalidation_reason = _resolve_invalidation_reason(normalized)

    if validation_status:
        normalized["validation_status"] = validation_status
    else:
        normalized.pop("validation_status", None)

    if knowledge_state:
        normalized["knowledge_state"] = knowledge_state
    else:
        normalized.pop("knowledge_state", None)

    if not for_query and status_token in {"invalidated", "superseded"} and not invalidation_reason:
        invalidation_reason = "manual_outdated"

    if invalidation_reason:
        normalized["invalidation_reason"] = invalidation_reason
        if not for_query:
            normalized["validation_status"] = "outdated"
            normalized["knowledge_state"] = "historical"
    else:
        normalized.pop("invalidation_reason", None)

    if not for_query:
        if normalized.get("validation_status") == "outdated":
            normalized["knowledge_state"] = "historical"
        elif normalized.get("validation_status") == "unverified" and not normalized.get("knowledge_state"):
            normalized["knowledge_state"] = "unverified"
        normalized[METADATA_SCHEMA_VERSION_FIELD] = METADATA_SCHEMA_VERSION

    resolved_state = _resolve_knowledge_state(normalized)
    if resolved_state:
        normalized["knowledge_state"] = resolved_state
    else:
        normalized.pop("knowledge_state", None)

    return normalized


def _encode_signature(signature: Dict[str, Any], status: str = "active") -> str:
    return json.dumps(_normalize_signature(signature, status=status), ensure_ascii=False, sort_keys=True)


def _decode_signature(encoded_signature: Any, status: str = "active") -> Dict[str, Any]:
    if isinstance(encoded_signature, dict):
        payload = encoded_signature
    elif not encoded_signature:
        payload = {}
    else:
        try:
            payload = json.loads(encoded_signature)
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return _normalize_signature(payload, status=status)


def _signature_values(signature: Dict[str, Any], key: str):
    value = (signature or {}).get(key)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values = []
        for item in value:
            item_text = str(item or "").strip()
            if item_text:
                values.append(item_text)
        return values
    value_text = str(value).strip()
    return [value_text] if value_text else []


def _render_signature(signature: Dict[str, Any]) -> str:
    if not signature:
        return "-"
    parts = []
    seen = set()
    for key in _SIGNATURE_RENDER_ORDER:
        values = _signature_values(signature, key)
        if not values:
            continue
        seen.add(key)
        for value in values:
            parts.append(f"{key}={value}")
    for key in sorted(signature):
        if key in seen:
            continue
        for value in _signature_values(signature, key):
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "-"


def _counter_text(counter: Counter, limit: int = 5) -> str:
    rendered_counter = []
    for value, count in counter.most_common(limit):
        rendered_counter.append(f"{value}({count})")
    return " | ".join(rendered_counter) if rendered_counter else "-"


def _collect_query_signature(args: Dict[str, Any]) -> Dict[str, Any]:
    signature = dict(args.get("signature") or {}) if isinstance(args.get("signature") or {}, dict) else {}
    for key in _QUERY_SIGNATURE_KEYS:
        if key == "signature":
            continue
        value = args.get(key)
        if value not in (None, ""):
            signature[key] = value
    return _normalize_signature(signature, for_query=True)


def _signature_matches(signature: Dict[str, Any], query_signature: Dict[str, Any]) -> bool:
    if not query_signature:
        return True
    for key in query_signature:
        node_values = {value.lower() for value in _signature_values(signature, key)}
        query_values = {value.lower() for value in _signature_values(query_signature, key)}
        if query_values and not (node_values & query_values):
            return False
    return True


def record_code_observation(conn, args):
    obs_type = (args.get("type") or "").upper()
    if obs_type not in VALID_TYPES:
        return f"Invalid type '{obs_type}'. Must be one of: {', '.join(sorted(VALID_TYPES))}"

    title = (args.get("title") or "").strip()
    content = (args.get("content") or "").strip()
    if not title or not content:
        return "Both 'title' and 'content' are required."

    obs_id = _gen_id(obs_type)
    signature_dict = _decode_signature(args.get("signature", "{}"), "active")
    source = args.get("source", "inference")
    if source not in VALID_SOURCES:
        source = "inference"
    confidence = max(0.1, min(1.0, float(args.get("confidence", 0.8))))

    encoded_signature = _encode_signature(signature_dict, "active")

    conn.execute(
        """INSERT INTO code_observations
           (id, type, title, content, why_important, file_path, function_name, signature, confidence, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (obs_id, obs_type, title, content,
         args.get("why_important", ""),
         args.get("file_path", ""),
         args.get("function_name", ""),
         encoded_signature, confidence, source)
    )
    conn.commit()
    return json.dumps({
        "id": obs_id,
        "status": "recorded",
        "type": obs_type,
        "confidence": confidence,
        "signature": signature_dict,
    }, ensure_ascii=False)


def search_code_observations(conn, args):
    query = (args.get("query") or "").strip()
    obs_type = (args.get("type") or "").upper() or None
    file_path = (args.get("file_path") or "").strip() or None
    component = (args.get("component") or "").strip() or None
    status = args.get("status", "active")
    query_signature = _collect_query_signature(args)

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
            ORDER BY confidence DESC, updated_at DESC LIMIT 100""",
        params
    ).fetchall()

    filtered_rows = []
    for row in rows:
        sig = _decode_signature(row["signature"], status=row["status"] if "status" in row.keys() else status)
        if not _signature_matches(sig, query_signature):
            continue
        filtered_rows.append((row, sig))
        if len(filtered_rows) >= 20:
            break

    if not filtered_rows:
        return "No observations found matching your criteria."

    results = []
    for r, sig in filtered_rows:
        sig_text = _render_signature(sig)
        entry = f"[{r['type']}] {r['title']}  (id: {r['id']})\n"
        entry += f"  confidence={r['confidence']:.2f} | source={r['source']} | file={r['file_path'] or 'N/A'}"
        if r["function_name"]:
            entry += f" | func={r['function_name']}"
        entry += f"\n  sig: {sig_text}\n"
        entry += f"  {r['content'][:300]}{'...' if len(r['content']) > 300 else ''}"
        if r["why_important"]:
            entry += f"\n  WHY: {r['why_important'][:200]}"
        results.append(entry)

    return f"Found {len(filtered_rows)} observations:\n\n" + "\n\n".join(results)


def get_observation(conn, args):
    obs_id = (args.get("id") or "").strip()
    if not obs_id:
        return "Parameter 'id' is required."

    row = conn.execute("SELECT * FROM code_observations WHERE id = ?", (obs_id,)).fetchone()
    if not row:
        return f"Observation '{obs_id}' not found."

    result = {k: row[k] for k in row.keys()}
    result["signature"] = _decode_signature(result["signature"], status=result.get("status") or "active")

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

    row = conn.execute("SELECT id, confidence, signature FROM code_observations WHERE id = ?", (obs_id,)).fetchone()
    if not row:
        return f"Observation '{obs_id}' not found."

    new_conf = min(1.0, row["confidence"] + 0.1)
    source = args.get("source", "code_review")
    signature = _decode_signature(row["signature"], status="active")
    signature["validation_status"] = "validated"
    signature["knowledge_state"] = "current"
    signature.pop("invalidation_reason", None)
    signature.pop("invalidation_note", None)
    encoded_signature = _encode_signature(signature, status="active")

    conn.execute(
        "UPDATE code_observations SET confidence = ?, source = ?, status = 'active', signature = ?, updated_at = datetime('now') WHERE id = ?",
        (new_conf, source, encoded_signature, obs_id)
    )
    conn.commit()
    return json.dumps({
        "id": obs_id,
        "old_confidence": row["confidence"],
        "new_confidence": new_conf,
        "status": "verified",
        "signature": _decode_signature(encoded_signature, status="active"),
    }, ensure_ascii=False)


def invalidate_observation(conn, args):
    obs_id = (args.get("id") or "").strip()
    reason = args.get("reason", "code changed")
    if not obs_id:
        return "Parameter 'id' is required."

    row = conn.execute("SELECT id, signature FROM code_observations WHERE id = ?", (obs_id,)).fetchone()
    if not row:
        return f"Observation '{obs_id}' not found."

    signature = _decode_signature(row["signature"], status="invalidated")
    signature["invalidation_reason"] = args.get("invalidation_reason") or signature.get("invalidation_reason") or "manual_outdated"
    signature["invalidation_note"] = str(reason or "").strip()
    encoded_signature = _encode_signature(signature, status="invalidated")

    conn.execute(
        "UPDATE code_observations SET status = 'invalidated', confidence = confidence * 0.3, signature = ?, updated_at = datetime('now') WHERE id = ?",
        (encoded_signature, obs_id)
    )
    conn.commit()
    return json.dumps({
        "id": obs_id,
        "status": "invalidated",
        "reason": reason,
        "signature": _decode_signature(encoded_signature, status="invalidated"),
    }, ensure_ascii=False)


def get_code_digest(conn, _args):
    total_rows = conn.execute(
        "SELECT id, type, title, confidence, file_path, function_name, signature, status FROM code_observations"
    ).fetchall()
    total = sum(1 for row in total_rows if row["status"] == "active")
    if not total_rows:
        return "No observations recorded yet. Use record_code_observation to document code facts."

    type_rows = conn.execute(
        "SELECT type, COUNT(*) as cnt, ROUND(AVG(confidence),2) as avg_conf FROM code_observations WHERE status = 'active' GROUP BY type ORDER BY cnt DESC"
    ).fetchall()

    status_rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM code_observations GROUP BY status ORDER BY cnt DESC"
    ).fetchall()

    file_rows = conn.execute(
        "SELECT file_path, COUNT(*) as cnt FROM code_observations WHERE status = 'active' AND file_path != '' GROUP BY file_path ORDER BY cnt DESC LIMIT 10"
    ).fetchall()

    top = conn.execute(
        "SELECT id, type, title, confidence, file_path, function_name FROM code_observations WHERE status = 'active' ORDER BY confidence DESC LIMIT 10"
    ).fetchall()

    lines = [f"=== Code Observations Digest ===", f"Total: {total} active\n"]

    if status_rows:
        status_parts = [f"{r['status']}({r['cnt']})" for r in status_rows]
        lines.append(f"By Status: {' | '.join(status_parts)}\n")

    type_parts = [f"{r['type']}({r['cnt']}, avg:{r['avg_conf']})" for r in type_rows]
    lines.append(f"By Type: {' | '.join(type_parts)}\n")

    if file_rows:
        file_parts = [f"{Path(r['file_path']).name}({r['cnt']})" for r in file_rows]
        lines.append(f"By File: {' | '.join(file_parts)}\n")

    signature_counters = {key: Counter() for key in _DIGEST_SIGNATURE_KEYS}
    for row in total_rows:
        if row["status"] != "active":
            continue
        signature = _decode_signature(row["signature"], status=row["status"])
        for key in _DIGEST_SIGNATURE_KEYS:
            for value in _signature_values(signature, key):
                signature_counters[key][value] += 1

    metadata_lines = []
    for key in _DIGEST_SIGNATURE_KEYS:
        rendered = _counter_text(signature_counters[key])
        if rendered != "-":
            metadata_lines.append(f"  {key}: {rendered}")
    if metadata_lines:
        lines.append("Metadata Lanes:")
        lines.extend(metadata_lines)
        lines.append("")

    lines.append("Top Observations:")
    for r in top:
        loc = r["function_name"] or (Path(r["file_path"]).name if r["file_path"] else "N/A")
        lines.append(f"  [{r['confidence']:.2f}] [{r['type']}] {r['title']} ({loc})")

    lines.append("")
    lines.append("Preferred metadata fields:")
    lines.append("  component | language | framework | runtime | observed_environment_scope | applies_to_environment_scope")
    lines.append("  validation_status | knowledge_state | invalidation_reason")
    lines.append("")
    lines.append("Structured search:")
    lines.append('  search_code_observations({"signature": {"component": "parser", "language": "python"}})')
    lines.append("  observed_environment_scope = where the fact was observed")
    lines.append("  applies_to_environment_scope = where the fact should be reused")

    return "\n".join(lines)


def get_file_observations(conn, args):
    file_path = (args.get("file_path") or "").strip()
    if not file_path:
        return "Parameter 'file_path' is required."

    fname = Path(file_path).name
    rows = conn.execute(
        """SELECT id, type, title, content, why_important, function_name, signature, confidence, source
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
        signature = _decode_signature(r["signature"], status="active")
        if signature:
            entry += f"\n  sig: {_render_signature(signature)}"
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
        "description": "Record a verified fact about the codebase: hidden constraints, implicit coupling, design tradeoffs, fragile patterns, or lessons from debugging. Prefer structured signature metadata so a blank LLM can reuse the fact efficiently later.",
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
                "signature": {"type": "object", "description": "Scoping metadata. Preferred keys: component, language, framework, runtime, observed_environment_scope, applies_to_environment_scope, validation_status, knowledge_state, invalidation_reason. metadata_schema_version is auto-filled to v2.",
                              "additionalProperties": True},
                "confidence": {"type": "number", "description": "0.0-1.0 certainty (default 0.8)"},
                "source": {"type": "string", "enum": ["inference", "code_review", "runtime_test", "bug_fix", "user_report"]}
            },
            "required": ["type", "title", "content"]
        }
    },
    {
        "name": "search_code_observations",
        "description": "Search known observations. Use structured signature filters before modifying code so an empty LLM can target the right constraints instead of relying on vague text search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text search across title/content/why_important"},
                "type": {"type": "string", "enum": ["CONSTRAINT", "COUPLING", "FRAGILITY", "TRADEOFF", "LESSON", "PATTERN"]},
                "file_path": {"type": "string", "description": "Filter by file (partial match)"},
                "component": {"type": "string", "description": "Filter by component (searches signature, file, function)"},
                "signature": {"type": "object", "description": "Exact-ish structured metadata filter. Example: {component, language, applies_to_environment_scope, validation_status}.", "additionalProperties": True},
                "observed_environment_scope": {"type": "string", "description": "Convenience filter for the environment where the fact was observed"},
                "applies_to_environment_scope": {"type": "string", "description": "Convenience filter for the environment where the fact should be reused"},
                "validation_status": {"type": "string", "description": "validated | unverified | partial | outdated"},
                "knowledge_state": {"type": "string", "description": "current | unverified | historical"},
                "invalidation_reason": {"type": "string", "description": "manual_outdated | audit_outdated | superseded_env"},
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
        "description": "Confirm an observation is still valid. Boosts confidence +0.1 (max 1.0) and restores metadata state to validated/current.",
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
        "description": "Mark an observation as no longer valid (code refactored, bug fixed, etc.). Also records metadata invalidation_reason for retrieval hygiene.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "reason": {"type": "string", "description": "Why invalidated"},
                "invalidation_reason": {"type": "string", "enum": ["manual_outdated", "audit_outdated", "superseded_env"], "description": "Optional canonical invalidation reason; defaults to manual_outdated"}
            },
            "required": ["id", "reason"]
        }
    },
    {
        "name": "get_code_digest",
        "description": "Overview of all known code observations. Use at START of session to see known types, metadata lanes, and the preferred structured search pattern.",
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
            "serverInfo": {"name": "genesis-nodevault", "version": "2.1.0"},
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
    sys.stderr.write(f"Genesis Code Metainfo MCP Server v2.1 started. DB: {DB_PATH}\n")
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
