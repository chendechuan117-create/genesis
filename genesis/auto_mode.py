"""
Genesis V4 — Auto Mode
自主改进模式的核心逻辑：信号收集、前沿追踪、KB delta 观测、Doctor 沙箱同步。
从 discord_bot.py 提取，减少主文件复杂度。
"""

import os
import re
import json
import sqlite3
import time as _time_module
import asyncio
import logging
from pathlib import Path

import discord

from genesis.core.models import CallbackEvent
from genesis.v4.manager import NodeVault

logger = logging.getLogger("DiscordBot.Auto")


# ─── Utilities ───────────────────────────────────────────────────

def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(f"Invalid {name}={raw!r}; fallback to {default}")
        return default
    return max(minimum, value)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    logger.warning(f"Invalid {name}={raw!r}; fallback to {default}")
    return default


# ─── Constants ───────────────────────────────────────────────────

AUTO_MAX_ROUNDS = _env_int("GENESIS_AUTO_MAX_ROUNDS", 0, minimum=0)
AUTO_DRY_LIMIT = _env_int("GENESIS_AUTO_DRY_LIMIT", 0, minimum=0)
AUTO_SLEEP_BASE = _env_int("GENESIS_AUTO_SLEEP_BASE", 8, minimum=0)
AUTO_DRY_SLEEP_BASE = _env_int("GENESIS_AUTO_DRY_SLEEP_BASE", 15, minimum=0)
AUTO_DRY_SLEEP_STEP = _env_int("GENESIS_AUTO_DRY_SLEEP_STEP", 5, minimum=0)
AUTO_ROUND_TIMEOUT_SECS = _env_int("GENESIS_AUTO_ROUND_TIMEOUT_SECS", 0, minimum=0)
AUTO_SYNC_DOCTOR_SANDBOX = _env_bool("GENESIS_AUTO_SYNC_DOCTOR_SANDBOX", True)
AUTO_DOCTOR_SYNC_TIMEOUT_SECS = _env_int("GENESIS_AUTO_DOCTOR_SYNC_TIMEOUT_SECS", 420, minimum=30)

AUTO_PROMPT_FIRST = """你正在执行自主探索任务。

## 用户方向
{directive}

## 本轮任务
1. 先用 `search_knowledge_nodes` 搜索知识库中与方向相关的已有知识，避免重复劳动
2. 使用可用工具（shell、读写文件等）进行探索和调研
3. 将新发现记录到知识库（调用 `record_lesson_node`）
4. 如果发现值得深入的子方向，在回复中标注供下轮继续

## 规则
- 围绕用户方向行动，不要偏离主题
- 每轮聚焦一个具体子目标，做到位
- 先搜后写：记录前先确认知识库中没有同类知识
- 如果方向过于宽泛，先拆分为可执行的子步骤

当前系统信号（仅供参考）：
{signals}"""

AUTO_PROMPT_CONTINUE = """继续自主探索。不要重复上一轮已完成的工作。

## 用户方向
{directive}

上一轮工作记忆：
{knowledge_state}

上一轮探索前沿：
{frontier_state}

{history}

## 续跑原则
- 沿上一轮的前沿继续深入
- 如果上一轮遗留了未解决的问题，优先处理
- 先用 `search_knowledge_nodes` 确认相关知识，再用 `record_lesson_node` 记录新发现
- 每轮聚焦一个子目标，做到位

当前信号（仅供参考）：
{signals}"""


AUTO_DEFAULT_DIRECTIVE = ("基于当前系统信号和知识库状态，"
    "选择最有价值的改进方向进行自主探索。"
    "优先处理：知识空洞(VOID)填充、过时知识更新、系统效率优化。")

_ERROR_RESPONSE_PATTERNS = [
    "V4 Execution Error",
    "LLM provider 连续",
    "API Error",
    "无效的令牌",
    "API 可能已下线",
    "rate_limit",
    "RateLimitError",
]

def _is_error_response(response: str, tokens: int = 0) -> bool:
    """检测 V4 loop 返回的是否是错误信息而非真正的 LLM 输出。"""
    if not response or not response.strip():
        return True
    if tokens == 0 and len(response.strip()) < 500:
        return True
    return any(p in response for p in _ERROR_RESPONSE_PATTERNS)


# ─── Doctor Sandbox ──────────────────────────────────────────────

async def _run_doctor_sync_command(*args: str, timeout_secs: int = AUTO_DOCTOR_SYNC_TIMEOUT_SECS) -> tuple[bool, str]:
    project_dir = Path(__file__).resolve().parent.parent
    script_path = project_dir / "scripts" / "doctor.sh"
    if not script_path.exists():
        return False, f"$ ./scripts/doctor.sh {' '.join(args)}\nmissing script: {script_path}"
    proc = await asyncio.create_subprocess_exec(
        str(script_path), *args, cwd=str(project_dir),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_secs)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return False, f"$ ./scripts/doctor.sh {' '.join(args)}\n[timeout after {timeout_secs}s]"
    output = stdout.decode("utf-8", errors="replace").strip()
    header = f"$ ./scripts/doctor.sh {' '.join(args)}"
    if output:
        return proc.returncode == 0, f"{header}\n{output}"
    return proc.returncode == 0, f"{header}\n(exit={proc.returncode})"


async def _sync_doctor_sandbox() -> tuple[bool, str]:
    reset_ok, reset_summary = await _run_doctor_sync_command("reset")
    sections = [reset_summary]
    if not reset_ok:
        return False, "\n\n".join(sections)
    status_timeout = min(AUTO_DOCTOR_SYNC_TIMEOUT_SECS, 120)
    status_ok, status_summary = await _run_doctor_sync_command("status", timeout_secs=status_timeout)
    sections.append(status_summary)
    if not status_ok:
        return False, "\n\n".join(sections)
    try:
        epoch_result = NodeVault().activate_environment_epoch(
            "doctor_workspace", origin="auto_sync", snapshot_summary=status_summary[-500:],
        )
        sections.append(
            "environment_epoch\n"
            f"scope=doctor_workspace\n"
            f"active={epoch_result['epoch_id']}\n"
            f"previous={epoch_result.get('previous_epoch_id') or 'none'}\n"
            f"invalidated_nodes={epoch_result.get('invalidated_nodes', 0)}"
        )
    except Exception as e:
        logger.error(f"Doctor sandbox epoch activation failed: {e}", exc_info=True)
        sections.append(f"environment_epoch\nerror={e}")
    return True, "\n\n".join(sections)


def _reset_provider(agent):
    """每轮行动前强制回到首选 provider，避免残留 failover 影响 /auto。"""
    try:
        router = agent.provider
        preferred = getattr(router, "_preferred_provider_name", "aixj")
        active = getattr(router, "active_provider_name", "")
        providers = getattr(router, "providers", {}) or {}
        if active != preferred and preferred in providers:
            router._switch_provider(preferred)
            router._failover_time = 0
            logger.info(f"/auto provider reset | {active} -> {preferred}")
    except Exception as e:
        logger.warning(f"/auto provider reset failed: {e}")


# ─── Signal Collection ───────────────────────────────────────────

def _get_auto_signals(round_num: int = 1, session_shown_voids: set | None = None, session_shown_nodes: set | None = None) -> str:
    """从 DB 中收集真实信号，作为 /auto 每轮的外部锚点。
    
    设计原则：确定性代码负责过滤和判断，GP 只看预筛后的可行动条目。
    不暴露原始数值（conf/fail_count）——LLM 无法正确解读数值权重，
    反而会被"失败N次"这类字眼误导去做低价值的紧急响应。
    
    优先级：低置信度节点 > 知识空洞(VOID) > Arena 真正失效的知识
    """
    sections = []
    db = Path.home() / ".genesis" / "workshop_v4.sqlite"
    if db.exists():
        conn = None
        try:
            conn = sqlite3.connect(str(db))

            # ── 1. 低有效置信度节点：用 effective_confidence（读时衰减）而非 raw confidence ──
            # 这样能发现 raw conf 高但长期未验证而衰减致死的节点
            conn.row_factory = sqlite3.Row
            try:
                from genesis.v4.arena_mixin import ArenaConfidenceMixin
                _eff_conf = ArenaConfidenceMixin.effective_confidence
            except ImportError:
                _eff_conf = lambda d: d.get("confidence_score", 0.5)
            candidate_rows = conn.execute(
                "SELECT node_id, title, type, confidence_score, updated_at, last_verified_at, trust_tier "
                "FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV_%' "
                "ORDER BY updated_at DESC LIMIT 200"
            ).fetchall()
            low_eff = []
            for r in candidate_rows:
                d = dict(r)
                if session_shown_nodes and d["node_id"] in session_shown_nodes:
                    continue
                eff = _eff_conf(d)
                if eff < 0.35:
                    low_eff.append((d["node_id"], d["title"], d["type"], eff))
            low_eff.sort(key=lambda x: x[3])
            if low_eff:
                lines = ["[待验证知识 — 有效置信度低于 0.35，可能过时或衰减]"]
                for nid, title, node_type, eff in low_eff[:5]:
                    lines.append(f"  {nid}: {title} (eff:{eff:.2f})")
                    if session_shown_nodes is not None:
                        session_shown_nodes.add(nid)
                sections.append("\n".join(lines))

            # ── 2. 知识空洞(VOID)：已知的未知，填补它们是核心价值 ──
            void_count = conn.execute("SELECT COUNT(*) FROM void_tasks").fetchone()[0]
            if void_count > 0:
                void_page_size = 3
                if session_shown_voids:
                    placeholders = ",".join("?" for _ in session_shown_voids)
                    void_samples = conn.execute(
                        f"SELECT void_id, query FROM void_tasks WHERE void_id NOT IN ({placeholders}) "
                        f"ORDER BY RANDOM() LIMIT {void_page_size}",
                        list(session_shown_voids),
                    ).fetchall()
                    if not void_samples:
                        void_samples = conn.execute(
                            f"SELECT void_id, query FROM void_tasks ORDER BY RANDOM() LIMIT {void_page_size}"
                        ).fetchall()
                else:
                    void_offset = ((round_num - 1) * void_page_size) % max(void_count, 1)
                    void_samples = conn.execute(
                        f"SELECT void_id, query FROM void_tasks ORDER BY created_at DESC LIMIT {void_page_size} OFFSET ?",
                        [void_offset],
                    ).fetchall()
                lines = [f"[知识空洞 — 以下问题在知识库中尚无答案]"]
                for vid, desc in void_samples:
                    lines.append(f"  {desc[:80]}")
                    if session_shown_voids is not None:
                        session_shown_voids.add(vid)
                sections.append("\n".join(lines))

            # ── 3. Arena 真正失效的知识：仅保留低置信+高失败率的条目 ──
            # 高置信节点偶尔失败是环境边界情况，不是知识缺陷，不展示
            rows = conn.execute(
                "SELECT node_id, title "
                "FROM knowledge_nodes "
                "WHERE usage_fail_count > 0 AND confidence_score < 0.7 "
                "ORDER BY usage_fail_count DESC LIMIT 3"
            ).fetchall()
            if rows:
                lines = ["[实践中反复失效的知识 — 需要修正或重写]"]
                for nid, title in rows:
                    lines.append(f"  {nid}: {title}")
                sections.append("\n".join(lines))
        except Exception as e:
            sections.append(f"[DB 查询异常: {e}]")
        finally:
            if conn:
                conn.close()
    log_file = Path("runtime/genesis.log")
    if log_file.exists():
        try:
            from datetime import datetime as _dt, timedelta as _td
            _now = _dt.now()
            _ts_pat = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
            lines = log_file.read_text(errors="replace").splitlines()
            current_errs, historical_errs = [], []
            for l in lines[-500:]:
                if "ERROR" not in l and "Traceback" not in l:
                    continue
                m = _ts_pat.match(l)
                if m:
                    try:
                        age = _now - _dt.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                        if age < _td(hours=6):
                            current_errs.append(l)
                        elif age < _td(hours=48):
                            historical_errs.append(l)
                    except ValueError:
                        current_errs.append(l)
                else:
                    current_errs.append(l)
            if current_errs:
                err_lines = ["[当前运行错误 (<6h) — 优先修复]"]
                for el in current_errs[-5:]:
                    err_lines.append(f"  {el[:150]}")
                sections.append("\n".join(err_lines))
            if historical_errs:
                err_lines = ["[历史错误 (6~48h) — 可能已修复，验证后再行动]"]
                for el in historical_errs[-3:]:
                    err_lines.append(f"  {el[:120]}")
                sections.append("\n".join(err_lines))
        except Exception:
            pass
    if not sections:
        return "[无明显信号 — 系统状态良好]"
    return "\n\n".join(sections)


def _query_kb_delta(since_iso: str) -> dict:
    db = Path.home() / ".genesis" / "workshop_v4.sqlite"
    result = {"new_nodes": [], "updated_nodes": [], "error": None}
    if not db.exists():
        result["error"] = "db_not_found"
        return result
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT node_id, type, title, confidence_score, trust_tier, created_at, updated_at "
                "FROM knowledge_nodes WHERE created_at >= ? ORDER BY created_at", [since_iso],
            ).fetchall()
            result["new_nodes"] = [dict(r) for r in rows]
            rows = conn.execute(
                "SELECT node_id, type, title, confidence_score, trust_tier, updated_at "
                "FROM knowledge_nodes WHERE updated_at >= ? AND created_at < ? ORDER BY updated_at",
                [since_iso, since_iso],
            ).fetchall()
            result["updated_nodes"] = [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        result["error"] = str(e)
    return result


def _get_node_count_status() -> dict:
    try:
        db = Path.home() / ".genesis" / "workshop_v4.sqlite"
        if not db.exists():
            return {"status": "unavailable", "count": None, "detail": f"数据库不存在: {db}"}
        conn = sqlite3.connect(str(db))
        try:
            count = conn.execute("SELECT COUNT(*) FROM knowledge_nodes").fetchone()[0]
        finally:
            conn.close()
        return {"status": "ok", "count": int(count), "detail": None}
    except Exception as e:
        return {"status": "error", "count": None, "detail": str(e)}


def _format_node_telemetry(before: dict, after: dict) -> str:
    if before.get("status") == "ok" and after.get("status") == "ok":
        before_count = before.get("count")
        after_count = after.get("count")
        delta = after_count - before_count
        delta_str = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "±0"
        return f"节点计数观测: {before_count} → {after_count} ({delta_str})"
    after_status = after.get("status")
    if after_status == "unavailable":
        return "节点计数观测: 统计不可用"
    if after_status == "error":
        detail = after.get("detail") or "未知错误"
        return f"节点计数观测: 统计失败（{detail[:120]}）"
    return "节点计数观测: 无法判断"


def _compact_whitespace(text: str) -> str:
    return " ".join(str(text or "").split())


def _trim_frontier_item(text: str, limit: int = 220) -> str:
    text = _compact_whitespace(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _extract_blueprint_goal(events: list) -> str:
    for event in events:
        if event.get("type") != "blueprint":
            continue
        content = str(event.get("content") or "")
        match = re.search(r"\*\*目标：\*\*\s*(.+?)(?:\*\*挂载认知节点：\*\*|执行建议：|$)", content, re.S)
        if match:
            goal = _trim_frontier_item(match.group(1), 240)
            if goal:
                return goal
    return ""


def _extract_candidate_issue(response: str) -> str:
    lines = [line.strip() for line in str(response or "").splitlines() if line.strip()]
    section_starts = ("## 本轮新问题", "## 本轮选中的新问题", "## 本轮选中的问题", "## 这轮修的是什么", "## 本轮问题")
    stop_markers = ("如果你要，我下一轮可以", "如果你要，我下一轮我会", "如果你要，我会优先", "下一轮可以继续", "下一轮我会优先")
    for idx, line in enumerate(lines):
        if any(line.startswith(prefix) for prefix in section_starts):
            collected = []
            for candidate in lines[idx + 1:]:
                if candidate.startswith("## "):
                    break
                cleaned = candidate.lstrip("> ").strip()
                if not cleaned:
                    continue
                if any(marker in cleaned for marker in stop_markers):
                    break
                if cleaned.startswith("- ") and collected:
                    break
                collected.append(cleaned)
                if len(" ".join(collected)) >= 240:
                    break
            issue = _trim_frontier_item(" ".join(collected), 240)
            if issue:
                return issue
    for line in lines:
        if line.startswith(">"):
            issue = _trim_frontier_item(line.lstrip("> ").strip(), 240)
            if issue:
                return issue
    skip_prefixes = ("已完成一轮", "已继续完成一轮", "已继续推进", "不过", "如果你要", "- ", "## ")
    for line in lines:
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        cleaned = _trim_frontier_item(line, 240)
        if cleaned:
            return cleaned
    return ""


def _extract_next_checks(response: str) -> list:
    lines = [line.strip() for line in str(response or "").splitlines() if line.strip()]
    markers = ("如果你要，我下一轮可以", "如果你要，我下一轮我会", "如果你要，我会优先", "下一轮可以继续", "下一轮我会优先")
    for idx, line in enumerate(lines):
        if any(marker in line for marker in markers):
            checks = []
            for candidate in lines[idx + 1:]:
                if candidate.startswith("## "):
                    break
                if candidate.startswith(("- ", "* ")) or re.match(r"^\d+[.)]\s+", candidate):
                    cleaned = re.sub(r"^[-*]\s+|^\d+[.)]\s+", "", candidate).strip()
                    cleaned = _trim_frontier_item(cleaned, 180)
                    if cleaned:
                        checks.append(cleaned)
                elif checks:
                    break
                if len(checks) >= 3:
                    break
            if checks:
                return checks
    return []


def _collect_tool_names(events: list) -> list:
    names = []
    for event in events:
        if event.get("type") not in ("tool_result", "search_result"):
            continue
        name = str(event.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names[:6]


def _collect_round_result_events(events: list) -> list:
    result_events = []
    for event in events:
        if event.get("type") not in ("tool_result", "search_result"):
            continue
        result_events.append(event)
        if len(result_events) >= 12:
            break
    return result_events


def _detect_reanchor_signal(response: str, round_events: list, frontier_state: dict | None = None) -> tuple[bool, str]:
    response_text = str(response or "")
    result_previews = []
    for event in _collect_round_result_events(round_events):
        preview = _compact_whitespace(event.get("result_preview") or "")
        if preview:
            result_previews.append(preview[:400])
        if len(result_previews) >= 8:
            break
    frontier_parts = []
    if frontier_state:
        frontier_parts.append(str(frontier_state.get("candidate_issue") or ""))
        frontier_parts.append(str(frontier_state.get("local_goal") or ""))
    combined = "\n".join(part for part in [response_text, *frontier_parts, *result_previews] if part).strip()
    if not combined:
        return False, ""
    lowered = combined.lower()
    env_hit = any(marker in lowered for marker in ("doctor", "/workspace", "workspace", "sandbox", "沙箱", "容器", "宿主"))
    drift_hit = any(marker in lowered for marker in ("不同步", "未同步", "不会自动反映", "不会自动同步", "快照", "副本", "snapshot", "baseline", "基线"))
    target_hit = any(marker in lowered for marker in ("导入", "import", "测试契约", "测试入口", "实际导入", "实际测试", "入口", "target"))
    explicit_workspace_drift = any(marker in combined for marker in (
        "不会自动反映到 Doctor", "不会自动反映到 Doctor 容器", "不会自动反映到 Doctor 容器内",
        "不会自动反映到 /workspace", "宿主仓库里的", "实际导入",
    ))
    has_external_anchor = bool(result_previews)
    if explicit_workspace_drift or (env_hit and drift_hit and has_external_anchor):
        return True, "Doctor /workspace 快照与宿主修改目标可能错位；先确认实际生效副本"
    if target_hit and drift_hit and (has_external_anchor or env_hit):
        return True, "当前修改目标与实际测试/导入目标可能不一致；先确认 import 入口与测试目标"
    if env_hit and target_hit and has_external_anchor:
        return True, "Doctor 沙箱、测试入口或修改目标出现错位信号；先重新锚定环境再继续"
    return False, ""


def _dedupe_trimmed_items(values: list, item_limit: int, list_limit: int) -> list:
    items = []
    for value in values or []:
        cleaned = _trim_frontier_item(value, item_limit)
        if cleaned and cleaned not in items:
            items.append(cleaned)
        if len(items) >= list_limit:
            break
    return items


def _derive_reanchor_stop_reason(reanchor_required: bool, reanchor_streak: int, activity_detected: bool, consecutive_dry: int) -> str:
    if not reanchor_required:
        return ""
    if activity_detected:
        return ""
    if AUTO_DRY_LIMIT > 0 and consecutive_dry >= AUTO_DRY_LIMIT and reanchor_streak >= 2:
        return "reanchor_dry_limit"
    if reanchor_streak >= 2:
        return "reanchor_watch"
    return ""


def _build_frontier_state(round_index, response, kb_delta_summary, kb_changed, node_telemetry, round_events, prior_reanchor_streak=0):
    local_goal = _extract_blueprint_goal(round_events)
    candidate_issue = _extract_candidate_issue(response)
    next_checks = _extract_next_checks(response)
    tool_names = _collect_tool_names(round_events)
    reanchor_required, reanchor_reason = _detect_reanchor_signal(response, round_events)
    reanchor_streak = prior_reanchor_streak + 1 if reanchor_required else 0
    observations = [f"KB {kb_delta_summary}", node_telemetry]
    if tool_names:
        observations.append("工具结果: " + ", ".join(tool_names))
    if reanchor_required:
        observations.append(f"锚定状态: 已连续 {reanchor_streak} 轮需要重新锚定" if reanchor_streak >= 2 else "锚定状态: 需要重新锚定")
    observations.append("文本回复: 有" if response and str(response).strip() else "文本回复: 无")
    carry_warnings = []
    if response and not kb_changed:
        carry_warnings.append("上轮有文本回复但 KB 无变化；其中\u201c已完成/已写入/已验证\u201d表述不得直接当作已证实事实")
    if not tool_names:
        carry_warnings.append("上轮未记录到有效 tool_result；如继续同方向，需重新取证")
    if reanchor_required:
        carry_warnings.insert(0, f"检测到信息错位：{reanchor_reason}")
    if reanchor_streak >= 2:
        carry_warnings.insert(0, f"信息错位已连续 {reanchor_streak} 轮出现；如重锚后仍无新的外部证据，应停止当前路径")
    if not next_checks:
        if kb_changed:
            next_checks = ["基于本轮外部观测继续推进尚未证实的相邻问题", "避免重复已完成动作"]
        else:
            next_checks = ["回到本轮工具输出、测试结果和 diff 重新取证", "必要时换一个问题方向"]
    if reanchor_required:
        next_checks = ["先确认 Doctor /workspace 快照、实际导入目标和测试入口是否一致", "确认当前 diff/修改落在哪个副本，再继续沿当前问题推进", *next_checks]
    if reanchor_streak >= 2:
        next_checks = ["若重新锚定后仍只剩文本推进或空转，停止当前路径并换问题方向", *next_checks]
    return {
        "round": round_index,
        "local_goal": local_goal or candidate_issue or "待重新锁定",
        "candidate_issue": candidate_issue or "未从上轮回复中提取到稳定问题定义",
        "observations": _dedupe_trimmed_items(observations, 220, 4),
        "carry_warnings": _dedupe_trimmed_items(carry_warnings, 220, 3),
        "next_checks": _dedupe_trimmed_items(next_checks, 180, 3),
        "reanchor_required": reanchor_required, "reanchor_streak": reanchor_streak,
        "reanchor_reason": _trim_frontier_item(reanchor_reason, 220) if reanchor_reason else "",
    }


def _format_frontier_state(frontier_state: dict) -> str:
    lines = [
        f"R{frontier_state.get('round')} frontier",
        f"- local_goal: {frontier_state.get('local_goal') or '待重新锁定'}",
        f"- candidate_issue: {frontier_state.get('candidate_issue') or '未提取'}",
    ]
    if frontier_state.get("reanchor_required"):
        lines.append("- anchor_status: 需要重新锚定")
        if frontier_state.get("reanchor_streak"):
            lines.append(f"- anchor_streak: {frontier_state.get('reanchor_streak')}")
        lines.append(f"- anchor_reason: {frontier_state.get('reanchor_reason') or '检测到信息错位信号'}")
    lines.append("- observations:")
    for item in frontier_state.get("observations") or []:
        lines.append(f"  - {item}")
    carry_warnings = frontier_state.get("carry_warnings") or []
    if carry_warnings:
        lines.append("- carry_warnings:")
        for item in carry_warnings:
            lines.append(f"  - {item}")
    next_checks = frontier_state.get("next_checks") or []
    if next_checks:
        lines.append("- next_checks:")
        for item in next_checks:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def _build_auto_knowledge_state(frontier_state, round_events, raw_state=None):
    raw_state = raw_state if isinstance(raw_state, dict) else {}
    issue_seed = (
        frontier_state.get("candidate_issue") or frontier_state.get("local_goal") or raw_state.get("issue") or "待重新锁定"
    ) if frontier_state.get("reanchor_required") else (
        raw_state.get("issue") or frontier_state.get("candidate_issue") or frontier_state.get("local_goal") or "待重新锁定"
    )
    issue = _trim_frontier_item(issue_seed, 240)
    verified_facts = _dedupe_trimmed_items(raw_state.get("verified_facts") or [], 220, 5)
    if not verified_facts:
        verified_facts = _dedupe_trimmed_items(frontier_state.get("observations") or [], 220, 3)
    failed_attempts = _dedupe_trimmed_items(raw_state.get("failed_attempts") or [], 220, 5)
    next_checks = _dedupe_trimmed_items((raw_state.get("next_checks") or frontier_state.get("next_checks") or []), 180, 5)
    if not failed_attempts:
        failed_attempts = _dedupe_trimmed_items(frontier_state.get("carry_warnings") or [], 220, 3)
    if frontier_state.get("reanchor_required"):
        anchor_warning = f"信息错位风险：{frontier_state.get('reanchor_reason') or '当前修改目标与实际生效环境可能不一致'}"
        failed_attempts = _dedupe_trimmed_items([anchor_warning, *failed_attempts], 220, 5)
        next_checks = _dedupe_trimmed_items([
            "先确认 Doctor /workspace 快照、实际导入目标和测试入口是否一致",
            "确认当前 diff/修改落在哪个副本，再继续沿当前问题推进", *next_checks,
        ], 180, 5)
    if frontier_state.get("reanchor_streak", 0) >= 2:
        failed_attempts = _dedupe_trimmed_items([
            f"信息错位已连续 {frontier_state.get('reanchor_streak')} 轮出现；未重锚前不要继续沿当前假设叠加修改",
            *failed_attempts,
        ], 220, 5)
        next_checks = _dedupe_trimmed_items([
            "若重新锚定后仍只剩文本推进或空转，停止当前路径并换问题方向", *next_checks,
        ], 180, 5)
    return {"issue": issue, "verified_facts": verified_facts, "failed_attempts": failed_attempts, "next_checks": next_checks}


def _format_knowledge_state(knowledge_state: dict) -> str:
    if not knowledge_state:
        return "(上轮没有稳定工作记忆，回到外部观测重新取证)"
    lines = [f"- issue: {knowledge_state.get('issue') or '待重新锁定'}"]
    for key in ["verified_facts", "failed_attempts", "next_checks"]:
        values = knowledge_state.get(key) or []
        if values:
            lines.append(f"- {key}:")
            for item in values:
                lines.append(f"  - {item}")
    return "\n".join(lines)


def _classify_auto_round_progress(response, round_events, kb_changed, frontier_state=None, is_error=False):
    if is_error:
        signals = ["progress=error"]
        response_text = (response or "").strip()
        if response_text:
            signals.append(f"reply={len(response_text)}c")
        signals.append("error_response")
        return {"activity_detected": False, "activity_summary": " | ".join(signals), "progress_class": "error"}

    result_events = _collect_round_result_events(round_events)
    tool_names = []
    for entry in result_events:
        name = (entry.get("name") or "").strip()
        if name and name not in tool_names:
            tool_names.append(name)
        if len(tool_names) >= 4:
            break
    preview_text = "\n".join(_compact_whitespace(entry.get("result_preview") or "") for entry in result_events[:10]).lower()
    ran_tests = "doctor.sh test" in preview_text or "pytest" in preview_text
    inspected_diff = "doctor.sh diff" in preview_text or "git diff" in preview_text or "diff --git" in preview_text
    touched_files = (
        any(name in ("write_file", "edit_file", "replace_in_file", "append_file") for name in tool_names)
        or "sed -i" in preview_text or "write_text(" in preview_text or "text = text.replace(" in preview_text
    )
    response_text = (response or "").strip()
    stable_issue = bool(frontier_state and frontier_state.get("candidate_issue")
                        and frontier_state.get("candidate_issue") not in ("未提取", "未从上轮回复中提取到稳定问题定义"))
    reanchor_required = bool(frontier_state and frontier_state.get("reanchor_required"))
    strong_progress = bool(kb_changed or touched_files or ran_tests or inspected_diff)
    evidence_progress = bool(not strong_progress and result_events)
    soft_progress = bool(not strong_progress and not evidence_progress and (response_text or stable_issue))
    if strong_progress:
        progress_class = "strong"
    elif evidence_progress:
        progress_class = "evidence"
    elif soft_progress:
        progress_class = "soft"
    else:
        progress_class = "idle"
    activity_detected = progress_class in ("strong", "evidence")
    signals = [f"progress={progress_class}"]
    if kb_changed: signals.append("kb")
    if touched_files: signals.append("write")
    if ran_tests: signals.append("test")
    if inspected_diff: signals.append("diff")
    if tool_names: signals.append(f"tools={','.join(tool_names[:3])}")
    if stable_issue: signals.append("issue")
    if reanchor_required: signals.append("reanchor")
    if response_text: signals.append(f"reply={len(response_text)}c")
    if progress_class == "idle": signals.append("no_external_progress")
    return {"activity_detected": activity_detected, "activity_summary": " | ".join(signals), "progress_class": progress_class}


# ─── Session Planner ─────────────────────────────────────────────
PLANNER_REVIEW_INTERVAL = 5  # 每 N 轮审查一次

SESSION_PLANNER_SYSTEM = """你是 Genesis 自主探索的 Session Planner。
你负责制定和调整探索议程，确保自主探索高效、多样、不卡死。

规则：
1. 议程包含 3-5 个**不同方向**的子目标，从信号中挑选
2. 每个子目标分配 2-5 轮预算
3. 已完成 → done；连续无进展 → stuck；API错误轮不算进度
4. next_focus 必须是**具体可执行的单轮指令**（不是方向性描述）
5. 优先选择知识空洞(VOID)和低置信度节点
6. 不同子目标之间要有足够的主题差异
7. 如果所有有价值的方向都已探索或无法推进，设 should_continue=false"""

SESSION_PLANNER_INITIAL = """## 用户指令
{directive}

## 系统信号
{signals}

基于以上信号，制定初始探索议程。输出严格 JSON（不要 markdown 包裹）：
{{
  "assessment": "对系统现状的一句话判断",
  "agenda": [
    {{"topic": "具体方向描述", "budget": 3, "priority": 1, "status": "pending"}}
  ],
  "next_focus": "第一轮的具体执行指令",
  "should_continue": true,
  "reasoning": "选择理由（一句话）"
}}"""

SESSION_PLANNER_REVIEW = """## 用户指令
{directive}

## 系统信号（最新）
{signals}

## 已完成轮次
{round_history}

## 当前议程
{current_agenda}

审查进展，更新议程，指定下一轮方向。输出严格 JSON（不要 markdown 包裹）：
{{
  "assessment": "对最近进展的一句话评价",
  "agenda": [
    {{"topic": "方向描述", "budget": 3, "priority": 1, "status": "pending|in_progress|done|stuck"}}
  ],
  "next_focus": "下一轮的具体执行指令",
  "should_continue": true,
  "reasoning": "选择理由（一句话）"
}}"""

DEFAULT_PLANNER_RESULT = {
    "assessment": "planner unavailable, using default directive",
    "agenda": [],
    "next_focus": "",
    "should_continue": True,
    "reasoning": "fallback",
}


def _pick_focused_fallback(signals: str, round_num: int = 1) -> str:
    """Planner 失败时的确定性聚焦：从 signals 中选 1 个最高优先级方向。
    优先级：Arena 失败 > VOID > 低置信度 > 通用探索"""
    lines = signals.strip().splitlines()
    arena_items, void_items, low_conf_items = [], [], []
    current_section = None
    for line in lines:
        if "Arena 失败" in line:
            current_section = "arena"
        elif "知识空洞" in line or "VOID" in line:
            current_section = "void"
        elif "低置信度" in line:
            current_section = "low_conf"
        elif line.strip().startswith("LESSON_") or line.strip().startswith("CTX_"):
            if current_section == "arena":
                arena_items.append(line.strip())
            elif current_section == "low_conf":
                low_conf_items.append(line.strip())
        elif line.strip().startswith("VOID_"):
            void_items.append(line.strip())
    # 轮换选择：奇数轮选 Arena/VOID，偶数轮选低置信
    if round_num % 2 == 1:
        if arena_items:
            pick = arena_items[0]
            return f"聚焦验证这条翻车知识并改进: {pick[:120]}"
        if void_items:
            pick = void_items[0]
            return f"调查这个知识空洞并尝试填充: {pick[:120]}"
    else:
        if low_conf_items:
            pick = low_conf_items[0]
            return f"验证并更新这个低置信节点: {pick[:120]}"
        if void_items:
            pick = void_items[(round_num // 2) % max(len(void_items), 1)]
            return f"调查这个知识空洞并尝试填充: {pick[:120]}"
    if arena_items:
        return f"聚焦验证这条翻车知识并改进: {arena_items[0][:120]}"
    return "检查知识库中置信度最低的节点，验证其准确性并更新"


def _compact_round_history(round_log: list, last_n: int = 10) -> str:
    """压缩最近 N 轮历史为紧凑文本，供 planner 审查。"""
    entries = []
    for r in round_log[-last_n:]:
        parts = [f"R{r['round']}"]
        parts.append(r.get("progress_class", "?"))
        if r.get("kb_delta_summary"):
            parts.append(f"KB:{r['kb_delta_summary']}")
        if r.get("frontier_preview"):
            parts.append(r["frontier_preview"][:80])
        elif r.get("response_preview"):
            parts.append(r["response_preview"][:80])
        if r.get("exception"):
            parts.append(f"err:{str(r['exception'])[:60]}")
        entries.append(" | ".join(parts))
    return "\n".join(entries) if entries else "(无历史)"


async def _call_session_planner(
    provider, directive: str, signals: str,
    round_log: list = None, current_agenda: list = None,
) -> dict:
    """调用 LLM 进行 session 级规划。失败时返回默认值，不阻塞主流程。"""
    try:
        if round_log:
            round_history = _compact_round_history(round_log)
            agenda_text = json.dumps(current_agenda or [], ensure_ascii=False, indent=1)
            user_content = SESSION_PLANNER_REVIEW.format(
                directive=directive, signals=signals,
                round_history=round_history, current_agenda=agenda_text,
            )
        else:
            user_content = SESSION_PLANNER_INITIAL.format(
                directive=directive, signals=signals,
            )

        messages = [
            {"role": "system", "content": SESSION_PLANNER_SYSTEM},
            {"role": "user", "content": user_content},
        ]
        result = await asyncio.wait_for(
            provider.chat(messages=messages, max_tokens=800, temperature=0.3),
            timeout=30,
        )
        raw = (result.content or "").strip()
        logger.info(f"Session planner raw response ({len(raw)}c): {raw[:300]}")
        if not raw:
            logger.warning("Session planner returned empty content")
            return DEFAULT_PLANNER_RESULT.copy()
        # 尝试提取 JSON（处理可能的 markdown 包裹）
        if raw.startswith("```"):
            lines = raw.split("\n")
            json_lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(json_lines).strip()
        parsed = json.loads(raw)
        # 基本校验
        if not isinstance(parsed, dict) or "next_focus" not in parsed:
            logger.warning(f"Session planner returned invalid structure: {raw[:200]}")
            return DEFAULT_PLANNER_RESULT.copy()
        logger.info(f"Session planner OK | assessment={parsed.get('assessment','')[:80]} | next={parsed.get('next_focus','')[:80]}")
        return parsed
    except asyncio.TimeoutError:
        logger.warning("Session planner call timed out (30s)")
        return DEFAULT_PLANNER_RESULT.copy()
    except json.JSONDecodeError as e:
        logger.warning(f"Session planner JSON parse error: {e} | raw={raw[:200] if 'raw' in dir() else '?'}")
        return DEFAULT_PLANNER_RESULT.copy()
    except Exception as e:
        logger.warning(f"Session planner call failed: {e}")
        return DEFAULT_PLANNER_RESULT.copy()


def describe_auto_state(auto_state: dict, channel_id: int) -> str:
    st = auto_state.get(channel_id)
    if not st:
        return "active=False task=missing"
    task = st.get("task")
    parts = [f"active={bool(st.get('active', False))}"]
    if task is None:
        parts.append("task=none")
        return " ".join(parts)
    parts.append(f"task_done={task.done()}")
    parts.append(f"task_cancelled={task.cancelled()}")
    if task.done() and not task.cancelled():
        try:
            exc = task.exception()
        except Exception as e:
            exc = e
        if exc:
            parts.append(f"task_exception={type(exc).__name__}:{str(exc)[:120]}")
    return " ".join(parts)


# ─── Main Entry Point ─────────────────────────────────────────────

async def run_auto(channel: discord.TextChannel, agent, auto_state: dict, directive: str = ""):
    """自主探索模式：用户指令驱动 → 工具探索 → 知识沉淀 → 报告"""
    if not directive:
        directive = AUTO_DEFAULT_DIRECTIVE
    state = auto_state.get(channel.id)
    if not state:
        logger.warning(f"/auto runner exited before start | channel={channel.id} state=missing")
        return
    logger.info(f"/auto runner started | channel={channel.id} state={describe_auto_state(auto_state, channel.id)}")

    round_num = 0
    consecutive_dry = 0
    consecutive_error = 0
    stop_reason = "manual"
    round_log = []
    last_frontier = ""
    last_knowledge_state: dict = {}
    last_good_knowledge_state: dict = {}
    last_reanchor_streak = 0
    session_shown_voids: set = set()
    session_shown_nodes: set = set()
    planner_agenda: list = []
    planner_result: dict = {}
    last_planner_round: int = 0
    planner_call_count: int = 0
    final_node_telemetry = "节点计数观测: 无法判断"
    doctor_sync_summary = "disabled"

    _report_dir = Path("runtime/auto_reports")
    _report_dir.mkdir(parents=True, exist_ok=True)
    _session_ts = _time_module.strftime("%Y%m%d_%H%M%S")
    _session_id = f"{channel.id}_{_session_ts}"
    _rounds_dir = _report_dir / _session_id
    _rounds_dir.mkdir(parents=True, exist_ok=True)
    _md_path = _report_dir / f"auto_{_session_id}.md"
    _md_path.write_text(f"# /auto Report — session={_session_id}\n\n", encoding="utf-8")
    _session_json_path = _report_dir / f"auto_{_session_id}.json"

    def _append_md(text: str):
        try:
            with _md_path.open("a", encoding="utf-8") as f:
                f.write(text)
        except Exception as _e:
            logger.debug(f"MD report write failed: {_e}")

    def _write_round_json(data: dict):
        try:
            rpath = _rounds_dir / f"round_{data['round']:03d}.json"
            rpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as _e:
            logger.debug(f"Round JSON write failed: {_e}")

    await channel.send(
        f"🚀 **自主改进模式启动** ({'无上限' if AUTO_MAX_ROUNDS == 0 else f'上限 {AUTO_MAX_ROUNDS} 轮'})\n"
        f"Genesis 将基于真实信号，在 Doctor 沙箱中动手改进自身。\n"
        f"发送 `/auto stop` 停止。"
    )
    if AUTO_SYNC_DOCTOR_SANDBOX:
        await channel.send("🩺 正在同步 Doctor 沙箱代码快照...")
        sync_ok, doctor_sync_summary = await _sync_doctor_sandbox()
        _append_md(f"## Doctor Sandbox Sync\n\n```\n{doctor_sync_summary}\n```\n\n")
        if sync_ok:
            await channel.send("✅ Doctor 沙箱已重置并同步到当前代码快照。")
        else:
            await channel.send("⚠️ Doctor 沙箱同步失败，将继续运行，但工作区可能不是最新快照。")
    else:
        _append_md("## Doctor Sandbox Sync\n\n```\ndisabled\n```\n\n")

    while state.get("active", False):
        round_num += 1
        if AUTO_MAX_ROUNDS > 0 and round_num > AUTO_MAX_ROUNDS:
            stop_reason = f"reached {AUTO_MAX_ROUNDS} round cap"
            break

        _reset_provider(agent)
        node_status_before = _get_node_count_status()
        round_start_ts = _time_module.time()
        round_start_iso = _time_module.strftime("%Y-%m-%d %H:%M:%S", _time_module.localtime(round_start_ts))
        round_start_utc_iso = _time_module.strftime("%Y-%m-%d %H:%M:%S", _time_module.gmtime(round_start_ts))

        signals = _get_auto_signals(round_num=round_num, session_shown_voids=session_shown_voids, session_shown_nodes=session_shown_nodes)

        # ── Session Planner：初始规划 / 定期审查 / 错误后审查 ──
        need_planner = (
            round_num == 1
            or (round_num - last_planner_round >= PLANNER_REVIEW_INTERVAL)
            or (consecutive_error > 0 and round_num - last_planner_round >= 2)
        )
        if need_planner and consecutive_error < 5:
            await channel.send(f"🧭 Session Planner {'制定初始议程' if round_num == 1 else '审查进展'}...")
            planner_result = await _call_session_planner(
                provider=agent.provider, directive=directive, signals=signals,
                round_log=round_log if round_num > 1 else None,
                current_agenda=planner_agenda if round_num > 1 else None,
            )
            planner_agenda = planner_result.get("agenda", [])
            planner_call_count += 1
            last_planner_round = round_num
            _append_md(
                f"\n### Session Planner (call #{planner_call_count})\n\n"
                f"```json\n{json.dumps(planner_result, ensure_ascii=False, indent=1)}\n```\n\n"
            )
            await channel.send(
                f"📋 {planner_result.get('assessment', '')[:200]}\n"
                f"🎯 next: {planner_result.get('next_focus', '')[:200]}"
            )
            if not planner_result.get("should_continue", True):
                stop_reason = f"planner: {planner_result.get('reasoning', 'all directions explored')}"
                await channel.send(f"🏁 Planner 建议停止: {stop_reason}")
                break

        # 从 planner 获取本轮 focus（fallback 到聚焦信号，而非宽泛 directive）
        round_focus = planner_result.get("next_focus", "").strip()
        if not round_focus:
            round_focus = _pick_focused_fallback(signals, round_num) if signals else directive

        if round_num == 1:
            prompt = AUTO_PROMPT_FIRST.format(directive=round_focus, signals=signals)
        else:
            history_entries = [
                f"R{e['round']}: {e.get('activity_summary') or e['kb_delta_summary']} | {e.get('frontier_preview') or e['response_preview']}"
                for e in round_log[-5:]
            ]
            history = "[已完成的行动]\n" + "\n".join(history_entries) + "\n不要重复以上内容。" if history_entries else ""
            frontier = last_frontier if last_frontier and last_frontier.strip() != "(无输出)" else "(上轮无可复用前沿，换个方向)"
            knowledge_state_text = _format_knowledge_state(last_knowledge_state)
            prompt = AUTO_PROMPT_CONTINUE.format(
                directive=round_focus,
                knowledge_state=knowledge_state_text, frontier_state=frontier,
                history=history, signals=signals,
            )

        _append_md(f"\n---\n## 第 {round_num} 轮\n\n### 信号\n```\n{signals}\n```\n\n### Prompt\n```\n{prompt[:2000]}\n```\n\n")
        await channel.send(f"{'─'*40}\n🔧 **第 {round_num} 轮**")

        round_events: list = []

        class RichAutoCallback:
            """捕捉全部 callback 事件写入 round JSON；tool_start 仍推送 Discord。"""
            def __init__(self, ch, events: list, t0: float):
                self._ch = ch
                self._events = events
                self._t0 = t0

            async def __call__(self, event_type, data):
                try:
                    rel_t = round(_time_module.time() - self._t0, 2)
                    evt = CallbackEvent.from_raw(event_type, data)
                    entry = {"t": rel_t, "type": evt.event_type}
                    if evt.phase:
                        entry["phase"] = evt.phase
                    if isinstance(data, dict):
                        if data.get("llm_call_id"):
                            entry["llm_call_id"] = data.get("llm_call_id")
                        if "iteration" in data:
                            entry["iteration"] = data.get("iteration")
                        if data.get("label"):
                            entry["label"] = data.get("label")
                    if evt.event_type == "tool_start":
                        entry["name"] = evt.name
                        if evt.name == "search_knowledge_nodes":
                            round_record["knowledge_search_count"] = round_record.get("knowledge_search_count", 0) + 1
                        await self._ch.send(f"🟢 `{evt.name or '?'}` ...")
                    elif evt.event_type == "tool_result":
                        entry["name"] = evt.name
                        entry["result_preview"] = (evt.result or "")[:400]
                        await self._ch.send(f"↩️ `{evt.name or '?'}`: {(evt.result or '')[:300]}")
                    elif evt.event_type == "blueprint":
                        blueprint_text = data.get("content", "") if isinstance(data, dict) else (str(data) if not isinstance(data, str) else data)
                        entry["content"] = str(blueprint_text)[:500]
                        if isinstance(data, dict):
                            entry["op_intent"] = str(data.get("op_intent", ""))[:200]
                            if data.get("active_nodes"):
                                entry["active_nodes"] = list(data.get("active_nodes") or [])[:10]
                    elif evt.event_type == "c_phase_done":
                        if isinstance(data, dict):
                            disc = data.get("discovery_recording") or {}
                            prom = data.get("pattern_promotion") or {}
                            chal = data.get("challenger_review") or {}
                            round_record["c_phase_summary"] = {
                                "mode": data.get("mode", "?"),
                                "c_tokens": data.get("c_tokens", 0),
                                "discoveries_recorded": disc.get("discoveries_recorded", 0),
                                "discovery_subjects": [d.get("subject", "?") for d in disc.get("discoveries", [])][:5],
                                "patterns_promoted": prom.get("patterns_promoted", 0),
                                "challenger_status": chal.get("status", "n/a"),
                            }
                            entry["data"] = round_record["c_phase_summary"]
                    elif evt.event_type in ("lens_start", "lens_analysis", "lens_adoption", "lens_done", "lens_skipped"):
                        entry["data"] = data if isinstance(data, dict) else {"raw": str(data)[:200]}
                    elif evt.event_type == "search_result":
                        entry["name"] = evt.name
                        entry["result_preview"] = (evt.result or "")[:400]
                        if evt.name == "search_knowledge_nodes":
                            round_record["knowledge_search_count"] = round_record.get("knowledge_search_count", 0) + 1
                    elif evt.event_type in ("content", "reasoning"):
                        chunk_text = evt.result or ""
                        entry["chunk_chars"] = (data.get("chunk_chars") if isinstance(data, dict) else None) or len(chunk_text)
                        if chunk_text:
                            entry["preview"] = chunk_text[:80]
                        stream_key = f"{evt.event_type}_chars"
                        chunk_key = f"{evt.event_type}_chunks"
                        round_record["stream_stats"][stream_key] += entry["chunk_chars"]
                        round_record["stream_stats"][chunk_key] += 1
                    elif evt.event_type in ("llm_call_start", "llm_call_end"):
                        if isinstance(data, dict):
                            entry["data"] = {
                                "phase": data.get("phase"), "llm_call_id": data.get("llm_call_id"),
                                "iteration": data.get("iteration"), "label": data.get("label"),
                                "stream": data.get("stream"), "duration_ms": data.get("duration_ms"),
                                "finish_reason": data.get("finish_reason"), "tool_call_count": data.get("tool_call_count"),
                                "content_chars": data.get("content_chars"), "reasoning_chars": data.get("reasoning_chars"),
                                "total_tokens": data.get("total_tokens"), "error": data.get("error"),
                            }
                        else:
                            entry["data"] = {"raw": str(data)[:200]}
                        if evt.event_type == "llm_call_start":
                            round_record["llm_call_count"] += 1
                    self._events.append(entry)
                    round_record["last_event_type"] = evt.event_type
                    round_record["last_event_t"] = rel_t
                    if entry.get("phase"):
                        round_record["last_event_phase"] = entry.get("phase")
                    if entry.get("llm_call_id"):
                        round_record["last_llm_call_id"] = entry.get("llm_call_id")
                    _flush_round_record()
                except Exception:
                    pass

        round_record = {
            "session_id": _session_id, "round": round_num, "status": "running",
            "started_at": round_start_iso, "started_at_utc": round_start_utc_iso,
            "updated_at": round_start_iso, "duration_s": 0.0, "tokens": 0,
            "signals": signals, "prompt_preview": prompt[:2000],
            "events": round_events, "event_count": 0,
            "response_full": "", "response_preview": "",
            "kb_delta": {"new_nodes": [], "updated_nodes": [], "error": "pending"},
            "kb_delta_summary": "pending", "kb_changed": False,
            "activity_detected": False, "activity_summary": "pending", "progress_class": "pending",
            "consecutive_dry": consecutive_dry,
            "node_telemetry": "节点计数观测: 进行中",
            "phase_trace": None, "knowledge_state": None, "knowledge_state_text": "",
            "frontier_state": None, "frontier_text": "", "frontier_preview": "running",
            "reanchor_required": False, "reanchor_reason": "", "reanchor_streak": 0, "reanchor_stop_reason": "",
            "last_event_type": None, "last_event_t": None, "last_event_phase": None, "last_llm_call_id": None,
            "llm_call_count": 0,
            "stream_stats": {"content_chunks": 0, "content_chars": 0, "reasoning_chunks": 0, "reasoning_chars": 0},
            "c_phase_summary": None,
            "knowledge_search_count": 0,
            "exception": None,
        }
        round_log.append(round_record)

        def _flush_round_record():
            round_record["updated_at"] = _time_module.strftime("%Y-%m-%d %H:%M:%S", _time_module.localtime())
            round_record["event_count"] = len(round_events)
            _write_round_json(round_record)

        def _observe_round_state():
            try:
                kb_delta = _query_kb_delta(round_start_utc_iso)
            except Exception as obs_e:
                kb_delta = {"new_nodes": [], "updated_nodes": [], "error": f"kb_observation_error:{str(obs_e)[:120]}"}
            try:
                node_telemetry = _format_node_telemetry(node_status_before, _get_node_count_status())
            except Exception as obs_e:
                node_telemetry = f"节点计数观测: 统计失败（{str(obs_e)[:120]}）"
            kb_changed = bool(kb_delta["new_nodes"] or kb_delta["updated_nodes"])
            kb_delta_summary = (
                f"+{len(kb_delta['new_nodes'])}新/{len(kb_delta['updated_nodes'])}更新"
                if not kb_delta["error"] else "KB-delta-error"
            )
            return kb_delta, kb_changed, kb_delta_summary, node_telemetry

        _flush_round_record()

        t0 = _time_module.time()
        def _finalize_incomplete_round(reason: str):
            nonlocal consecutive_dry, final_node_telemetry, last_frontier, last_knowledge_state, last_reanchor_streak
            if round_record.get("status") != "running":
                return
            kb_delta, kb_changed, kb_delta_summary, node_telemetry = _observe_round_state()
            final_node_telemetry = node_telemetry
            frontier_state = _build_frontier_state(
                round_index=round_num, response=round_record.get("response_full") or round_record.get("response_preview") or "",
                kb_delta_summary=kb_delta_summary, kb_changed=kb_changed, node_telemetry=node_telemetry,
                round_events=round_events, prior_reanchor_streak=last_reanchor_streak,
            )
            frontier_text = _format_frontier_state(frontier_state)
            frontier_preview = f"goal={frontier_state['local_goal']} | issue={frontier_state['candidate_issue']}" + (f" | reanchor#{frontier_state.get('reanchor_streak', 0)}" if frontier_state.get("reanchor_required") else "")
            knowledge_state = _build_auto_knowledge_state(
                frontier_state=frontier_state, round_events=round_events,
                raw_state=round_record.get("knowledge_state") or last_knowledge_state or None,
            )
            knowledge_state_text = _format_knowledge_state(knowledge_state)
            progress_profile = _classify_auto_round_progress(
                response=round_record.get("response_full") or round_record.get("response_preview") or "",
                round_events=round_events, kb_changed=kb_changed, frontier_state=frontier_state,
            )
            consecutive_dry = 0 if progress_profile["activity_detected"] else consecutive_dry + 1
            reanchor_stop_reason = _derive_reanchor_stop_reason(
                frontier_state.get("reanchor_required", False),
                int(frontier_state.get("reanchor_streak", 0) or 0),
                progress_profile["activity_detected"], consecutive_dry,
            )
            last_frontier = frontier_text
            last_knowledge_state = knowledge_state
            last_reanchor_streak = int(frontier_state.get("reanchor_streak", 0) or 0)
            round_record.update({
                "status": "interrupted", "duration_s": round(_time_module.time() - t0, 1),
                "kb_delta": kb_delta, "kb_delta_summary": kb_delta_summary, "kb_changed": kb_changed,
                "activity_detected": progress_profile["activity_detected"],
                "activity_summary": progress_profile["activity_summary"],
                "progress_class": progress_profile["progress_class"],
                "consecutive_dry": consecutive_dry, "node_telemetry": node_telemetry,
                "knowledge_state": knowledge_state, "knowledge_state_text": knowledge_state_text,
                "frontier_state": frontier_state, "frontier_text": frontier_text, "frontier_preview": frontier_preview,
                "reanchor_required": frontier_state.get("reanchor_required", False),
                "reanchor_reason": frontier_state.get("reanchor_reason") or "",
                "reanchor_streak": frontier_state.get("reanchor_streak", 0),
                "reanchor_stop_reason": reanchor_stop_reason, "exception": reason,
            })
            _flush_round_record()

        try:
            process_coro = agent.process(
                f"[GENESIS_USER_REQUEST_START]\n{prompt}",
                step_callback=RichAutoCallback(channel, round_events, t0),
                c_phase_blocking=True,
                loop_config={
                    "disable_multi_g": True,
                    "gp_unblock_tools": ["record_lesson_node"],
                },
                initial_knowledge_state=last_knowledge_state or None,
            )
            if AUTO_ROUND_TIMEOUT_SECS > 0:
                result = await asyncio.wait_for(process_coro, timeout=AUTO_ROUND_TIMEOUT_SECS)
            else:
                result = await process_coro
            duration = _time_module.time() - t0
            response = result.response if hasattr(result, 'response') else result.get("response", "") if isinstance(result, dict) else ""
            total_tokens = result.total_tokens if hasattr(result, 'total_tokens') else 0
            round_is_error = _is_error_response(response, total_tokens)
            kb_delta, kb_changed, kb_delta_summary, node_telemetry = _observe_round_state()
            final_node_telemetry = node_telemetry

            frontier_state = _build_frontier_state(
                round_index=round_num, response="" if round_is_error else response,
                kb_delta_summary=kb_delta_summary, kb_changed=kb_changed if not round_is_error else False,
                node_telemetry=node_telemetry, round_events=round_events,
                prior_reanchor_streak=last_reanchor_streak,
            )
            frontier_text = _format_frontier_state(frontier_state)
            if not round_is_error:
                last_frontier = frontier_text
            frontier_preview = f"goal={frontier_state['local_goal']} | issue={frontier_state['candidate_issue']}" + (f" | reanchor#{frontier_state.get('reanchor_streak', 0)}" if frontier_state.get("reanchor_required") else "")
            if round_is_error:
                knowledge_state = last_good_knowledge_state.copy() if last_good_knowledge_state else {}
                consecutive_error += 1
                logger.warning(f"Auto round {round_num} error response detected (consecutive={consecutive_error}): {(response or '')[:120]}")
            else:
                knowledge_state = _build_auto_knowledge_state(
                    frontier_state=frontier_state, round_events=round_events,
                    raw_state=result.knowledge_state if hasattr(result, 'knowledge_state') else None,
                )
                consecutive_error = 0
                last_good_knowledge_state = knowledge_state.copy()
            knowledge_state_text = _format_knowledge_state(knowledge_state)
            progress_profile = _classify_auto_round_progress(
                response=response, round_events=round_events,
                kb_changed=kb_changed if not round_is_error else False,
                frontier_state=frontier_state, is_error=round_is_error,
            )
            consecutive_dry = 0 if progress_profile["activity_detected"] else consecutive_dry + 1
            last_knowledge_state = knowledge_state
            reanchor_stop_reason = _derive_reanchor_stop_reason(
                frontier_state.get("reanchor_required", False),
                int(frontier_state.get("reanchor_streak", 0) or 0),
                progress_profile["activity_detected"], consecutive_dry,
            )
            last_reanchor_streak = int(frontier_state.get("reanchor_streak", 0) or 0)

            round_record.update({
                "status": "completed", "duration_s": round(duration, 1), "tokens": total_tokens,
                "response_full": response or "", "response_preview": (response or "")[:300].replace("\n", " "),
                "kb_delta": kb_delta, "kb_delta_summary": kb_delta_summary, "kb_changed": kb_changed,
                "activity_detected": progress_profile["activity_detected"],
                "activity_summary": progress_profile["activity_summary"],
                "progress_class": progress_profile["progress_class"],
                "consecutive_dry": consecutive_dry, "node_telemetry": node_telemetry,
                "phase_trace": result.phase_trace if hasattr(result, 'phase_trace') else None,
                "knowledge_state": knowledge_state, "knowledge_state_text": knowledge_state_text,
                "frontier_state": frontier_state, "frontier_text": frontier_text, "frontier_preview": frontier_preview,
                "reanchor_required": frontier_state.get("reanchor_required", False),
                "reanchor_reason": frontier_state.get("reanchor_reason") or "",
                "reanchor_streak": frontier_state.get("reanchor_streak", 0),
                "reanchor_stop_reason": reanchor_stop_reason, "exception": None,
            })
            _flush_round_record()
            # C-Phase + 知识闭环诊断行
            c_sum = round_record.get("c_phase_summary") or {}
            ks_count = round_record.get("knowledge_search_count", 0)
            c_diag = f"C[disc={c_sum.get('discoveries_recorded', 0)} pat={c_sum.get('patterns_promoted', 0)}]" if c_sum else "C[skip]"
            k_diag = f"search={ks_count}" if ks_count else "search=0"

            _append_md(
                f"### Knowledge State\n\n```\n{knowledge_state_text}\n```\n\n"
                f"### C-Phase\n\n```\n{json.dumps(c_sum, ensure_ascii=False) if c_sum else 'skipped'}\n```\n\n"
                f"### Frontier\n\n```\n{frontier_text}\n```\n\n"
                f"### Response ({duration:.0f}s | {total_tokens}t | {node_telemetry} | KB {kb_delta_summary} | {c_diag} | {k_diag} | activity {progress_profile['activity_summary']})\n\n"
                f"{response or '(无输出)'}\n\n"
            )
            await channel.send(
                f"**第{round_num}轮** | {duration:.0f}s | {total_tokens}t | {node_telemetry} | KB {kb_delta_summary} | {c_diag} | {k_diag} | activity={progress_profile['activity_summary']} | idle={consecutive_dry}"
            )
            if response:
                preview = response[:3600]
                if len(response) > 3600:
                    preview += f"\n... (共{len(response)}字)"
                for i in range(0, len(preview), 1990):
                    await channel.send(preview[i:i+1990])

        except asyncio.TimeoutError:
            duration = _time_module.time() - t0
            err_str = f"round_timeout>{AUTO_ROUND_TIMEOUT_SECS}s" if AUTO_ROUND_TIMEOUT_SECS > 0 else "round_timeout"
            logger.error(f"Auto round {round_num} timeout: {err_str}", exc_info=True)
            await channel.send(f"⚠️ 第{round_num}轮超时: {err_str}")
            _append_md(f"### Response (timeout)\n\n{err_str}\n\n")
            kb_delta, kb_changed, kb_delta_summary, node_telemetry = _observe_round_state()
            final_node_telemetry = node_telemetry
            frontier_state = _build_frontier_state(
                round_index=round_num, response="",
                kb_delta_summary=kb_delta_summary, kb_changed=kb_changed,
                node_telemetry=node_telemetry, round_events=round_events,
                prior_reanchor_streak=last_reanchor_streak,
            )
            frontier_text = _format_frontier_state(frontier_state)
            frontier_preview = "timeout" + (f" | reanchor#{frontier_state.get('reanchor_streak', 0)}" if frontier_state.get("reanchor_required") else "")
            progress_profile = _classify_auto_round_progress(
                response="", round_events=round_events,
                kb_changed=kb_changed, frontier_state=frontier_state,
            )
            consecutive_dry = 0 if progress_profile["activity_detected"] else consecutive_dry + 1
            reanchor_stop_reason = _derive_reanchor_stop_reason(
                frontier_state.get("reanchor_required", False),
                int(frontier_state.get("reanchor_streak", 0) or 0),
                progress_profile["activity_detected"], consecutive_dry,
            )
            last_reanchor_streak = int(frontier_state.get("reanchor_streak", 0) or 0)
            round_record.update({
                "status": "timeout", "duration_s": round(duration, 1),
                "kb_delta": kb_delta, "kb_delta_summary": kb_delta_summary, "kb_changed": kb_changed,
                "activity_detected": progress_profile["activity_detected"],
                "activity_summary": progress_profile["activity_summary"],
                "progress_class": progress_profile["progress_class"],
                "consecutive_dry": consecutive_dry, "node_telemetry": node_telemetry,
                "frontier_state": frontier_state, "frontier_text": frontier_text, "frontier_preview": frontier_preview,
                "reanchor_required": frontier_state.get("reanchor_required", False),
                "reanchor_reason": frontier_state.get("reanchor_reason") or "",
                "reanchor_streak": frontier_state.get("reanchor_streak", 0),
                "reanchor_stop_reason": reanchor_stop_reason, "exception": err_str,
            })
            _flush_round_record()
            last_frontier = ""

        except asyncio.CancelledError:
            stop_reason = f"cancelled during round {round_num}"
            logger.warning(f"Auto round {round_num} cancelled before finalize.", exc_info=True)
            _finalize_incomplete_round(stop_reason)
            break

        except Exception as e:
            duration = _time_module.time() - t0
            logger.error(f"Auto round {round_num} error: {e}", exc_info=True)
            err_str = str(e)[:300]
            await channel.send(f"⚠️ 第{round_num}轮异常: {err_str}")
            _append_md(f"### Response (exception)\n\n{err_str}\n\n")
            kb_delta, kb_changed, kb_delta_summary, node_telemetry = _observe_round_state()
            final_node_telemetry = node_telemetry
            frontier_state = _build_frontier_state(
                round_index=round_num, response="",
                kb_delta_summary=kb_delta_summary, kb_changed=kb_changed,
                node_telemetry=node_telemetry, round_events=round_events,
                prior_reanchor_streak=last_reanchor_streak,
            )
            frontier_text = _format_frontier_state(frontier_state)
            frontier_preview = "exception" + (f" | reanchor#{frontier_state.get('reanchor_streak', 0)}" if frontier_state.get("reanchor_required") else "")
            progress_profile = _classify_auto_round_progress(
                response="", round_events=round_events,
                kb_changed=kb_changed, frontier_state=frontier_state,
            )
            consecutive_dry = 0 if progress_profile["activity_detected"] else consecutive_dry + 1
            reanchor_stop_reason = _derive_reanchor_stop_reason(
                frontier_state.get("reanchor_required", False),
                int(frontier_state.get("reanchor_streak", 0) or 0),
                progress_profile["activity_detected"], consecutive_dry,
            )
            last_reanchor_streak = int(frontier_state.get("reanchor_streak", 0) or 0)
            round_record.update({
                "status": "exception", "duration_s": round(duration, 1),
                "kb_delta": kb_delta, "kb_delta_summary": kb_delta_summary, "kb_changed": kb_changed,
                "activity_detected": progress_profile["activity_detected"],
                "activity_summary": progress_profile["activity_summary"],
                "progress_class": progress_profile["progress_class"],
                "consecutive_dry": consecutive_dry, "node_telemetry": node_telemetry,
                "frontier_state": frontier_state, "frontier_text": frontier_text, "frontier_preview": frontier_preview,
                "reanchor_required": frontier_state.get("reanchor_required", False),
                "reanchor_reason": frontier_state.get("reanchor_reason") or "",
                "reanchor_streak": frontier_state.get("reanchor_streak", 0),
                "reanchor_stop_reason": reanchor_stop_reason, "exception": err_str,
            })
            _flush_round_record()
            last_frontier = ""

        finally:
            _finalize_incomplete_round("interrupted_before_round_finalize")

        # ── 熔断：连续错误 ──
        if consecutive_error >= 5:
            stop_reason = f"{consecutive_error} consecutive error rounds"
            await channel.send(f"⛔ 连续 {consecutive_error} 轮 API/provider 错误，自动停止。请检查 provider 状态后重启。")
            break

        # ── 熔断：连续无外部证据/修改 ──
        if AUTO_DRY_LIMIT > 0 and consecutive_dry >= AUTO_DRY_LIMIT:
            latest_round = round_log[-1] if round_log else {}
            if latest_round.get("reanchor_stop_reason") == "reanchor_dry_limit":
                stop_reason = "reanchor_dry_limit"
                await channel.send(
                    f"⏸️ 连续 {AUTO_DRY_LIMIT} 轮未观察到新的外部证据或修改，且已连续 {latest_round.get('reanchor_streak', 0)} 轮存在信息错位信号，自动停止当前路径。"
                )
            else:
                stop_reason = f"{AUTO_DRY_LIMIT} consecutive idle rounds"
                await channel.send(f"⏸️ 连续 {AUTO_DRY_LIMIT} 轮未观察到新的外部证据或修改，自动停止。")
            break

        # 轮间休息（错误轮指数退避 + provider reset）
        if state.get("active", False):
            if consecutive_error > 0:
                error_sleep = min(30 + consecutive_error * 30, 180)
                logger.info(f"/auto error backoff | consecutive_error={consecutive_error} sleep={error_sleep}s")
                await channel.send(f"⚠️ API 错误，等待 {error_sleep}s 后重试（连续第 {consecutive_error} 次）...")
                _reset_provider(agent)
                await asyncio.sleep(error_sleep)
            else:
                sleep_time = AUTO_SLEEP_BASE if consecutive_dry == 0 else AUTO_DRY_SLEEP_BASE + consecutive_dry * AUTO_DRY_SLEEP_STEP
                await asyncio.sleep(sleep_time)

    # ── 会话汇总 JSON ──
    state["active"] = False
    total_rounds = len(round_log)
    progress_rounds = sum(1 for r in round_log if r.get("activity_detected"))
    strong_progress_rounds = sum(1 for r in round_log if r.get("progress_class") == "strong")
    evidence_progress_rounds = sum(1 for r in round_log if r.get("progress_class") == "evidence")
    soft_progress_rounds = sum(1 for r in round_log if r.get("progress_class") == "soft")
    kb_progress_rounds = sum(1 for r in round_log if r.get("kb_changed"))
    reanchor_rounds = sum(1 for r in round_log if r.get("reanchor_required"))
    reanchor_watch_rounds = sum(1 for r in round_log if r.get("reanchor_stop_reason") == "reanchor_watch")
    reanchor_dry_stop_rounds = sum(1 for r in round_log if r.get("reanchor_stop_reason") == "reanchor_dry_limit")
    max_reanchor_streak = max((int(r.get("reanchor_streak", 0) or 0) for r in round_log), default=0)
    error_rounds = sum(1 for r in round_log if r.get("progress_class") == "error")
    session_summary = {
        "session_id": _session_id,
        "total_rounds": total_rounds, "progress_rounds": progress_rounds,
        "strong_progress_rounds": strong_progress_rounds,
        "evidence_progress_rounds": evidence_progress_rounds,
        "soft_progress_rounds": soft_progress_rounds,
        "kb_progress_rounds": kb_progress_rounds,
        "error_rounds": error_rounds,
        "planner_calls": planner_call_count,
        "planner_agenda_size": len(planner_agenda),
        "unique_voids_shown": len(session_shown_voids),
        "unique_nodes_shown": len(session_shown_nodes),
        "reanchor_rounds": reanchor_rounds,
        "reanchor_watch_rounds": reanchor_watch_rounds,
        "reanchor_dry_stop_rounds": reanchor_dry_stop_rounds,
        "max_reanchor_streak": max_reanchor_streak,
        "dry_rounds": total_rounds - progress_rounds,
        "stop_reason": stop_reason,
        "total_tokens": sum(r.get("tokens", 0) for r in round_log),
        "total_new_nodes": sum(len(r.get("kb_delta", {}).get("new_nodes", [])) for r in round_log),
        "total_updated_nodes": sum(len(r.get("kb_delta", {}).get("updated_nodes", [])) for r in round_log),
        "doctor_sync_summary": doctor_sync_summary,
        "rounds_dir": str(_rounds_dir),
    }
    try:
        _session_json_path.write_text(json.dumps(session_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as _e:
        logger.debug(f"Session JSON write failed: {_e}")

    _append_md(
        f"\n---\n## 终止摘要\n\n"
        f"- rounds: {total_rounds} (activity={progress_rounds}, strong={strong_progress_rounds}, evidence={evidence_progress_rounds}, soft={soft_progress_rounds}, error={error_rounds}, kb_progress={kb_progress_rounds}, dry={total_rounds - progress_rounds}, reanchor={reanchor_rounds}, reanchor_watch={reanchor_watch_rounds}, reanchor_max={max_reanchor_streak})\n"
        f"- planner_calls: {planner_call_count}, agenda_size: {len(planner_agenda)}, unique_voids_shown: {len(session_shown_voids)}, unique_nodes_shown: {len(session_shown_nodes)}\n"
        f"- stop_reason: {stop_reason}\n"
        f"- total_tokens: {session_summary['total_tokens']}\n"
        f"- new_nodes: {session_summary['total_new_nodes']}, updated_nodes: {session_summary['total_updated_nodes']}\n"
        f"- doctor_sync: {doctor_sync_summary[:240]}\n"
        f"- {final_node_telemetry}\n"
    )
    try:
        await channel.send(
            f"{'═'*40}\n"
            f"🏁 **自主改进结束** | {total_rounds} 轮 (有推进={progress_rounds}, 强={strong_progress_rounds}, 证据={evidence_progress_rounds}, 错误={error_rounds}, KB={kb_progress_rounds}, reanchor_max={max_reanchor_streak}) | 停止: {stop_reason}\n"
            f"{final_node_telemetry}\n"
            f"📄 报告: `{_md_path.name}` | JSON: `{_rounds_dir.name}/`\n"
            f"{'═'*40}"
        )
    except Exception as _e:
        logger.debug(f"Auto final summary send failed: {_e}")
    finally:
        auto_state.pop(channel.id, None)
