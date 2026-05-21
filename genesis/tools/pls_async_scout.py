import asyncio
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from genesis.v4.manager import NodeVault
from genesis.tools.pls_query_tool import PLSQueryTool


DEFAULT_SCOUT_MODES: Tuple[str, ...] = (
    "basis",
    "frontier",
    "saturation",
    "contradictions",
    "potential",
    "ablation",
)

DEFAULT_BRANCH_MODES: Tuple[str, ...] = DEFAULT_SCOUT_MODES


_NUMERIC_PREFIX_RE = re.compile(r"^\s*(?:\d+\s+in\s+\||usage=|links=|active=|ratio=|total=|rows=|seen=|nodes\(|reasoning_lines|node_edges|potential_samples|open_void_tasks|ablation_)")
_COUNT_ASSIGN_RE = re.compile(r"\b(?:in|incoming|rl_out|edges|usage|links|count|nodes|reasoning_lines|node_edges|potential_samples|ratio|active|total|rows|seen|missing_dedupe|active_open|actionable_open|non_actionable_open)=\d")
_METRIC_COLON_RE = re.compile(r"^[a-zA-Z_]+:\s*\d+(?:\.\d+)?$")
_DISTRIBUTION_COUNT_RE = re.compile(r":\s*\d+(?:\.\d+)?$")


def _strip_numeric_terrain(line: str) -> str:
    text = re.sub(r"\s+", " ", str(line or "")).strip()
    if not text:
        return ""
    if text.startswith("[PLS DB]"):
        return ""
    if text.startswith("==="):
        return ""
    if text.startswith("--"):
        return ""
    if text == "(none)":
        return ""
    if text.startswith("dedupe:"):
        return ""
    if _NUMERIC_PREFIX_RE.search(text):
        return ""
    text = re.sub(r"\b\d+\s+in\s+\|\s*", "", text)
    text = re.sub(r"\b(?:rl_out|edges|usage|links|incoming|basis_set)=\S+\s*\|\s*", "", text)
    text = re.sub(r"\b(?:rl_out|edges|usage|links|incoming|basis_set)=\S+", "", text)
    text = re.sub(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*\|\s*", "", text)
    text = re.sub(r"^(?:actionable|structural|exit|noise)\s+\|\s+(?:open|actionable|observed|resolved|ignored|rejected|stale|noise|crystallized)\s+\|\s*", "", text)
    text = re.sub(r"^seen=\S+\s*\|\s*", "", text)
    text = re.sub(r"^last_seen=[^|]+\|\s*", "", text)
    text = re.sub(r"^[^|]+ / [^|]+\s*\|\s*", "", text)
    if _COUNT_ASSIGN_RE.search(text):
        return ""
    if _METRIC_COLON_RE.search(text):
        return ""
    if "|" in text and _DISTRIBUTION_COUNT_RE.search(text):
        return ""
    return text.strip(" |")


def _compact_section(mode: str, raw: str, limit: int = 4) -> List[str]:
    items: List[str] = []
    for line in str(raw or "").splitlines():
        item = _strip_numeric_terrain(line)
        if not item:
            continue
        if item in items:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _label_for_mode(mode: str) -> str:
    labels = {
        "frontier": "探索前沿",
        "saturation": "饱和提醒",
        "contradictions": "证伪/衰减",
        "potential": "可验证势",
        "ablation": "消融可见性",
        "basis": "基础锚点",
        "basin": "盆地摘要",
        "theme": "主题局部面",
    }
    return labels.get(mode, mode)


def _run_scout_query_sync(mode: str, limit: int, since: str = "") -> Tuple[str, str]:
    tool = PLSQueryTool()
    try:
        result = asyncio.run(tool.execute(mode=mode, limit=limit, since=since, include_same_round=False))
        return mode, result
    except Exception as exc:
        return mode, f"PLS scout failed: {exc}"


async def _run_scout_query(mode: str, limit: int, since: str = "") -> Tuple[str, str]:
    return await asyncio.to_thread(_run_scout_query_sync, mode, limit, since)


async def build_pls_terrain_brief(limit: int = 6, since: str = "", modes: Tuple[str, ...] = DEFAULT_SCOUT_MODES) -> str:
    tasks = [_run_scout_query(mode, limit, since=since) for mode in modes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    compacted: Dict[str, List[str]] = {}
    for result in results:
        if isinstance(result, Exception):
            continue
        mode, raw = result
        items = _compact_section(mode, raw, limit=4)
        if items:
            compacted[mode] = items
    sections: List[str] = []
    for mode in modes:
        items = compacted.get(mode)
        if not items:
            continue
        sections.append(f"- {_label_for_mode(mode)}：" + "；".join(items))

    if not sections:
        return ""
    return "[PLS 地形摘要｜只读并发 scout，不代表事实或任务]\n" + "\n".join(sections)


def build_pls_terrain_brief_sync(limit: int = 6, since: str = "") -> str:
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(build_pls_terrain_brief(limit=limit, since=since))
        return ""
    except Exception:
        return ""


def _first_item(sections: Dict[str, List[str]], mode: str) -> str:
    items = sections.get(mode) or []
    return items[0] if items else ""


def _format_branch(name: str, focus: str, seed: str, guard: str) -> str:
    if not seed:
        return ""
    return f"- {name}：{focus}；候选线索：{seed}；边界：{guard}"


def _proposal_id(branch_id: str, seed: str, parent_trace_id: str = "", parent_round_seq: int = None) -> str:
    raw = f"{branch_id}|{seed}|{parent_trace_id}|{parent_round_seq}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"PLSP_{digest}"


def _proposal_payload(branch_id: str, focus: str, seed: str, guard: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "node_id": "",
        "title": f"{branch_id}: {focus[:80]}",
        "content": seed,
        "point_type": "CONTEXT",
        "tags": "async_proposal,pls_potential",
        "resolves": focus,
        "reasoning": guard,
        "basis_ids": [],
        "origin": {
            "branch_id": branch_id,
            "seed": seed,
            "guard": guard,
        },
        "extra": {},
    }


def _branch_specs(sections: Dict[str, List[str]]) -> List[Dict[str, str]]:
    specs = [
        {
            "branch_id": "basis_branch",
            "focus": "从稳固基础中选一个概念锚点，复用后推进到新的 why/what/how/boundary/failure/practice 切面",
            "seed": _first_item(sections, "basis"),
            "guard": "不要把基础锚点本身当成新发现",
        },
        {
            "branch_id": "frontier_branch",
            "focus": "从未被充分复用的探索前沿中选一条，先验证其 basis 再决定是否记录新点",
            "seed": _first_item(sections, "frontier"),
            "guard": "同轮联想不能当作独立验证",
        },
        {
            "branch_id": "falsify_branch",
            "focus": "优先处理矛盾、证伪债或正在衰减的旧知识",
            "seed": _first_item(sections, "contradictions"),
            "guard": "只在证据充分时连 CONTRADICTS，不要为反驳而反驳",
        },
        {
            "branch_id": "exit_branch",
            "focus": "从可验证势或出口势中挑一个相邻概念缺口，避免继续原地深挖",
            "seed": _first_item(sections, "potential"),
            "guard": "势只是注意力候选，不是事实或任务",
        },
        {
            "branch_id": "avoid_saturation_branch",
            "focus": "若当前方向靠近饱和或隐藏节点，转向未饱和邻域",
            "seed": _first_item(sections, "saturation") or _first_item(sections, "ablation"),
            "guard": "不要验证 VIRT 本身，也不要依赖已隐藏节点作为新 basis",
        },
    ]
    return [spec for spec in specs if spec.get("seed")]


async def _collect_branch_sections(limit: int, since: str, modes: Tuple[str, ...]) -> Dict[str, List[str]]:
    tasks = [_run_scout_query(mode, limit, since=since) for mode in modes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    sections: Dict[str, List[str]] = {}
    for result in results:
        if isinstance(result, Exception):
            continue
        mode, raw = result
        items = _compact_section(mode, raw, limit=4)
        if items:
            sections[mode] = items
    return sections


def _ensure_pls_proposals_table(conn: sqlite3.Connection) -> None:
    conn.execute('''
    CREATE TABLE IF NOT EXISTS pls_proposals (
        proposal_id TEXT PRIMARY KEY,
        parent_trace_id TEXT,
        parent_round_seq INTEGER,
        branch_id TEXT,
        proposal_type TEXT NOT NULL,
        source TEXT DEFAULT 'async_branch',
        payload_json TEXT NOT NULL,
        basis_ids_json TEXT,
        status TEXT DEFAULT 'pending',
        merge_result TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pls_proposals)").fetchall()]
    for col_name, col_def in [
        ("parent_trace_id", "TEXT"),
        ("parent_round_seq", "INTEGER"),
        ("branch_id", "TEXT"),
        ("source", "TEXT DEFAULT 'async_branch'"),
        ("basis_ids_json", "TEXT"),
        ("status", "TEXT DEFAULT 'pending'"),
        ("merge_result", "TEXT"),
    ]:
        if col_name not in cols:
            conn.execute(f"ALTER TABLE pls_proposals ADD COLUMN {col_name} {col_def}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pls_proposals_status_created ON pls_proposals(status, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pls_proposals_branch_created ON pls_proposals(branch_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pls_proposals_parent ON pls_proposals(parent_trace_id, parent_round_seq)")


def _record_pls_proposal_direct(
    db_path: Path,
    proposal_id: str,
    payload: Dict[str, Any],
    parent_trace_id: str = "",
    parent_round_seq: int = None,
    branch_id: str = "",
) -> bool:
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            _ensure_pls_proposals_table(conn)
            cur = conn.execute(
                "INSERT OR IGNORE INTO pls_proposals "
                "(proposal_id, parent_trace_id, parent_round_seq, branch_id, proposal_type, source, payload_json, basis_ids_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    proposal_id,
                    parent_trace_id or None,
                    parent_round_seq,
                    branch_id,
                    "branch_candidate",
                    "async_branch_worker",
                    json.dumps(payload, ensure_ascii=False),
                    "[]",
                ),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False


async def build_pls_branch_proposals(limit: int = 6, since: str = "", modes: Tuple[str, ...] = DEFAULT_BRANCH_MODES) -> str:
    sections = await _collect_branch_sections(limit, since, modes)
    lines = [
        _format_branch(spec["branch_id"], spec["focus"], spec["seed"], spec["guard"])
        for spec in _branch_specs(sections)
    ]
    if not lines:
        return ""
    return "[PLS Branch Proposals｜只读候选，不落库，不代表事实]\n" + "\n".join(lines)


def _stage_pls_branch_proposals_sync(
    parent_trace_id: str = "",
    parent_round_seq: int = None,
    limit: int = 6,
    since: str = "",
    db_path: str = "",
    modes: Tuple[str, ...] = DEFAULT_BRANCH_MODES,
) -> str:
    try:
        sections = asyncio.run(_collect_branch_sections(limit, since, modes))
        specs = _branch_specs(sections)
        if not specs:
            return ""
        vault = None if db_path else NodeVault(skip_vector_engine=True)
        direct_db_path = Path(db_path).expanduser() if db_path else None
        staged = 0
        for spec in specs:
            proposal_id = _proposal_id(spec["branch_id"], spec["seed"], parent_trace_id, parent_round_seq)
            payload = _proposal_payload(spec["branch_id"], spec["focus"], spec["seed"], spec["guard"])
            if direct_db_path is not None:
                ok = _record_pls_proposal_direct(
                    direct_db_path,
                    proposal_id=proposal_id,
                    payload=payload,
                    parent_trace_id=parent_trace_id,
                    parent_round_seq=parent_round_seq,
                    branch_id=spec["branch_id"],
                )
            else:
                ok = vault.record_pls_proposal(
                    proposal_id=proposal_id,
                    proposal_type="branch_candidate",
                    payload=payload,
                    basis_ids=[],
                    parent_trace_id=parent_trace_id or None,
                    parent_round_seq=parent_round_seq,
                    branch_id=spec["branch_id"],
                    source="async_branch_worker",
                )
            if ok:
                staged += 1
        if not staged:
            return ""
        return f"[PLS Proposal Staging｜已暂存 {staged} 条候选，仅 staging，不代表事实]"
    except Exception:
        return ""


async def stage_pls_branch_proposals(
    parent_trace_id: str = "",
    parent_round_seq: int = None,
    limit: int = 6,
    since: str = "",
    db_path: str = "",
    modes: Tuple[str, ...] = DEFAULT_BRANCH_MODES,
) -> str:
    return await asyncio.to_thread(_stage_pls_branch_proposals_sync, parent_trace_id, parent_round_seq, limit, since, db_path, modes)


def build_pls_branch_proposals_sync(limit: int = 6, since: str = "") -> str:
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(build_pls_branch_proposals(limit=limit, since=since))
        return ""
    except Exception:
        return ""
