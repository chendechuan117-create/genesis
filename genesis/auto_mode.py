"""
Genesis V4 — Auto Mode
自主改进模式的核心逻辑：信号收集、前沿追踪、KB delta 观测、Doctor 沙箱同步。
从 discord_bot.py 提取，减少主文件复杂度。
"""

import gc
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

# ─── Memory Management ────────────────────────────────────────────
_ROUND_LOG_KEEP = 12  # keep last N rounds full; older rounds compacted (heavy fields dropped)

def _release_memory():
    """Force GC and return freed pages to OS (Linux malloc_trim)."""
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


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
SPIRAL_CONCURRENCY = _env_int("GENESIS_SPIRAL_CONCURRENCY", 3, minimum=1)
SELF_EVOLUTION_ENABLED = _env_bool("GENESIS_SELF_EVOLUTION", False)
SELF_EVOLUTION_COOLDOWN = _env_int("GENESIS_SELF_EVOLUTION_COOLDOWN", 10, minimum=3)
SELF_EVOLUTION_UNTRACKED_COOLDOWN = _env_int("GENESIS_SELF_EVOLUTION_UNTRACKED_COOLDOWN", 5, minimum=2)

AUTO_PROMPT_FIRST = """你是 Genesis 的自主探索者。你的目标不是修 bug 或填空洞——而是基于已有知识，发现 Genesis 还没想到的新可能性。

## 用户方向
{directive}

## 方法
1. 用 `search_knowledge_nodes` 了解已有知识——这是你的起点，不是终点
2. 基于已有知识，提出一个大胆假设：Genesis 还可以怎样变得更强？
3. 在 Doctor 沙箱中实验验证你的假设
4. 记录发现——假设成立记录为什么成立，不成立记录为什么不成立，两者同样有价值

## 规则
- 围绕用户方向行动
- 每轮聚焦一个假设，做到位
- 已有知识直接用，你的价值在于发现新的
- 不要做琐碎的环境检查——只在实验需要时才检查环境

## 沙箱规则（严格遵守）
- **禁止直接修改 genesis/ 目录下的任何 .py 源文件**——那是正在运行的本体
- 所有代码修改必须通过 Doctor 沙箱执行：`shell doctor.sh exec <command>`
- **多行脚本用 `doctor.sh run`**：`shell doctor.sh run <<'SCRIPT' ... SCRIPT` — 绕过宿主 shell 变量展开，$VAR 只在容器内解析
- 修改后在沙箱中测试：`shell doctor.sh test`
- 查看修改差异：`shell doctor.sh diff`
- 你可以自由读取本体代码（read_file）用于诊断，但写入只能进沙箱

当前系统信号（仅供参考）：
{signals}"""

AUTO_PROMPT_CONTINUE = """继续自主探索。上一轮的结论是这一轮的起点。

## 用户方向
{directive}

上一轮工作记忆：
{knowledge_state}

上一轮探索前沿：
{frontier_state}

{history}

## 续跑原则
- 上一轮的结论直接作为已知事实，在此基础上推进
- 如果上一轮的假设已验证或已证伪，提出新的假设
- 追求让人意想不到的发现，不是流水线式的节点记录
- 每轮聚焦一个假设，做到位

## 沙箱规则（严格遵守）
- **禁止直接修改 genesis/ 目录下的任何 .py 源文件**——那是正在运行的本体
- 所有代码修改必须通过 Doctor 沙箱执行：`shell doctor.sh exec <command>`
- **多行脚本用 `doctor.sh run`**：`shell doctor.sh run <<'SCRIPT' ... SCRIPT` — 绕过宿主 shell 变量展开，$VAR 只在容器内解析
- 修改后在沙箱中测试：`shell doctor.sh test`
- 查看修改差异：`shell doctor.sh diff`
- 你可以自由读取本体代码（read_file）用于诊断，但写入只能进沙箱

## 自进化目标（优先于探索）
- **你的核心任务是修改 genesis/*.py 源码让系统变好**，不是写探针观察系统行为
- 探针测试（test_*.py）只用于验证修改是否正确，不是最终产出
- 每轮产出应该是：沙箱中有 genesis/*.py 的实际修改（通过 doctor.sh exec/write），而不是只有 tests/ 下的新文件
- 如果连续多轮只产出探针而没有源码修改，说明你在观察而不是改进——必须转向修改源码

当前信号（仅供参考）：
{signals}"""


AUTO_DEFAULT_DIRECTIVE = (
    "基于 Genesis 的元信息系统（知识库、经验图谱、Arena），改进 Genesis 系统本身。"
    "方法：读已有知识 → 提出假设 → 在 Doctor 沙箱中修改 genesis/*.py 源码 → 测试验证 → 记录发现。"
    "方向：修改源码让系统变好——修 bug、架构改进、新机制、性能优化、知识利用的新方式。"
    "所有代码修改必须在 Doctor 沙箱中进行（单行用 doctor.sh exec，多行脚本用 doctor.sh run），严禁直接改本体源码。"
    "核心产出是 genesis/*.py 的源码改进，不是探针测试。探针只用于验证假设，不是最终产出。"
    "每轮只做一件事，做到位。"
)

SPIRAL_PROMPT = """你的任务：为 Genesis 代码库中的一个文件创建 **结构性理解锚点**。

## 目标文件
`{filepath}`
来源：{discovered_from}

## 步骤
1. 用 `read_file` 读取目标文件的源码
2. 理解这个文件在 Genesis 系统中的角色和职责
3. 识别关键的类和函数，各一句话概括
4. 用 `record_context_node` 创建锚点节点：
   - node_id: `{anchor_id}`
   - title: 模块名 + 一句话职责
   - state_description: 角色 + 关键组件列表 + 对外接口

## 规则
- 只关注目标文件，一轮只做一个文件
- 大文件聚焦公开接口和关键逻辑，不需要逐行分析
- 不要做环境检查、不要搜索知识库、不要验证已有知识
- 锚点是组织索引，不是重复描述碎片已有内容
- 边连接由系统自动完成，你只需创建锚点

探索进度：{progress}"""

CROSS_MODULE_PROMPT = """你的任务：分析两个 Genesis 模块之间的 **因果协作关系**。

## 模块 A
`{filepath_a}` — {anchor_title_a}

## 模块 B
`{filepath_b}` — {anchor_title_b}

## 共享知识线索
{shared_context}

## 步骤
1. 用 `read_file` 读取两个模块的源码
2. 找到它们之间的**具体调用链**：A 的哪个函数/类调用了 B 的什么？或反过来？
3. 理解这个调用的**目的**：为什么 A 需要 B？去掉这个连接会怎样？
4. 用 `record_lesson_node` 记录一条因果关系：
   - title: "A → B: 一句话描述协作关系"
   - content: 具体调用链 + 目的 + 如果修改一方需要注意什么
   - tags: 两个模块名
   - resolves: "cross_module_understanding"

## 规则
- 只关注这两个模块之间的关系，不发散
- 找**具体代码证据**（函数名、import 路径），不要泛泛而谈
- 如果两个模块没有直接交互，记录"无直接依赖"也是有价值的发现
- 不要做环境检查、不要搜索知识库

进度：{progress}"""


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
        try:
            await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            # 子进程可能进入 D 状态（不可杀），communicate 永远等不到
            # 强制关闭 stdout transport 防止 FD 泄漏，放弃回收子进程
            logger.warning(f"doctor.sh {' '.join(args)} unkillable after SIGKILL (D state?), abandoning process")
            if proc.stdout:
                proc.stdout.close()
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
        preferred = getattr(router, "_preferred_provider_name", "xcode")
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

            # ── 1. 实践中失败的知识：失败次数 > 成功次数，需要修正 ──
            conn.row_factory = sqlite3.Row
            failing_rows = conn.execute(
                "SELECT node_id, title, type, usage_success_count, usage_fail_count "
                "FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV_%' "
                "AND usage_fail_count > 0 AND usage_fail_count > usage_success_count "
                "AND node_id NOT IN (SELECT target_id FROM node_edges WHERE relation = 'CONTRADICTS') "
                "ORDER BY usage_fail_count DESC LIMIT 5"
            ).fetchall()
            if failing_rows:
                lines = ["[实践中反复失败的知识 — 失败>成功，需要修正或重写]"]
                for r in failing_rows:
                    nid = r['node_id']
                    if session_shown_nodes and nid in session_shown_nodes:
                        continue
                    w, l = r['usage_success_count'] or 0, r['usage_fail_count'] or 0
                    lines.append(f"  {nid}: {r['title']} ({w}W/{l}L)")
                    if session_shown_nodes is not None:
                        session_shown_nodes.add(nid)
                if len(lines) > 1:
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

            # ── 3. 未经测试的新节点：从未使用过且至少 1 小时前创建 ──
            # 加 age 过滤：防止 auto 模式下 GP 本轮/本 session 刚产出的 LESSON
            # 立刻作为"未经实践"回注到下一轮信号，形成自引用回声循环
            untested_rows = conn.execute(
                "SELECT node_id, title, type "
                "FROM knowledge_nodes "
                "WHERE usage_count = 0 AND node_id NOT LIKE 'MEM_CONV_%' "
                "AND type IN ('LESSON', 'PATTERN', 'ASSET') "
                "AND node_id NOT IN (SELECT target_id FROM node_edges WHERE relation = 'CONTRADICTS') "
                "AND created_at < datetime('now', '-1 hour') "
                "ORDER BY created_at DESC LIMIT 3"
            ).fetchall()
            if untested_rows:
                lines = ["[未经实践的新知识 — 优先尝试挂载]"]
                for r in untested_rows:
                    lines.append(f"  {r['node_id']}: {r['title']} <{r['type']}>")
                sections.append("\n".join(lines))

            # ── 4. C-Phase 跨轮洞察：LESSON_C_ 节点（C 观察到 GP 自身看不到的行为规律）──
            lesson_c_rows = conn.execute(
                "SELECT kn.node_id, kn.title, nc.full_content FROM knowledge_nodes kn "
                "LEFT JOIN node_contents nc ON kn.node_id = nc.node_id "
                "WHERE kn.node_id LIKE 'LESSON_C_%' AND kn.type = 'LESSON' "
                "AND kn.node_id NOT IN (SELECT target_id FROM node_edges WHERE relation = 'CONTRADICTS') "
                "ORDER BY kn.created_at DESC LIMIT 5"
            ).fetchall()
            if lesson_c_rows:
                lines = ["[⚠ C-Phase 跨轮洞察 — 优先级最高 — GP 自身无法察觉的行为盲区]",
                         "这些洞察来自跨轮行为统计，不是单轮观察。如果这里说你在某模式中卡住，",
                         "你必须改变行为，不能继续同方向。"]
                for r in lesson_c_rows:
                    content_preview = (r['full_content'] or '')[:500]
                    lines.append(f"  {r['node_id']}: {r['title']}")
                    if content_preview:
                        lines.append(f"    → {content_preview}")
                sections.append("\n".join(lines))

            # ── 5. C-Phase 产出：DISCOVERY 和 PATTERN 节点可见性 ──
            disc_rows = conn.execute(
                "SELECT node_id, title FROM knowledge_nodes "
                "WHERE type = 'DISCOVERY' ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            pat_rows = conn.execute(
                "SELECT node_id, title FROM knowledge_nodes "
                "WHERE type = 'PATTERN' ORDER BY created_at DESC LIMIT 3"
            ).fetchall()
            if disc_rows or pat_rows:
                lines = ["[C-Phase 产出 — DISCOVERY/PATTERN 节点]"]
                for r in pat_rows:
                    lines.append(f"  {r['node_id']}: {r['title']}")
                for r in disc_rows:
                    lines.append(f"  {r['node_id']}: {r['title']}")
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


def _summarize_event_args(args: dict | None) -> dict:
    if not isinstance(args, dict):
        return {}
    summarized = {}
    for idx, (key, value) in enumerate(args.items()):
        if idx >= 8:
            break
        if isinstance(value, str):
            limit = 300 if key in ("command", "query", "path", "file_path", "cwd") else 120
            summarized[key] = _trim_frontier_item(value, limit)
        elif isinstance(value, (int, float, bool)) or value is None:
            summarized[key] = value
        elif isinstance(value, (list, tuple)):
            summarized[key] = [_trim_frontier_item(str(v), 80) for v in list(value)[:5]]
        elif isinstance(value, dict):
            nested = {}
            for nested_idx, (nested_key, nested_value) in enumerate(value.items()):
                if nested_idx >= 5:
                    break
                if isinstance(nested_value, str):
                    nested[nested_key] = _trim_frontier_item(nested_value, 80)
                elif isinstance(nested_value, (int, float, bool)) or nested_value is None:
                    nested[nested_key] = nested_value
                else:
                    nested[nested_key] = type(nested_value).__name__
            summarized[key] = nested
        else:
            summarized[key] = type(value).__name__
    return summarized


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
    """Detect genuine workspace drift — only trigger on explicit sync-mismatch phrases.

    Previous implementation used broad keyword combos (e.g. "doctor" + "snapshot")
    which were always-true when GP works inside the Doctor sandbox, causing every
    round to trigger reanchor and forcing GP into repetitive environment verification.
    Now only fires on very specific phrases that indicate actual host↔container drift.
    """
    response_text = str(response or "")
    combined = response_text.strip()
    if not combined:
        return False, ""
    # Only trigger on phrases that unambiguously indicate host↔sandbox mismatch
    explicit_drift_phrases = (
        "不会自动反映到 Doctor",
        "不会自动反映到 /workspace",
        "宿主仓库里的修改不会同步",
        "宿主和容器的代码不一致",
        "修改了宿主但容器里没变",
    )
    if any(phrase in combined for phrase in explicit_drift_phrases):
        return True, "检测到宿主↔沙箱同步漂移的明确描述"
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


def _build_frontier_state(round_index, response, kb_delta_summary, kb_changed, node_telemetry, round_events, prior_reanchor_streak=0, consecutive_dry=0, progress_class="", kb_delta=None):
    local_goal = _extract_blueprint_goal(round_events)
    candidate_issue = _extract_candidate_issue(response)
    next_checks = _extract_next_checks(response)
    tool_names = _collect_tool_names(round_events)
    reanchor_required, reanchor_reason = _detect_reanchor_signal(response, round_events)
    reanchor_streak = prior_reanchor_streak + 1 if reanchor_required else 0
    observations = [f"KB {kb_delta_summary}", node_telemetry]
    # Inject actual node titles so GP knows what it already verified
    # (not just meta counts like "+3新/8更新" which tell GP nothing about content)
    if kb_delta:
        new_titles = [n.get("title", "?")[:60] for n in (kb_delta.get("new_nodes") or [])[:3]]
        upd_titles = [n.get("title", "?")[:60] for n in (kb_delta.get("updated_nodes") or [])[:3]]
        if new_titles:
            observations.append("本轮新增: " + " | ".join(new_titles))
        if upd_titles:
            observations.append("本轮更新: " + " | ".join(upd_titles))
    if candidate_issue and candidate_issue not in ("未提取", "未从上轮回复中提取到稳定问题定义"):
        observations.insert(0, f"已确认: {candidate_issue[:150]}")
    if tool_names:
        observations.append("工具结果: " + ", ".join(tool_names))
    if reanchor_required:
        observations.append(f"锚定状态: 已连续 {reanchor_streak} 轮需要重新锚定" if reanchor_streak >= 2 else "锚定状态: 需要重新锚定")
    observations.append("文本回复: 有" if response and str(response).strip() else "文本回复: 无")
    carry_warnings = []
    # ── Strong-but-dry: GP is active but producing no durable outcome ──
    # This is the key signal that breaks the verification loop.
    # kb_changed=True + tools used → old logic never warned → GP kept re-verifying.
    if progress_class in ("strong", "soft") and consecutive_dry >= 2:
        carry_warnings.insert(0, f"已连续{consecutive_dry}轮有活动但无持久产出(progress={progress_class})——停止重复验证，转向新问题")
    if response and not kb_changed:
        carry_warnings.append("上轮无新知识写入，该方向可能已探索充分——优先切换到新方向")
    if not tool_names:
        carry_warnings.append("上轮无工具调用——如果相关知识已存在，直接转向新问题")
    if reanchor_required:
        carry_warnings.insert(0, f"检测到信息错位：{reanchor_reason}")
    if reanchor_streak >= 2:
        carry_warnings.insert(0, f"信息错位已连续 {reanchor_streak} 轮出现；如重锚后仍无新的外部证据，应停止当前路径")
    if not next_checks:
        if consecutive_dry >= 3:
            next_checks = ["当前方向已连续空转，必须切换到完全不同的新问题", "不要再次验证已有结论"]
        elif kb_changed:
            next_checks = ["在已确认事实基础上探索新的相邻问题", "避免重复验证已知事实"]
        else:
            next_checks = ["当前方向已无新信息，切换到新问题方向", "不要重复验证已有结论"]
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
    # issue: frontier 优先（反映本轮实际发现），raw_state 仅做兜底
    # 旧逻辑：非 reanchor 时 raw_state.issue 优先 → V4Loop 纯透传不修改 → 自引用循环冻结
    issue_seed = (
        frontier_state.get("candidate_issue") or frontier_state.get("local_goal") or raw_state.get("issue") or "待重新锁定"
    )
    issue = _trim_frontier_item(issue_seed, 240)
    # verified_facts: frontier observations 优先（本轮新鲜数据），raw_state 补充
    frontier_obs = _dedupe_trimmed_items(frontier_state.get("observations") or [], 220, 3)
    raw_facts = _dedupe_trimmed_items(raw_state.get("verified_facts") or [], 220, 3)
    verified_facts = _dedupe_trimmed_items(frontier_obs + raw_facts, 220, 5)
    # failed_attempts / next_checks: frontier 优先，raw_state 补充
    frontier_warnings = _dedupe_trimmed_items(frontier_state.get("carry_warnings") or [], 220, 3)
    raw_failures = _dedupe_trimmed_items(raw_state.get("failed_attempts") or [], 220, 3)
    failed_attempts = _dedupe_trimmed_items(frontier_warnings + raw_failures, 220, 5)
    next_checks = _dedupe_trimmed_items(
        (frontier_state.get("next_checks") or []) + (raw_state.get("next_checks") or []), 180, 5
    )
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


def _is_source_path(path: str) -> bool:
    """Check if a file path is a genesis source file (not test/scratch/runtime)."""
    p = path.lower()
    return ("/genesis/" in p and "/tests/" not in p and "/runtime/" not in p and "/scratch/" not in p)


def _classify_auto_round_progress(response, round_events, kb_changed, frontier_state=None, is_error=False, outcome_detected=False):
    if is_error:
        signals = ["progress=error"]
        response_text = (response or "").strip()
        if response_text:
            signals.append(f"reply={len(response_text)}c")
        signals.append("error_response")
        return {"activity_detected": False, "activity_summary": " | ".join(signals), "progress_class": "error", "outcome_detected": False}

    result_events = _collect_round_result_events(round_events)
    tool_names = []
    for entry in result_events:
        name = (entry.get("name") or "").strip()
        if name and name not in tool_names:
            tool_names.append(name)
        if len(tool_names) >= 4:
            break
    # Collect both result previews AND tool_start command args to detect doctor.sh usage
    preview_text = "\n".join(_compact_whitespace(entry.get("result_preview") or "") for entry in result_events[:10]).lower()
    # Also scan tool_start events for shell command content (GP uses shell to run doctor.sh)
    shell_cmd_text = ""
    for evt in round_events:
        if evt.get("type") == "tool_start" and evt.get("name") == "shell":
            args = evt.get("args") or {}
            if isinstance(args, dict):
                action = str(args.get("action") or "")
                command = str(args.get("command") or "")
                cwd = str(args.get("cwd") or "")
                shell_cmd_text += " " + _compact_whitespace(f"{action} {command} {cwd}").lower()
            elif args:
                shell_cmd_text += " " + _compact_whitespace(str(args)).lower()
    combined_text = preview_text + " " + shell_cmd_text
    ran_tests = "doctor.sh test" in combined_text or "pytest" in combined_text
    inspected_diff = "doctor.sh diff" in combined_text or "git diff" in combined_text or "diff --git" in combined_text
    touched_files = (
        any(name in ("write_file", "edit_file", "replace_in_file", "append_file") for name in tool_names)
        or "sed -i" in combined_text or "write_text(" in combined_text or "text = text.replace(" in combined_text
        or "doctor.sh exec" in combined_text
    )
    response_text = (response or "").strip()
    stable_issue = bool(frontier_state and frontier_state.get("candidate_issue")
                        and frontier_state.get("candidate_issue") not in ("未提取", "未从上轮回复中提取到稳定问题定义"))
    reanchor_required = bool(frontier_state and frontier_state.get("reanchor_required"))
    # ── Progress classification ──
    # outcome_detected = ground truth from diff-status snapshot comparison (passed in)
    # This replaces all indirect signal synthesis (new_source_this_round, cooldowns, etc.)
    if outcome_detected:
        progress_class = "evidence"  # sandbox diff changed → real durable outcome
    elif touched_files or ran_tests or inspected_diff:
        progress_class = "strong"   # GP was active but sandbox diff unchanged
    elif result_events:
        progress_class = "evidence" if not (touched_files or ran_tests) else "strong"
    elif response_text or stable_issue:
        progress_class = "soft"
    else:
        progress_class = "idle"
    activity_detected = progress_class in ("strong", "evidence")

    # Source-written signal (for display only, not for outcome_detected)
    source_written = any(
        name in ("write_file", "edit_file", "replace_in_file") and _is_source_path(
            str((entry.get("data") or {}).get("path") or (entry.get("args") or {}).get("path") or "")
        )
        for entry in result_events
        for name in [entry.get("name", "")]
    )

    signals = [f"progress={progress_class}"]
    if kb_changed: signals.append("kb")
    if touched_files: signals.append("write")
    if source_written: signals.append("source")
    if ran_tests: signals.append("test")
    if inspected_diff: signals.append("diff")
    if tool_names: signals.append(f"tools={','.join(tool_names[:3])}")
    if stable_issue: signals.append("issue")
    if reanchor_required: signals.append("reanchor")
    if response_text: signals.append(f"reply={len(response_text)}c")
    if progress_class == "idle": signals.append("no_external_progress")
    if outcome_detected: signals.append("outcome✓")
    return {"activity_detected": activity_detected, "activity_summary": " | ".join(signals), "progress_class": progress_class, "outcome_detected": outcome_detected}


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
  "next_focus": "第一轮的方向性目标（描述要调查/修复什么，不要写工具命令）",
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
  "next_focus": "下一轮的方向性目标（描述要调查/修复什么，不要写工具命令）",
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
        if "反复失效" in line or "Arena" in line:
            current_section = "arena"
        elif "知识空洞" in line or "VOID" in line:
            current_section = "void"
        elif "待验证" in line or "置信度" in line:
            current_section = "low_conf"
        elif "C-Phase" in line or "DISCOVERY" in line or "未经实践的新知识" in line or "优先尝试挂载" in line:
            current_section = "c_phase"
        elif line.startswith("  ") and ":" in line:
            # 缩进行 = 某 section 下的具体条目
            item = line.strip()
            if current_section == "arena":
                arena_items.append(item)
            elif current_section == "low_conf":
                low_conf_items.append(item)
            elif current_section == "void":
                void_items.append(item)
            elif current_section == "c_phase":
                low_conf_items.append(item)  # C-Phase 产出也可作为验证方向
    # 优先级：Arena 翻车 > VOID 空洞 > 低置信/C-Phase > 通用探索
    if arena_items:
        pick = arena_items[0]
        return f"聚焦验证这条翻车知识并改进: {pick[:120]}"
    if void_items:
        pick = void_items[round_num % max(len(void_items), 1)]
        return f"调查这个知识空洞并尝试填充: {pick[:120]}"
    if low_conf_items:
        pick = low_conf_items[round_num % max(len(low_conf_items), 1)]
        return f"优先验证并利用这条 C-Phase 新知识: {pick[:120]}"
    return "继续探索 Genesis 系统，寻找可改进之处并在沙箱中实践"


def _compute_cross_round_observations(round_log: list, self_evolution=None) -> dict:
    """Compute cross-round behavioral observations for C-Phase.
    These are patterns GP cannot see about its own behavior —
    not corrections, but objective observations of behavioral blind spots.

    Design principle: only use OUTCOME signals (what actually happened),
    not ACTIVITY signals (what GP appeared to do). Activity signals like
    progress_class are inflated by probe writing and mislead C into
    thinking GP is productive when it's spinning in place.
    """
    if not round_log:
        return {}

    recent = round_log[-20:]
    total_rounds = len(round_log)

    # 1. GP write targets: what file categories GP writes to
    #    Count UNIQUE files, not tool call count — GP writes same file 3x (probe+test+impl)
    #    which inflates tests/scratch counts and deflates source_write_ratio.
    write_file_sets = {"tests": set(), "scratch": set(), "source": set(), "other": set()}
    for r in recent:
        events = r.get("events") or []
        for evt in events:
            if evt.get("type") == "tool_result" and evt.get("name") == "write_file":
                data = evt.get("data") or {}
                path = str(data.get("path") or data.get("args", {}).get("path") or "")
                if not path:
                    continue
                if "/tests/" in path or path.startswith("tests/"):
                    write_file_sets["tests"].add(path)
                elif "/scratch/" in path or "/runtime/" in path:
                    write_file_sets["scratch"].add(path)
                elif "/genesis/" in path:
                    write_file_sets["source"].add(path)
                else:
                    write_file_sets["other"].add(path)
    write_categories = {k: len(v) for k, v in write_file_sets.items() if v}

    # 1b. Source write ratio: the key outcome signal.
    #     If GP writes 0% to genesis/, it's only producing probes/scratch,
    #     never touching production code. This is the real "productivity" metric.
    total_writes = sum(write_categories.values())
    source_write_ratio = write_categories["source"] / total_writes if total_writes > 0 else 0

    # 2. Auto-apply outcome (grounded in apply_history which records both success and failure)
    apply_attempts = 0
    apply_successes = 0
    apply_blocked_reasons = []
    if self_evolution:
        apply_attempts = len(self_evolution.apply_history)
        apply_successes = sum(1 for h in self_evolution.apply_history if h.get("status") == "success")
        apply_blocked_reasons = [h.get("reason", "?") for h in self_evolution.apply_history if h.get("status") != "success"]

    # 3. KB change rate: how many rounds actually changed the knowledge base
    #    This is an outcome signal — kb_changed is set by actual vault mutations.
    kb_changed_rounds = sum(1 for r in recent if r.get("kb_changed"))

    # 4. LESSON count per round (NOT titles — titles create echo chamber)
    #    Just the number tells C whether it's producing or passing.
    lesson_counts = []
    for r in recent:
        c_sum = r.get("c_phase_summary") or {}
        n = c_sum.get("lessons_recorded", 0)
        if n > 0:
            lesson_counts.append(n)
    lesson_total = sum(lesson_counts)
    lesson_rounds = len(lesson_counts)

    # 5. Sandbox file stability: from cooldown state
    #    How many files are at what stable_count — this tells C whether
    #    GP's changes are converging or churning.
    sandbox_stability = {"stable_0": 0, "stable_1_2": 0, "stable_3_plus": 0}
    if self_evolution and self_evolution.file_cooldowns:
        for v in self_evolution.file_cooldowns.values():
            sc = v.get("stable_count", 0)
            if sc == 0:
                sandbox_stability["stable_0"] += 1
            elif sc <= 2:
                sandbox_stability["stable_1_2"] += 1
            else:
                sandbox_stability["stable_3_plus"] += 1

    # 6. Error rounds (reliable — only set on actual exceptions)
    error_count = sum(1 for r in recent if r.get("progress_class") == "error")

    obs = {
        "total_rounds": total_rounds,
        "write_targets": {k: v for k, v in write_categories.items() if v > 0},
        "source_write_ratio": round(source_write_ratio, 2),
        "auto_apply_attempts": apply_attempts,
        "auto_apply_successes": apply_successes,
        "auto_apply_blocked_reasons": apply_blocked_reasons[-5:],
        "kb_change_rate": f"{kb_changed_rounds}/{len(recent)}",
        "lesson_total_in_window": lesson_total,
        "lesson_rounds_in_window": lesson_rounds,
        "sandbox_stability": sandbox_stability,
        "error_rounds_in_window": error_count,
        "window_size": len(recent),
    }
    return obs


def _compact_round_history(round_log: list, last_n: int = 10) -> str:
    """压缩最近 N 轮历史为紧凑文本，供 planner 审查。"""
    entries = []
    for r in round_log[-last_n:]:
        parts = [f"R{r['round']}"]
        parts.append(r.get("progress_class", "?"))
        if r.get("kb_delta_summary"):
            parts.append(f"KB:{r['kb_delta_summary']}")
        c_sum = r.get("c_phase_summary") or {}
        if c_sum:
            parts.append(f"C:lessons={c_sum.get('lessons_recorded', 0)}")
        ks = r.get("knowledge_search_count", 0)
        if ks:
            parts.append(f"search={ks}")
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


# ─── Session-Level Structural Controls ──────────────────────────────

class TopicTracker:
    """Structural topic tracking — hard round limit per topic.

    Uses character bigram Jaccard similarity (Chinese-friendly)
    to detect when GP keeps working on the same topic across rounds.
    """

    MAX_ROUNDS_PER_TOPIC = 5
    SIMILARITY_THRESHOLD = 0.35

    def __init__(self):
        self.topics: list = []
        self.active_idx: int | None = None

    @staticmethod
    def _bigrams(text: str) -> set:
        t = text.strip().lower()
        return {t[i:i+2] for i in range(len(t) - 1)} if len(t) >= 2 else ({t} if t else set())

    def _similarity(self, a: str, b: str) -> float:
        sa, sb = self._bigrams(a), self._bigrams(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _find_match(self, candidate: str) -> int | None:
        best_idx, best_sim = None, 0.0
        for i, t in enumerate(self.topics):
            sim = self._similarity(candidate, t["topic"])
            if sim >= self.SIMILARITY_THRESHOLD and sim > best_sim:
                best_idx, best_sim = i, sim
        return best_idx

    def update(self, round_num: int, candidate_issue: str, had_progress: bool) -> dict:
        _skip = ("未提取", "未从上轮回复中提取到稳定问题定义", "待重新锁定", "")
        if not candidate_issue or candidate_issue in _skip:
            return {"action": "continue", "topic_info": None, "message": ""}
        match_idx = self._find_match(candidate_issue)
        if match_idx is not None:
            topic = self.topics[match_idx]
            topic["rounds_spent"] += 1
            topic["last_round"] = round_num
            self.active_idx = match_idx
            if topic["rounds_spent"] >= self.MAX_ROUNDS_PER_TOPIC:
                topic["verdict"] = "exhausted"
                self.active_idx = None
                return {
                    "action": "force_switch",
                    "topic_info": topic,
                    "message": f"话题「{topic['topic'][:60]}」已持续 {topic['rounds_spent']} 轮，强制切换",
                }
            if topic["rounds_spent"] >= 3 and not had_progress:
                return {
                    "action": "suggest_switch",
                    "topic_info": topic,
                    "message": f"话题「{topic['topic'][:60]}」已 {topic['rounds_spent']} 轮且无新进展",
                }
            return {"action": "continue", "topic_info": topic, "message": ""}
        new_topic = {
            "topic": candidate_issue[:200], "first_round": round_num,
            "last_round": round_num, "rounds_spent": 1, "verdict": "active",
        }
        self.topics.append(new_topic)
        self.active_idx = len(self.topics) - 1
        return {"action": "continue", "topic_info": new_topic, "message": ""}

    def get_exhausted_topics(self) -> list:
        return [t["topic"][:80] for t in self.topics if t["verdict"] == "exhausted"]

    def format_for_prompt(self) -> str:
        if not self.topics:
            return ""
        lines = ["[已探索话题——标记为✗的话题不得再次探索]"]
        for t in self.topics:
            if t["verdict"] == "exhausted":
                lines.append(f"  ✗ {t['topic'][:80]} ({t['rounds_spent']}轮, 已用尽)")
            else:
                lines.append(f"  → {t['topic'][:80]} ({t['rounds_spent']}轮)")
        return "\n".join(lines)


class ActionHistory:
    """Session-level cross-round action deduplication.

    Records tool calls + results. Surfaces repeated actions in prompt
    so GP sees *exactly* what has already been executed.
    """

    REPEAT_THRESHOLD = 2
    ARG_PRIORITY = ("file_path", "path", "command", "query", "pattern", "name", "symbol", "directory", "url")
    ARG_IGNORE = {"cwd", "job_id", "is_daemon"}

    def __init__(self):
        self.actions: dict = {}  # key → {count, last_round}

    def _action_key(self, name: str, event: dict) -> str:
        args = event.get("args") or {}
        arg_desc = self._summarize_args(name, args)
        if arg_desc:
            return f"{name}:{arg_desc}"
        preview = (event.get("result_preview") or "").strip()
        return f"{name}:{preview[:80]}" if preview else name

    def _summarize_args(self, tool_name: str, args: dict) -> str:
        if not isinstance(args, dict):
            return ""
        parts = []
        for key in self.ARG_PRIORITY:
            value = args.get(key)
            if value in (None, "", [], {}):
                continue
            parts.append(f"{key}={_trim_frontier_item(str(value), 120)}")
        if tool_name == "read_file" and (args.get("offset") is not None or args.get("limit") is not None):
            parts.append(f"slice={args.get('offset')}:{args.get('limit')}")
        if not parts:
            for key, value in args.items():
                if key in self.ARG_IGNORE or value in (None, "", [], {}):
                    continue
                if isinstance(value, str):
                    parts.append(f"{key}={_trim_frontier_item(value, 80)}")
                elif isinstance(value, (int, float, bool)):
                    parts.append(f"{key}={value}")
                else:
                    parts.append(f"{key}={type(value).__name__}")
                if len(parts) >= 3:
                    break
        return " | ".join(parts[:3])

    def record_round(self, round_num: int, round_events: list):
        for event in round_events:
            if event.get("type") not in ("tool_result", "search_result"):
                continue
            name = (event.get("name") or "").strip()
            if not name or name in ("search_knowledge_nodes", "record_lesson_node"):
                continue
            key = self._action_key(name, event)
            if key in self.actions:
                self.actions[key]["count"] += 1
                self.actions[key]["last_round"] = round_num
            else:
                self.actions[key] = {"count": 1, "last_round": round_num}

    def get_repeated(self) -> list:
        return [
            (key, info["count"])
            for key, info in sorted(self.actions.items(), key=lambda x: -x[1]["count"])
            if info["count"] >= self.REPEAT_THRESHOLD
        ][:8]

    def format_for_prompt(self) -> str:
        repeated = self.get_repeated()
        if not repeated:
            return ""
        lines = ["[以下操作已多次执行——结果已知，不要重复]"]
        for key, count in repeated:
            desc = key.split(":", 1)[-1][:80] if ":" in key else key
            lines.append(f"  ×{count}: {desc}")
        return "\n".join(lines)


class SpiralPioneer:
    """Vault-grounded organic traversal of Genesis codebase.

    Base  = vault knowledge nodes (what Genesis already knows about itself).
    Priority = files with scattered fragments but no organizing anchor (CTX_MODULE_).
    Growth = after anchoring fragmented files, follow imports to pioneer new territory.
    State persists to disk across sessions.
    """

    SEED = "discord_bot.py"
    ANCHOR_PREFIX = "CTX_MODULE_"
    # Noise filter for deterministic edge building
    _EDGE_NOISE_RE = re.compile(
        r'read_file\s*\('
        r'|\[ENV_FACT\]'
        r'|\[TOOL_BEHAVIOR\]'
        r'|(无需|不用|避免|跳过|不再).*(shell|list_directory)'
        r'|全程不?使?用\s*(shell|search)'
    )

    def __init__(self, state_path: str | None = None, project_root: str | None = None):
        self._state_path = Path(state_path) if state_path else Path("runtime/spiral_pioneer_state.json")
        self._root = Path(project_root) if project_root else Path(".")
        # 与 NodeVault 使用相同的 DB 路径（新路径优先，旧路径兜底）
        _new_db = Path.home() / ".genesis" / "workshop_v4.sqlite"
        _legacy_db = Path.home() / ".nanogenesis" / "workshop_v4.sqlite"
        self._db_path = _new_db if _new_db.exists() else _legacy_db
        self.covered: list = []
        self.frontier: list = []
        self._load()
        self._refresh_from_vault()
        self._refresh_all_edges()

    def _refresh_all_edges(self):
        """Rebuild edges for all covered files in one pass (idempotent — INSERT OR IGNORE)."""
        if not self.covered or not self._db_path.exists():
            return
        try:
            conn = sqlite3.connect(str(self._db_path))
            rows = conn.execute(
                "SELECT n.node_id, n.title, nc.full_content "
                "FROM knowledge_nodes n "
                "LEFT JOIN node_contents nc ON n.node_id = nc.node_id "
                "WHERE n.node_id NOT LIKE 'MEM_CONV_%' AND n.node_id NOT LIKE 'CTX_MODULE_%'"
            ).fetchall()
            # Pre-compute file patterns and generic-node counts once
            all_files = self._discover_genesis_files()
            generic_stems = {"__init__", "base", "models", "utils", "config", "constants", "types"}
            all_patterns = {}
            for fp in all_files:
                s = Path(fp).stem
                md = fp.replace("/", ".").replace(".py", "")
                all_patterns[fp] = [fp, md] if s in generic_stems else [fp, md, f"/{s}.py"]
            node_file_counts = {}
            for nid, title, content in rows:
                text = f"{title or ''} {content or ''}"
                node_file_counts[nid] = sum(1 for _, pats in all_patterns.items() if any(p in text for p in pats))
            # Build edges for each covered file
            total = 0
            for filepath in self.covered:
                anchor_id = self.anchor_id_for(filepath)
                patterns = all_patterns.get(filepath, [])
                if not patterns:
                    continue
                for nid, title, content in rows:
                    text = f"{title or ''} {content or ''}"
                    if not any(p in text for p in patterns):
                        continue
                    if self._EDGE_NOISE_RE.search(title or ''):
                        continue
                    if node_file_counts.get(nid, 0) >= 5:
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation, weight) VALUES (?,?,?,?)",
                        (anchor_id, nid, "RELATED_TO", 0.5)
                    )
                    total += 1
            conn.commit()
            conn.close()
            if total:
                logger.info(f"SpiralPioneer: refreshed edges for {len(self.covered)} files ({total} inserts)")
        except Exception as e:
            logger.warning(f"SpiralPioneer: edge refresh failed: {e}")

    def _load(self):
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                self.covered = data.get("covered", [])
                self.frontier = data.get("frontier", [])
        except Exception:
            self.covered = []
            self.frontier = []

    def _save(self):
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps({
                "covered": self.covered,
                "frontier": self.frontier,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"SpiralPioneer state save failed: {e}")

    # ── vault coverage check ──

    def _discover_genesis_files(self) -> list:
        files = []
        for pkg in ["genesis"]:
            pkg_path = self._root / pkg
            if pkg_path.is_dir():
                for py in pkg_path.rglob("*.py"):
                    rel = str(py.relative_to(self._root))
                    if "__pycache__" not in rel:
                        files.append(rel)
        for py in self._root.glob("*.py"):
            files.append(py.name)
        return sorted(set(files))

    def _query_vault_file_map(self) -> dict:
        """Query vault → {filepath: {fragments: [{id,title}], has_anchor: bool}}"""
        if not self._db_path.exists():
            return {}
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT n.node_id, n.title, nc.full_content "
                "FROM knowledge_nodes n "
                "LEFT JOIN node_contents nc ON n.node_id = nc.node_id"
            ).fetchall()
            conn.close()
        except Exception as e:
            logger.warning(f"SpiralPioneer vault query failed: {e}")
            return {}
        all_files = self._discover_genesis_files()
        generic_stems = {"__init__", "base", "models", "utils", "config", "constants", "types"}
        file_patterns = {}
        for fp in all_files:
            stem = Path(fp).stem
            module_dot = fp.replace("/", ".").replace(".py", "")
            if stem in generic_stems:
                file_patterns[fp] = [fp, module_dot]
            else:
                file_patterns[fp] = [fp, module_dot, f"/{stem}.py"]
        file_map = {}
        for node_id, title, content in rows:
            text = f"{title or ''} {content or ''}"
            for fp, patterns in file_patterns.items():
                if any(p in text for p in patterns):
                    if fp not in file_map:
                        file_map[fp] = {"fragments": [], "has_anchor": False}
                    file_map[fp]["fragments"].append({"id": node_id, "title": title or ""})
                    if node_id.startswith(self.ANCHOR_PREFIX):
                        file_map[fp]["has_anchor"] = True
        return file_map

    def _query_existing_anchors(self) -> set:
        """Query vault for all files that already have CTX_MODULE_ anchor nodes."""
        if not self._db_path.exists():
            return set()
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT node_id FROM knowledge_nodes WHERE node_id LIKE 'CTX_MODULE_%'"
            ).fetchall()
            conn.close()
        except Exception:
            return set()
        # Reverse map: anchor_id → filepath
        all_files = self._discover_genesis_files()
        anchor_to_file = {self.anchor_id_for(fp): fp for fp in all_files}
        anchored = set()
        for (nid,) in rows:
            fp = anchor_to_file.get(nid)
            if fp:
                anchored.add(fp)
        return anchored

    def _refresh_from_vault(self):
        """Rebuild frontier: vault fragments first, then import-graph expansion."""
        file_map = self._query_vault_file_map()
        covered_set = set(self.covered)
        frontier_files = {item["filepath"] for item in self.frontier}

        # Auto-cover: files that already have CTX_MODULE_ anchors in vault
        already_anchored = self._query_existing_anchors()
        for fp in already_anchored:
            if fp not in covered_set:
                self.covered.append(fp)
                covered_set.add(fp)
                logger.debug(f"SpiralPioneer: auto-covered {fp} (anchor exists)")

        # Phase 1: files with vault fragments but no anchor → HIGH priority
        fragmented = [
            (fp, info) for fp, info in file_map.items()
            if info["fragments"]
            and fp not in already_anchored
            and fp not in covered_set and fp not in frontier_files
        ]
        fragmented.sort(key=lambda x: len(x[1]["fragments"]), reverse=True)
        insert_pos = 0
        for fp, info in fragmented:
            self.frontier.insert(insert_pos, {
                "filepath": fp, "from": "vault_fragments",
                "fragments": info["fragments"][:10],
            })
            frontier_files.add(fp)
            insert_pos += 1

        # Phase 2: from known files (covered + fragmented), follow imports → new territory
        known_files = set(covered_set) | set(file_map.keys())
        for fp in sorted(known_files):
            for imp in self._extract_local_imports(fp):
                if imp not in covered_set and imp not in frontier_files:
                    frags = file_map.get(imp, {}).get("fragments", [])
                    self.frontier.append({
                        "filepath": imp, "from": fp,
                        "fragments": frags[:10] if frags else [],
                    })
                    frontier_files.add(imp)

        # Seed fallback
        if not self.covered and not self.frontier:
            self.frontier.append({"filepath": self.SEED, "from": "(入口)", "fragments": []})

        self._save()

    # ── ast import extraction ──

    def _extract_local_imports(self, filepath: str) -> list:
        import ast as _ast
        full_path = self._root / filepath
        if not full_path.exists():
            return []
        try:
            source = full_path.read_text(encoding="utf-8")
            tree = _ast.parse(source)
        except Exception:
            return []
        found = []
        for node in _ast.walk(tree):
            modules = []
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    if alias.name:
                        modules.append(alias.name)
            elif isinstance(node, _ast.ImportFrom) and node.module:
                modules.append(node.module)
                for alias in node.names:
                    if alias.name and alias.name != "*":
                        modules.append(f"{node.module}.{alias.name}")
            for mod in modules:
                rel = mod.replace(".", "/")
                for cand in [rel + ".py", rel + "/__init__.py"]:
                    if (self._root / cand).exists():
                        if cand not in found:
                            found.append(cand)
                        break
        return found

    # ── task selection ──

    @staticmethod
    def anchor_id_for(filepath: str) -> str:
        parts = Path(filepath).with_suffix("").parts
        if parts and parts[0] == "genesis":
            parts = parts[1:]
        return "CTX_MODULE_" + "_".join(p.upper() for p in parts)

    def next_task(self) -> dict | None:
        covered_set = set(self.covered)
        for item in self.frontier:
            fp = item["filepath"]
            if fp not in covered_set and (self._root / fp).exists():
                return {
                    "filepath": fp,
                    "discovered_from": item.get("from", ""),
                    "fragments": item.get("fragments", []),
                    "anchor_id": self.anchor_id_for(fp),
                }
        if self._expand_frontier_with_all_files() > 0:
            return self.next_task()
        return None

    def _build_edges_for_anchor(self, filepath: str) -> int:
        """Deterministic edge building: match vault nodes to filepath, filter noise, INSERT edges."""
        anchor_id = self.anchor_id_for(filepath)
        if not self._db_path.exists():
            return 0
        stem = Path(filepath).stem
        module_dot = filepath.replace("/", ".").replace(".py", "")
        generic_stems = {"__init__", "base", "models", "utils", "config", "constants", "types"}
        patterns = [filepath, module_dot]
        if stem not in generic_stems:
            patterns.append(f"/{stem}.py")
        try:
            conn = sqlite3.connect(str(self._db_path))
            rows = conn.execute(
                "SELECT n.node_id, n.title, nc.full_content "
                "FROM knowledge_nodes n "
                "LEFT JOIN node_contents nc ON n.node_id = nc.node_id "
                "WHERE n.node_id NOT LIKE 'MEM_CONV_%' AND n.node_id NOT LIKE 'CTX_MODULE_%'"
            ).fetchall()
            # Pre-compute: skip nodes matching too many files (generic)
            all_files = self._discover_genesis_files()
            all_patterns = {}
            for fp in all_files:
                s = Path(fp).stem
                md = fp.replace("/", ".").replace(".py", "")
                all_patterns[fp] = [fp, md] if s in generic_stems else [fp, md, f"/{s}.py"]
            node_file_counts = {}
            for nid, title, content in rows:
                text = f"{title or ''} {content or ''}"
                node_file_counts[nid] = sum(1 for fp2, pats in all_patterns.items() if any(p in text for p in pats))
            inserted = 0
            for nid, title, content in rows:
                text = f"{title or ''} {content or ''}"
                if not any(p in text for p in patterns):
                    continue
                if self._EDGE_NOISE_RE.search(title or ''):
                    continue
                if node_file_counts.get(nid, 0) >= 5:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation, weight) VALUES (?,?,?,?)",
                    (anchor_id, nid, "RELATED_TO", 0.5)
                )
                inserted += 1
            conn.commit()
            conn.close()
            logger.info(f"SpiralPioneer: built {inserted} edges for {anchor_id}")
            return inserted
        except Exception as e:
            logger.warning(f"SpiralPioneer: edge building failed for {filepath}: {e}")
            return 0

    def _expand_frontier_with_all_files(self):
        """When import-graph frontier is exhausted, add all undiscovered genesis files."""
        covered_set = set(self.covered)
        frontier_fps = {item["filepath"] for item in self.frontier}
        all_files = self._discover_genesis_files()
        added = 0
        for fp in all_files:
            if fp not in covered_set and fp not in frontier_fps:
                self.frontier.append({"filepath": fp, "from": "(全量扫描)", "fragments": []})
                added += 1
        if added:
            self._save()
            logger.info(f"SpiralPioneer: expanded frontier with {added} undiscovered files")
        return added

    def next_batch(self, n: int) -> list:
        """Get up to n distinct tasks for parallel processing."""
        tasks = []
        covered_set = set(self.covered)
        taken = set()
        for item in self.frontier:
            if len(tasks) >= n:
                break
            fp = item["filepath"]
            if fp not in covered_set and fp not in taken and (self._root / fp).exists():
                tasks.append({
                    "filepath": fp,
                    "discovered_from": item.get("from", ""),
                    "fragments": item.get("fragments", []),
                    "anchor_id": self.anchor_id_for(fp),
                })
                taken.add(fp)
        if not tasks:
            if self._expand_frontier_with_all_files() > 0:
                return self.next_batch(n)
        return tasks

    def mark_done(self, filepath: str):
        if filepath not in self.covered:
            self.covered.append(filepath)
        self._build_edges_for_anchor(filepath)
        new_imports = self._extract_local_imports(filepath)
        covered_set = set(self.covered)
        frontier_files = {item["filepath"] for item in self.frontier}
        for imp in new_imports:
            if imp not in covered_set and imp not in frontier_files:
                self.frontier.append({"filepath": imp, "from": filepath, "fragments": []})
        self._save()

    def get_progress(self) -> str:
        covered_set = set(self.covered)
        pending = [f for f in self.frontier if f["filepath"] not in covered_set]
        has_frags = sum(1 for f in pending if f.get("fragments"))
        return f"已锚定 {len(self.covered)} | 待组织 {has_frags} | 待探索 {len(pending) - has_frags}"


class CrossModuleExplorer:
    """Phase 2: 确定性跨模块配对分析器。
    
    从 vault 查询共享边的锚点对，按共享边数排序，
    每轮分析一对模块的因果协作关系，记录为 LESSON。
    """

    _state_path = Path("runtime/cross_module_explorer_state.json")

    def __init__(self):
        self._db_path = Path.home() / ".genesis" / "workshop_v4.sqlite"
        self._root = Path(".")
        self.analyzed: list = []  # list of [anchor_a, anchor_b] pairs already done
        self.pair_queue: list = []  # list of {a_id, b_id, a_fp, b_fp, a_title, b_title, shared_nodes, shared}
        self._load()
        if not self.pair_queue:
            self._build_pair_queue()

    def _load(self):
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                self.analyzed = data.get("analyzed", [])
                self.pair_queue = data.get("pair_queue", [])
        except Exception:
            self.analyzed = []
            self.pair_queue = []

    def _save(self):
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps({
                "analyzed": self.analyzed,
                "pair_queue": self.pair_queue,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"CrossModuleExplorer state save failed: {e}")

    def _anchor_to_filepath(self, anchor_id: str) -> str:
        """CTX_MODULE_V4_LOOP → genesis/v4/loop.py (best effort from vault title or heuristic)"""
        if not self._db_path.exists():
            return ""
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            row = conn.execute(
                "SELECT nc.full_content FROM node_contents nc WHERE nc.node_id = ?", (anchor_id,)
            ).fetchone()
            conn.close()
            if row and row[0]:
                for line in row[0].split("\n"):
                    stripped = line.strip().strip("`").strip()
                    if stripped.endswith(".py") and "/" in stripped:
                        return stripped
        except Exception:
            pass
        # Heuristic fallback: CTX_MODULE_V4_LOOP → genesis/v4/loop.py
        parts = anchor_id.replace("CTX_MODULE_", "").lower().split("_")
        candidates = [
            "/".join(parts) + ".py",
            "genesis/" + "/".join(parts) + ".py",
        ]
        for c in candidates:
            if (self._root / c).exists():
                return c
        return ""

    def _build_pair_queue(self):
        """Query vault for anchor pairs sharing edges to common knowledge nodes."""
        if not self._db_path.exists():
            return
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            # Find pairs sharing edges + get titles
            rows = conn.execute("""
                SELECT e1.source_id, e2.source_id, COUNT(*) as shared,
                       GROUP_CONCAT(e1.target_id, '|')
                FROM node_edges e1
                JOIN node_edges e2 ON e1.target_id = e2.target_id
                WHERE e1.source_id LIKE 'CTX_MODULE_%'
                  AND e2.source_id LIKE 'CTX_MODULE_%'
                  AND e1.source_id < e2.source_id
                GROUP BY e1.source_id, e2.source_id
                HAVING shared >= 1
                ORDER BY shared DESC
            """).fetchall()
            # Get anchor titles
            titles = {}
            for r in conn.execute("SELECT node_id, title FROM knowledge_nodes WHERE node_id LIKE 'CTX_MODULE_%'"):
                titles[r[0]] = r[1] or r[0]
            # Get shared node titles for context
            all_node_titles = {}
            for r in conn.execute("SELECT node_id, title FROM knowledge_nodes"):
                all_node_titles[r[0]] = r[1] or r[0]
            conn.close()

            analyzed_set = {tuple(sorted(p)) for p in self.analyzed}
            for a_id, b_id, shared, shared_ids_str in rows:
                pair_key = tuple(sorted([a_id, b_id]))
                if pair_key in analyzed_set:
                    continue
                shared_node_ids = shared_ids_str.split("|") if shared_ids_str else []
                shared_titles = [all_node_titles.get(nid, nid) for nid in shared_node_ids[:5]]
                a_fp = self._anchor_to_filepath(a_id)
                b_fp = self._anchor_to_filepath(b_id)
                if not a_fp or not b_fp:
                    continue
                self.pair_queue.append({
                    "a_id": a_id, "b_id": b_id,
                    "a_fp": a_fp, "b_fp": b_fp,
                    "a_title": titles.get(a_id, a_id),
                    "b_title": titles.get(b_id, b_id),
                    "shared": shared,
                    "shared_titles": shared_titles,
                })
            self._save()
            logger.info(f"CrossModuleExplorer: built queue with {len(self.pair_queue)} pairs")
        except Exception as e:
            logger.warning(f"CrossModuleExplorer: queue build failed: {e}")

    def next_batch(self, n: int) -> list:
        """Get up to n pairs for parallel analysis."""
        analyzed_set = {tuple(sorted(p)) for p in self.analyzed}
        tasks = []
        for pair in self.pair_queue:
            if len(tasks) >= n:
                break
            pair_key = tuple(sorted([pair["a_id"], pair["b_id"]]))
            if pair_key not in analyzed_set:
                tasks.append(pair)
        return tasks

    def mark_done(self, a_id: str, b_id: str):
        self.analyzed.append([a_id, b_id])
        self._save()

    def get_progress(self) -> str:
        analyzed_set = {tuple(sorted(p)) for p in self.analyzed}
        pending = sum(1 for p in self.pair_queue if tuple(sorted([p["a_id"], p["b_id"]])) not in analyzed_set)
        return f"已分析 {len(self.analyzed)} 对 | 待分析 {pending} 对"


# ─── Self-Evolution ──────────────────────────────────────────────

class SelfEvolution:
    """Tracks Doctor sandbox modifications and auto-applies after cooling period.

    File-level cooldown:
    - Each file in sandbox is tracked independently with its own stable_count
    - Tracked files (modified): cooldown = SELF_EVOLUTION_COOLDOWN (default 10)
    - Untracked files (new): cooldown = SELF_EVOLUTION_UNTRACKED_COOLDOWN (default 5)
    - Any single file reaching its cooldown triggers apply of ALL changes
    - This solves the "Yogg never stops" problem: old files cool independently
      even while Yogg keeps adding new ones

    Safety:
    - Git commit before apply (rollback point stored in state)
    - Max 1 apply per session
    - Crash-loop detection in yogg_auto.py triggers rollback on next startup
    """

    _STATE_PATH = Path("runtime/self_evolution_state.json")
    _RESTART_MARKER = Path("runtime/.self_evolution_restart")

    def __init__(self, cooldown: int = SELF_EVOLUTION_COOLDOWN,
                 untracked_cooldown: int = SELF_EVOLUTION_UNTRACKED_COOLDOWN):
        self.cooldown = cooldown
        self.untracked_cooldown = untracked_cooldown
        # File-level cooldown state: {path: {"hash": str, "stable_count": int, "type": "T"|"U"}}
        self.file_cooldowns: dict = {}
        # Session state
        self.applied_this_session: bool = False
        self.apply_history: list = []
        # Diff-status snapshot for outcome detection (ground truth)
        self._pre_round_snapshot: str = ""
        self._load()

    def _load(self):
        try:
            if self._STATE_PATH.exists():
                data = json.loads(self._STATE_PATH.read_text(encoding="utf-8"))
                self.apply_history = data.get("apply_history", [])
                self.file_cooldowns = data.get("file_cooldowns", {})
        except Exception:
            pass

    def _save(self):
        try:
            self._STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._STATE_PATH.write_text(json.dumps({
                "file_cooldowns": self.file_cooldowns,
                "apply_history": self.apply_history[-10:],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"SelfEvolution state save failed: {e}")

    async def snapshot_before_round(self):
        """Take diff-status snapshot BEFORE GP runs. Compared with post-round
        snapshot in outcome_changed_since_snapshot() to detect real changes.
        Uses doctor.sh diff-status (ground truth) instead of indirect signals.
        """
        self._pre_round_snapshot = await self._get_diff_status_hash()

    async def check_round(self, round_num: int, channel) -> dict:
        """Called each round after GP execution. Manages file-level cooling + auto-apply.

        Each file's cooldown is independent: adding new files doesn't reset
        the cooldown of existing files that haven't changed.

        Returns dict: {"apply_attempted": bool, "apply_succeeded": bool, "apply_reason": str}
        """
        result = {"apply_attempted": False, "apply_succeeded": False, "apply_reason": ""}
        if self.applied_this_session:
            return result

        # Get per-file status from sandbox
        current_files = await self._get_file_status()
        if not current_files:
            return result  # no pending changes in sandbox

        # ── Update per-file cooldown state ──
        cooled_files = []
        for path, info in current_files.items():
            ftype = info["type"]  # "T" or "U"
            fhash = info["hash"]
            threshold = self.untracked_cooldown if ftype == "U" else self.cooldown

            if path in self.file_cooldowns:
                old = self.file_cooldowns[path]
                if old["hash"] == fhash:
                    # File unchanged → increment stable count
                    old["stable_count"] = old.get("stable_count", 0) + 1
                    if old["stable_count"] >= threshold:
                        cooled_files.append((path, ftype, old["stable_count"]))
                else:
                    # File changed → reset (GP modified this file this round)
                    old["hash"] = fhash
                    old["stable_count"] = 0
                    old["type"] = ftype
            else:
                # New file in sandbox
                self.file_cooldowns[path] = {
                    "hash": fhash, "stable_count": 0, "type": ftype
                }

        # Remove files that are no longer in sandbox (applied/deleted)
        stale = [p for p in self.file_cooldowns if p not in current_files]
        for p in stale:
            del self.file_cooldowns[p]

        # ── Stable count cap: prevent permanent stall ──
        # If any file's stable_count exceeds 3x its threshold, apply will never
        # succeed (test infrastructure broken). Reset all cooldowns to unblock.
        max_stable = max((v.get("stable_count", 0) for v in self.file_cooldowns.values()), default=0)
        if max_stable >= self.cooldown * 3:
            logger.warning(f"SelfEvolution: stable_count={max_stable} exceeds 3x threshold ({self.cooldown}), resetting cooldowns")
            await channel.send(
                f"🧬 ⚠️ stable_count={max_stable} 超过阈值{self.cooldown}的3倍，重置冷却（沙箱测试基础设施不匹配）"
            )
            self.file_cooldowns.clear()
            cooled_files.clear()  # prevent stale cooled entries from triggering apply

        self._save()

        # ── Status reporting ──
        t_files = {p: v for p, v in self.file_cooldowns.items() if v["type"] == "T"}
        u_files = {p: v for p, v in self.file_cooldowns.items() if v["type"] == "U"}
        parts = []
        if t_files:
            max_t = max(v["stable_count"] for v in t_files.values())
            parts.append(f"T:{len(t_files)}f max{max_t}/{self.cooldown}")
        if u_files:
            max_u = max(v["stable_count"] for v in u_files.values())
            parts.append(f"U:{len(u_files)}f max{max_u}/{self.untracked_cooldown}")
        status_text = " | ".join(parts) if parts else ""

        # Any file cooled → trigger apply
        if cooled_files:
            sample = cooled_files[0]
            await channel.send(
                f"🧬 冷却完成 | {sample[0]} ({sample[1]}) {sample[2]}轮未变 | {status_text} | 开始自进化应用流程..."
            )
            apply_result = await self._try_apply(round_num, channel)
            if apply_result:
                result.update(apply_result)
        elif status_text:
            # Periodic reminder every 3 rounds
            total = sum(v["stable_count"] for v in self.file_cooldowns.values())
            if total % 3 == 0:
                await channel.send(f"🧬 冷却中 | {status_text}")

        return result

    async def _get_diff_status_hash(self) -> str:
        """Get tracked diff hash from sandbox (ground truth for outcome detection).
        Only uses TRACKED_HASH — untracked files are GP's probe/scratch files
        that change every round and would make outcome_detected always True.
        """
        try:
            ok, output = await _run_doctor_sync_command("diff-status", timeout_secs=30)
            if not ok:
                return ""
            for line in output.strip().split("\n"):
                line = line.strip()
                if line.startswith("TRACKED_HASH:"):
                    return line.split(":", 1)[1]
            return ""
        except Exception as e:
            logger.warning(f"SelfEvolution diff-status check failed: {e}")
            return ""

    async def outcome_changed_since_snapshot(self) -> bool:
        """Compare current diff-status with pre-round snapshot.
        Returns True if sandbox state changed since round start (ground truth).
        """
        if self.applied_this_session:
            return False
        current = await self._get_diff_status_hash()
        if not current and not self._pre_round_snapshot:
            return False  # both empty = no sandbox or no changes
        return current != self._pre_round_snapshot

    async def _get_file_status(self) -> dict:
        """Check Doctor sandbox for per-file status.
        Returns dict: {path: {"hash": str, "type": "T"|"U"}}

        NOTE: doctor.sh file-status uses pipefail + while-read pipe, which can
        exit with code=1 even when output is perfectly valid (read returns non-zero
        when input is exhausted). We parse output content regardless of returncode.
        """
        try:
            _, output = await _run_doctor_sync_command("file-status", timeout_secs=30)
            result = {}
            for line in output.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Format: T:path:hash or U:path:hash
                parts = line.split(":", 2)
                if len(parts) == 3 and parts[0] in ("T", "U"):
                    result[parts[1]] = {"hash": parts[2], "type": parts[0]}
            if not result and output.strip():
                logger.warning(f"SelfEvolution file-status: got output but no valid T:/U: lines parsed: {output[:200]}")
            return result
        except Exception as e:
            logger.warning(f"SelfEvolution file-status check failed: {e}")
            return {}

    async def _try_apply(self, round_num: int, channel) -> dict:
        """Test → apply → write restart marker.

        Returns dict: {"apply_attempted": True, "apply_succeeded": bool, "apply_reason": str}
        """
        apply_result = {"apply_attempted": True, "apply_succeeded": False, "apply_reason": ""}
        t_files = {p: v for p, v in self.file_cooldowns.items() if v["type"] == "T"}
        u_files = {p: v for p, v in self.file_cooldowns.items() if v["type"] == "U"}
        max_t = max((v["stable_count"] for v in t_files.values()), default=0)
        max_u = max((v["stable_count"] for v in u_files.values()), default=0)

        # Death loop guard: if recent apply_history shows repeated test_failed with
        # same reason, skip apply for a cooldown period instead of retrying forever.
        recent = self.apply_history[-3:] if len(self.apply_history) >= 3 else []
        if recent and all(e.get("status") == "test_failed" for e in recent):
            # Check if reasons are similar (share a common error substring)
            reasons = [e.get("reason", "")[:60] for e in recent]
            # Simple similarity: if first 30 chars of reason are identical → same root cause
            if len(set(r[:30] for r in reasons)) == 1:
                last_fail_round = recent[-1].get("round", 0)
                skip_remaining = 5 - (round_num - last_fail_round)
                if skip_remaining > 0:
                    await channel.send(
                        f"🧬 ⏭ 跳过自进化（连续测试失败同原因，冷却 {skip_remaining} 轮）| T:{len(t_files)}f max{max_t}/{self.cooldown}"
                    )
                    return apply_result

        await channel.send(
            f"🧬 冷却完成 | T:{len(t_files)}f max{max_t}/{self.cooldown} U:{len(u_files)}f max{max_u}/{self.untracked_cooldown} | 开始自进化应用流程..."
        )

        # 1. Run diff-scoped tests in sandbox (only test files related to current changes)
        await channel.send("🧬 [1/3] 沙箱测试中（差分范围）...")
        test_ok, test_output = await _run_doctor_sync_command("test-diff", timeout_secs=180)
        if not test_ok:
            await channel.send(
                f"🧬 ❌ 沙箱测试失败，放弃本次应用\n```\n{test_output[-500:]}\n```"
            )
            apply_result["apply_reason"] = test_output[-200:].replace("\n", " ").strip()
            self.apply_history.append({
                "round": round_num,
                "status": "test_failed",
                "reason": apply_result["apply_reason"],
            })
            # Selective reset: only reset files whose hash changed (they may be the cause),
            # preserve stable files that weren't involved in the failure.
            current_files = await self._get_file_status()
            if current_files:
                changed = [p for p, v in self.file_cooldowns.items()
                           if p in current_files and v["hash"] != current_files[p]["hash"]]
                for p in changed:
                    self.file_cooldowns[p]["hash"] = current_files[p]["hash"]
                    self.file_cooldowns[p]["stable_count"] = 0
                # Remove files no longer in sandbox
                stale = [p for p in self.file_cooldowns if p not in current_files]
                for p in stale:
                    del self.file_cooldowns[p]
            else:
                # Fallback: can't determine which files changed, reset all
                self.file_cooldowns.clear()
            self._save()
            return apply_result

        await channel.send("🧬 ✅ 测试通过")

        # 2. Auto-apply with git safety net
        await channel.send("🧬 [2/3] 应用沙箱修改到本体...")
        apply_ok, apply_output = await _run_doctor_sync_command("auto-apply", timeout_secs=60)

        # Parse output for rollback point
        rollback_commit = ""
        applied_commit = ""
        for line in apply_output.split("\n"):
            if line.startswith("ROLLBACK_POINT:"):
                rollback_commit = line.split(":", 1)[1].strip()
            elif line.startswith("APPLIED_COMMIT:"):
                applied_commit = line.split(":", 1)[1].strip()

        if not apply_ok or "APPLY_SUCCESS" not in apply_output:
            await channel.send(
                f"🧬 ❌ 应用失败\n```\n{apply_output[-500:]}\n```"
            )
            apply_result["apply_reason"] = apply_output[-200:].replace("\n", " ").strip()
            self.apply_history.append({
                "round": round_num,
                "status": "apply_failed",
                "reason": apply_result["apply_reason"],
            })
            # Selective reset on apply failure too
            current_files = await self._get_file_status()
            if current_files:
                changed = [p for p, v in self.file_cooldowns.items()
                           if p in current_files and v["hash"] != current_files[p]["hash"]]
                for p in changed:
                    self.file_cooldowns[p]["hash"] = current_files[p]["hash"]
                    self.file_cooldowns[p]["stable_count"] = 0
                stale = [p for p in self.file_cooldowns if p not in current_files]
                for p in stale:
                    del self.file_cooldowns[p]
            else:
                self.file_cooldowns.clear()
            self._save()
            return apply_result

        await channel.send(f"🧬 ✅ 代码已应用 | commit={applied_commit[:8]}")

        # 3. Reset sandbox to new production baseline (production now has the changes)
        await channel.send("🧬 [3/4] 重置沙箱到新基线...")
        reset_ok, reset_output = await _run_doctor_sync_command("reset", timeout_secs=60)
        if reset_ok:
            await channel.send("🧬 ✅ 沙箱已同步到新基线")
        else:
            await channel.send(f"🧬 ⚠️ 沙箱重置失败（不影响本体）: {reset_output[-200:]}")

        # 4. Write restart marker + record history + clear cooling state
        apply_result["apply_succeeded"] = True
        self.applied_this_session = True
        self.apply_history.append({
            "round": round_num,
            "status": "success",
            "timestamp": _time_module.strftime("%Y-%m-%d %H:%M:%S"),
            "rollback_commit": rollback_commit,
            "applied_commit": applied_commit,
        })
        self.file_cooldowns.clear()  # 沙箱已 reset，diff 应为空
        self._save()

        # Write restart marker for yogg_auto.py crash-loop detection
        try:
            self._RESTART_MARKER.parent.mkdir(parents=True, exist_ok=True)
            self._RESTART_MARKER.write_text(json.dumps({
                "rollback_commit": rollback_commit,
                "applied_commit": applied_commit,
                "timestamp": _time_module.strftime("%Y-%m-%d %H:%M:%S"),
            }), encoding="utf-8")
        except Exception as e:
            logger.error(f"SelfEvolution: restart marker write failed: {e}")

        await channel.send(
            f"🧬 [4/4] 自进化完成 | rollback={rollback_commit[:8]} → applied={applied_commit[:8]}\n"
            f"🔄 正在重启服务以加载新代码..."
        )

        # 5. Restart — this kills the current process, systemd restarts it
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "systemctl", "restart", "yogg-auto.service",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
        except Exception as e:
            logger.error(f"SelfEvolution: restart failed: {e}")
            # Not fatal — user/systemd can restart manually

    @staticmethod
    def check_and_rollback_if_needed():
        """Called at startup. Logs marker info but does NOT clear it.
        Marker is cleared only after first successful round (see clear_restart_marker).
        This ensures yogg_auto.py crash-loop detector can still see the marker."""
        marker = SelfEvolution._RESTART_MARKER
        if not marker.exists():
            return False
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            rollback_commit = data.get("rollback_commit", "")
            applied_commit = data.get("applied_commit", "")
            ts = data.get("timestamp", "?")
            logger.info(
                f"SelfEvolution: post-apply startup | "
                f"applied={applied_commit[:8]} rollback={rollback_commit[:8]} ts={ts} | "
                f"marker preserved for crash-loop detection"
            )
            return False
        except Exception as e:
            logger.error(f"SelfEvolution: marker check failed: {e}")
            return False

    @staticmethod
    def clear_restart_marker():
        """Clear marker after first successful round — confirms apply didn't break anything."""
        try:
            SelfEvolution._RESTART_MARKER.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def force_rollback(rollback_commit: str) -> bool:
        """Emergency rollback to a known-good commit."""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "reset", "--hard", rollback_commit],
                capture_output=True, text=True, timeout=30,
            )
            logger.warning(f"SelfEvolution: ROLLBACK to {rollback_commit[:8]} | {result.stdout.strip()}")
            try:
                SelfEvolution._RESTART_MARKER.unlink(missing_ok=True)
            except Exception:
                pass
            return result.returncode == 0
        except Exception as e:
            logger.error(f"SelfEvolution: rollback failed: {e}")
            return False


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
    _pending_apply_feedback = None  # carry apply-failure reason to next round signals
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
    topic_tracker = TopicTracker()
    action_history = ActionHistory()
    spiral_mode = (directive == AUTO_DEFAULT_DIRECTIVE)
    pioneer = SpiralPioneer() if spiral_mode else None
    cross_module_mode = False
    explorer = None
    _current_pioneer_file = None
    self_evolution = SelfEvolution() if SELF_EVOLUTION_ENABLED else None

    _report_dir = Path("runtime/auto_reports")
    _report_dir.mkdir(parents=True, exist_ok=True)
    _session_ts = _time_module.strftime("%Y%m%d_%H%M%S")
    _session_id = f"{channel.id}_{_session_ts}"
    _rounds_dir = _report_dir / _session_id
    _rounds_dir.mkdir(parents=True, exist_ok=True)
    _md_path = _report_dir / f"auto_{_session_id}.md"
    _md_path.write_text(f"# /auto Report — session={_session_id}\n\n", encoding="utf-8")
    _session_json_path = _report_dir / f"auto_{_session_id}.json"

    # ── Session working memory persistence (crash recovery) ──
    _memory_path = Path("runtime/.auto_session_memory.json")

    def _save_session_memory():
        """每轮结束后持久化关键工作记忆，crash 后新 session 可恢复。"""
        try:
            data = {
                "round_num": round_num,
                "consecutive_dry": consecutive_dry,
                "last_frontier": last_frontier,
                "last_knowledge_state": last_knowledge_state,
                "last_good_knowledge_state": last_good_knowledge_state,
                "last_reanchor_streak": last_reanchor_streak,
                "session_shown_voids": list(session_shown_voids),
                "session_shown_nodes": list(session_shown_nodes),
                "planner_agenda": planner_agenda,
                "planner_result": planner_result,
                "last_planner_round": last_planner_round,
                "planner_call_count": planner_call_count,
                "saved_at": _time_module.strftime("%Y-%m-%d %H:%M:%S"),
            }
            _memory_path.parent.mkdir(parents=True, exist_ok=True)
            _memory_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as _e:
            logger.debug(f"session memory save failed: {_e}")

    def _load_session_memory():
        """加载上轮持久化的工作记忆。超过 2 小时的记忆视为过期。"""
        try:
            if not _memory_path.exists():
                return None
            data = json.loads(_memory_path.read_text(encoding="utf-8"))
            # 过期检查：超过 2 小时的记忆不恢复
            saved_at = data.get("saved_at", "")
            if saved_at:
                from datetime import datetime, timedelta
                saved_dt = datetime.strptime(saved_at, "%Y-%m-%d %H:%M:%S")
                if datetime.now() - saved_dt > timedelta(hours=2):
                    logger.info("session memory expired (>2h), starting fresh")
                    return None
            logger.info(f"session memory recovered from round {data.get('round_num', 0)}")
            return data
        except Exception as _e:
            logger.debug(f"session memory load failed: {_e}")
            return None

    _recovered = _load_session_memory()
    if _recovered:
        # round_num 不恢复——它是 session 内计数器，新 session 必须从 0 开始
        # 否则恢复后 round_num >= AUTO_MAX_ROUNDS 会立即退出
        consecutive_dry = _recovered.get("consecutive_dry", 0)
        last_frontier = _recovered.get("last_frontier", "")
        last_knowledge_state = _recovered.get("last_knowledge_state", {})
        last_good_knowledge_state = _recovered.get("last_good_knowledge_state", {})
        last_reanchor_streak = _recovered.get("last_reanchor_streak", 0)
        session_shown_voids = set(_recovered.get("session_shown_voids", []))
        session_shown_nodes = set(_recovered.get("session_shown_nodes", []))
        planner_agenda = _recovered.get("planner_agenda", [])
        planner_result = _recovered.get("planner_result", {})
        last_planner_round = _recovered.get("last_planner_round", 0)
        planner_call_count = _recovered.get("planner_call_count", 0)
        await channel.send(f"♻️ 恢复上轮工作记忆 (R{round_num}, dry={consecutive_dry})")

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

    if spiral_mode:
        await channel.send(
            f"🌿 **螺旋拓荒模式启动** ({'无上限' if AUTO_MAX_ROUNDS == 0 else f'上限 {AUTO_MAX_ROUNDS} 轮'})\n"
            f"以 vault 已有碎片为底座，为每个文件创建结构性锚点 (CTX_MODULE_) 并连边。\n"
            f"{pioneer.get_progress()} | 发送 `/auto stop` 停止。"
        )
    else:
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

        # Take diff-status snapshot BEFORE GP runs (ground truth for outcome detection)
        if self_evolution:
            try:
                logger.debug(f"auto R{round_num} snapshot_before_round start")
                await self_evolution.snapshot_before_round()
                logger.debug(f"auto R{round_num} snapshot_before_round done")
            except Exception as _snap_e:
                logger.warning(f"auto R{round_num} snapshot_before_round error: {_snap_e}")

        _reset_provider(agent)
        node_status_before = _get_node_count_status()
        round_start_ts = _time_module.time()
        round_start_iso = _time_module.strftime("%Y-%m-%d %H:%M:%S", _time_module.localtime(round_start_ts))
        round_start_utc_iso = _time_module.strftime("%Y-%m-%d %H:%M:%S", _time_module.gmtime(round_start_ts))

        signals = _get_auto_signals(round_num=round_num, session_shown_voids=session_shown_voids, session_shown_nodes=session_shown_nodes)
        # Inject apply-failure feedback from previous round into signals
        if _pending_apply_feedback:
            _aw = "\n\n[⚠️ 上一轮自进化apply被拒(沙箱测试失败)] " + _pending_apply_feedback[:200] + " 不要继续写同类型探针,转向修复测试或换方向"
            signals += _aw
            _pending_apply_feedback = None
        _struct = [topic_tracker.format_for_prompt(), action_history.format_for_prompt()]
        _struct_text = "\n\n".join(p for p in _struct if p)
        if _struct_text:
            signals = signals + "\n\n" + _struct_text

        # ── 任务选择：螺旋拓荒模式 vs 经典 planner 模式 ──
        _current_pioneer_file = None
        if spiral_mode and pioneer:
            # ── Parallel batch processing ──
            _batch = pioneer.next_batch(SPIRAL_CONCURRENCY)
            if not _batch:
                await channel.send(
                    "🌿 **拓荒阶段完成！** 所有文件已锚定。\n"
                    "🔗 **升级到第二阶段：自然连接** — 分析跨模块因果关系。"
                )
                _append_md("\n---\n## 🔗 金字塔升级：拓荒 → 自然连接\n\n")
                spiral_mode = False
                cross_module_mode = True
                explorer = CrossModuleExplorer()
                await channel.send(f"🔗 {explorer.get_progress()}")
                continue

            _batch_t0 = _time_module.time()
            _file_list = " / ".join(f"`{t['filepath']}`" for t in _batch)
            await channel.send(
                f"{'─'*40}\n🌿 **第 {round_num} 批** ({len(_batch)} 并行) | {pioneer.get_progress()}\n{_file_list}"
            )

            async def _spiral_one(_task_item):
                _p = SPIRAL_PROMPT.format(
                    filepath=_task_item["filepath"],
                    discovered_from=_task_item["discovered_from"],
                    anchor_id=_task_item["anchor_id"],
                    progress=pioneer.get_progress(),
                )
                try:
                    _r = await agent.process(
                        f"[GENESIS_USER_REQUEST_START]\n{_p}",
                        c_phase_blocking=True,
                        loop_config={"disable_multi_g": True, "gp_unblock_tools": ["record_lesson_node", "record_context_node"]},
                    )
                    _resp = _r.response if hasattr(_r, 'response') else ""
                    _tok = _r.total_tokens if hasattr(_r, 'total_tokens') else 0
                    return {"task": _task_item, "ok": not _is_error_response(_resp, _tok), "tokens": _tok, "response": _resp}
                except Exception as _e:
                    return {"task": _task_item, "ok": False, "tokens": 0, "response": str(_e)}

            _results = await asyncio.gather(*[_spiral_one(t) for t in _batch], return_exceptions=True)

            _ok_files, _fail_files, _batch_tokens = [], [], 0
            for _br in _results:
                if isinstance(_br, Exception):
                    _fail_files.append("exception")
                    continue
                _batch_tokens += _br.get("tokens", 0)
                if _br["ok"]:
                    pioneer.mark_done(_br["task"]["filepath"])
                    _ok_files.append(_br["task"]["filepath"])
                else:
                    _fail_files.append(_br["task"]["filepath"])

            _batch_dur = _time_module.time() - _batch_t0
            _append_md(
                f"\n---\n## 第 {round_num} 批 ({len(_batch)} 并行)\n\n"
                f"✅ {len(_ok_files)}/{len(_batch)} | {_batch_dur:.0f}s | {_batch_tokens}t\n\n"
            )
            for _br in _results:
                if not isinstance(_br, Exception):
                    _st = "✅" if _br["ok"] else "❌"
                    _append_md(f"- {_st} `{_br['task']['filepath']}` → `{_br['task']['anchor_id']}` ({_br.get('tokens', 0)}t)\n")

            await channel.send(f"✅ {len(_ok_files)}/{len(_batch)} 成功 | {_batch_dur:.0f}s | {_batch_tokens}t | {pioneer.get_progress()}")
            if _ok_files:
                await channel.send("锚定: " + ", ".join(f"`{f}`" for f in _ok_files))
            if _fail_files:
                await channel.send("失败: " + ", ".join(f"`{f}`" for f in _fail_files))

            consecutive_error = consecutive_error + len(_batch) if not _ok_files else 0
            round_num += len(_batch) - 1

            if AUTO_SLEEP_BASE > 0 and state.get("active", False):
                await asyncio.sleep(AUTO_SLEEP_BASE)
            continue

        elif cross_module_mode and explorer:
            # ── Phase 2: Cross-module parallel batch ──
            _cm_batch = explorer.next_batch(SPIRAL_CONCURRENCY)
            if not _cm_batch:
                await channel.send("🔗 **自然连接阶段完成！** 所有配对已分析。")
                _append_md("\n---\n## ✅ 自然连接阶段完成\n\n")
                cross_module_mode = False
                continue

            _cm_t0 = _time_module.time()
            _pair_list = " / ".join(f"`{p['a_fp']}` ↔ `{p['b_fp']}`" for p in _cm_batch)
            await channel.send(
                f"{'─'*40}\n🔗 **第 {round_num} 批** ({len(_cm_batch)} 配对并行) | {explorer.get_progress()}\n{_pair_list}"
            )

            async def _cross_one(_pair):
                _shared_ctx = "\n".join(f"- {t}" for t in _pair.get("shared_titles", [])[:5]) or "(无共享线索)"
                _p = CROSS_MODULE_PROMPT.format(
                    filepath_a=_pair["a_fp"], anchor_title_a=_pair["a_title"],
                    filepath_b=_pair["b_fp"], anchor_title_b=_pair["b_title"],
                    shared_context=_shared_ctx,
                    progress=explorer.get_progress(),
                )
                try:
                    _r = await agent.process(
                        f"[GENESIS_USER_REQUEST_START]\n{_p}",
                        c_phase_blocking=True,
                        loop_config={"disable_multi_g": True, "gp_unblock_tools": ["record_lesson_node", "record_context_node"]},
                    )
                    _resp = _r.response if hasattr(_r, 'response') else ""
                    _tok = _r.total_tokens if hasattr(_r, 'total_tokens') else 0
                    return {"pair": _pair, "ok": not _is_error_response(_resp, _tok), "tokens": _tok, "response": _resp}
                except Exception as _e:
                    return {"pair": _pair, "ok": False, "tokens": 0, "response": str(_e)}

            _cm_results = await asyncio.gather(*[_cross_one(p) for p in _cm_batch], return_exceptions=True)

            _cm_ok, _cm_fail, _cm_tokens = [], [], 0
            for _cr in _cm_results:
                if isinstance(_cr, Exception):
                    _cm_fail.append("exception")
                    continue
                _cm_tokens += _cr.get("tokens", 0)
                if _cr["ok"]:
                    explorer.mark_done(_cr["pair"]["a_id"], _cr["pair"]["b_id"])
                    _cm_ok.append(f"{_cr['pair']['a_fp']} ↔ {_cr['pair']['b_fp']}")
                else:
                    _cm_fail.append(f"{_cr['pair']['a_fp']} ↔ {_cr['pair']['b_fp']}")

            _cm_dur = _time_module.time() - _cm_t0
            _append_md(
                f"\n---\n## 第 {round_num} 批 跨模块 ({len(_cm_batch)} 配对)\n\n"
                f"✅ {len(_cm_ok)}/{len(_cm_batch)} | {_cm_dur:.0f}s | {_cm_tokens}t\n\n"
            )
            for _cr in _cm_results:
                if not isinstance(_cr, Exception):
                    _st = "✅" if _cr["ok"] else "❌"
                    _append_md(f"- {_st} `{_cr['pair']['a_fp']}` ↔ `{_cr['pair']['b_fp']}` ({_cr.get('tokens', 0)}t)\n")

            await channel.send(f"✅ {len(_cm_ok)}/{len(_cm_batch)} 成功 | {_cm_dur:.0f}s | {_cm_tokens}t | {explorer.get_progress()}")
            if _cm_ok:
                await channel.send("连接: " + ", ".join(_cm_ok[:5]))

            consecutive_error = consecutive_error + len(_cm_batch) if not _cm_ok else 0
            round_num += len(_cm_batch) - 1

            if AUTO_SLEEP_BASE > 0 and state.get("active", False):
                await asyncio.sleep(AUTO_SLEEP_BASE)
            continue

        else:
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

            if need_planner and last_planner_round == round_num:
                round_focus = planner_result.get("next_focus", "").strip()
            else:
                round_focus = ""
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
                    if evt.args:
                        summarized_args = _summarize_event_args(evt.args)
                        if summarized_args:
                            entry["args"] = summarized_args
                    if isinstance(data, dict):
                        if data.get("llm_call_id"):
                            entry["llm_call_id"] = data.get("llm_call_id")
                        if "iteration" in data:
                            entry["iteration"] = data.get("iteration")
                        if data.get("label"):
                            entry["label"] = data.get("label")
                        if "duration_ms" in data:
                            entry["duration_ms"] = data.get("duration_ms")
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
                            refl = data.get("reflection") or {}
                            round_record["c_phase_summary"] = {
                                "mode": data.get("mode", "?"),
                                "c_tokens": data.get("c_tokens", 0),
                                "lessons_recorded": refl.get("lessons_recorded", 0),
                                "lesson_titles": [l.get("title", "?") for l in refl.get("lessons", [])][:3],
                                "reflection_reason": refl.get("reason", ""),
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
                        chunk_chars = (data.get("chunk_chars") if isinstance(data, dict) else None) or len(chunk_text)
                        stream_key = f"{evt.event_type}_chars"
                        chunk_key = f"{evt.event_type}_chunks"
                        round_record["stream_stats"][stream_key] += chunk_chars
                        round_record["stream_stats"][chunk_key] += 1
                        return  # skip storing streaming chunks in events list (OOM prevention)
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
            # Classify first (interrupted = no outcome)
            progress_profile = _classify_auto_round_progress(
                response=round_record.get("response_full") or round_record.get("response_preview") or "",
                round_events=round_events, kb_changed=kb_changed, frontier_state=None,
                outcome_detected=False,  # interrupted round — GP didn't complete
            )
            consecutive_dry = 0 if progress_profile.get("outcome_detected") else consecutive_dry + 1
            frontier_state = _build_frontier_state(
                round_index=round_num, response=round_record.get("response_full") or round_record.get("response_preview") or "",
                kb_delta_summary=kb_delta_summary, kb_changed=kb_changed, node_telemetry=node_telemetry,
                round_events=round_events, prior_reanchor_streak=last_reanchor_streak,
                consecutive_dry=consecutive_dry, progress_class=progress_profile.get("progress_class", ""),
                kb_delta=kb_delta,
            )
            frontier_text = _format_frontier_state(frontier_state)
            frontier_preview = f"goal={frontier_state['local_goal']} | issue={frontier_state['candidate_issue']}" + (f" | reanchor#{frontier_state.get('reanchor_streak', 0)}" if frontier_state.get("reanchor_required") else "")
            knowledge_state = _build_auto_knowledge_state(
                frontier_state=frontier_state, round_events=round_events,
                raw_state=round_record.get("knowledge_state") or last_knowledge_state or None,
            )
            knowledge_state_text = _format_knowledge_state(knowledge_state)
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
                    "gp_unblock_tools": ["record_lesson_node", "record_context_node"],
                    "cross_round_observations": _compute_cross_round_observations(round_log, self_evolution),
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

            # Ground truth: did sandbox diff change since round start?
            _outcome = False
            if self_evolution and not round_is_error:
                try:
                    logger.debug(f"auto R{round_num} outcome_changed_since_snapshot start")
                    _outcome = await self_evolution.outcome_changed_since_snapshot()
                    logger.debug(f"auto R{round_num} outcome_changed_since_snapshot done: {_outcome}")
                except Exception as _oc_e:
                    logger.warning(f"auto R{round_num} outcome_changed_since_snapshot error: {_oc_e}")
            # Classify FIRST — needs only candidate_issue + reanchor_required from frontier
            _partial_frontier = {
                "candidate_issue": _extract_candidate_issue("" if round_is_error else response),
                "reanchor_required": _detect_reanchor_signal("" if round_is_error else response, round_events)[0],
            }
            progress_profile = _classify_auto_round_progress(
                response=response, round_events=round_events,
                kb_changed=kb_changed if not round_is_error else False,
                frontier_state=_partial_frontier, is_error=round_is_error,
                outcome_detected=_outcome,
            )
            consecutive_dry = 0 if progress_profile.get("outcome_detected") else consecutive_dry + 1

            # Build full frontier_state NOW with progress_class available
            frontier_state = _build_frontier_state(
                round_index=round_num, response="" if round_is_error else response,
                kb_delta_summary=kb_delta_summary, kb_changed=kb_changed if not round_is_error else False,
                node_telemetry=node_telemetry, round_events=round_events,
                prior_reanchor_streak=last_reanchor_streak,
                consecutive_dry=consecutive_dry, progress_class=progress_profile.get("progress_class", ""),
                kb_delta=kb_delta,
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
                # 首轮成功完成后清除自进化重启标记（证明 apply 的新代码能正常工作）
                if round_num == 1 and SELF_EVOLUTION_ENABLED:
                    SelfEvolution.clear_restart_marker()
            knowledge_state_text = _format_knowledge_state(knowledge_state)
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
            c_diag = f"C[lessons={c_sum.get('lessons_recorded', 0)}]" if c_sum else "C[skip]"
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

            # Spiral Pioneer mark_done is handled in batch handler above (parallel mode)

        except asyncio.TimeoutError:
            duration = _time_module.time() - t0
            err_str = f"round_timeout>{AUTO_ROUND_TIMEOUT_SECS}s" if AUTO_ROUND_TIMEOUT_SECS > 0 else "round_timeout"
            logger.error(f"Auto round {round_num} timeout: {err_str}", exc_info=True)
            await channel.send(f"⚠️ 第{round_num}轮超时: {err_str}")
            _append_md(f"### Response (timeout)\n\n{err_str}\n\n")
            kb_delta, kb_changed, kb_delta_summary, node_telemetry = _observe_round_state()
            final_node_telemetry = node_telemetry
            # Classify first (timeout = no outcome)
            progress_profile = _classify_auto_round_progress(
                response="", round_events=round_events,
                kb_changed=kb_changed, frontier_state=None,
                outcome_detected=False,  # timeout — GP didn't complete
            )
            consecutive_dry = 0 if progress_profile.get("outcome_detected") else consecutive_dry + 1
            frontier_state = _build_frontier_state(
                round_index=round_num, response="",
                kb_delta_summary=kb_delta_summary, kb_changed=kb_changed,
                node_telemetry=node_telemetry, round_events=round_events,
                prior_reanchor_streak=last_reanchor_streak,
                consecutive_dry=consecutive_dry, progress_class=progress_profile.get("progress_class", ""),
                kb_delta=kb_delta,
            )
            frontier_text = _format_frontier_state(frontier_state)
            frontier_preview = "timeout" + (f" | reanchor#{frontier_state.get('reanchor_streak', 0)}" if frontier_state.get("reanchor_required") else "")
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
            # 与 error 路径一致：不污染 knowledge_state，回退到上次成功值
            last_knowledge_state = last_good_knowledge_state.copy() if last_good_knowledge_state else last_knowledge_state

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
            # Classify first (exception = no outcome)
            progress_profile = _classify_auto_round_progress(
                response="", round_events=round_events,
                kb_changed=kb_changed, frontier_state=None,
                outcome_detected=False,  # exception — GP didn't complete
            )
            consecutive_dry = 0 if progress_profile.get("outcome_detected") else consecutive_dry + 1
            frontier_state = _build_frontier_state(
                round_index=round_num, response="",
                kb_delta_summary=kb_delta_summary, kb_changed=kb_changed,
                node_telemetry=node_telemetry, round_events=round_events,
                prior_reanchor_streak=last_reanchor_streak,
                consecutive_dry=consecutive_dry, progress_class=progress_profile.get("progress_class", ""),
                kb_delta=kb_delta,
            )
            frontier_text = _format_frontier_state(frontier_state)
            frontier_preview = "exception" + (f" | reanchor#{frontier_state.get('reanchor_streak', 0)}" if frontier_state.get("reanchor_required") else "")
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
            # 与 error 路径一致：不污染 knowledge_state，回退到上次成功值
            last_knowledge_state = last_good_knowledge_state.copy() if last_good_knowledge_state else last_knowledge_state

        finally:
            _finalize_incomplete_round("interrupted_before_round_finalize")

        # ─── Structural Controls Update ───
        action_history.record_round(round_num, round_events)
        _latest_fs = round_record.get("frontier_state") or {}
        _topic_result = topic_tracker.update(
            round_num, _latest_fs.get("candidate_issue", ""),
            round_record.get("activity_detected", False),
        )
        if _topic_result["action"] == "force_switch":
            last_frontier = ""
            last_knowledge_state = {
                "issue": "上一话题已用尽轮次预算——必须切换到完全不同的新方向",
                "verified_facts": [],
                "failed_attempts": [_topic_result["message"]],
                "next_checks": ["选择一个与已探索话题完全不同的新方向"],
            }
            await channel.send(f"🔀 {_topic_result['message']}")
        elif _topic_result["action"] == "suggest_switch" and isinstance(last_knowledge_state, dict):
            _fa = last_knowledge_state.get("failed_attempts") or []
            _fa.insert(0, _topic_result["message"])
            last_knowledge_state["failed_attempts"] = _fa[:5]

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

        # ── Memory hygiene: compact old round records + release pages ──
        if len(round_log) > _ROUND_LOG_KEEP:
            for _old_rec in round_log[:-_ROUND_LOG_KEEP]:
                for _heavy_key in ("events", "response_full", "signals", "prompt_preview",
                                   "frontier_text", "knowledge_state_text", "phase_trace"):
                    _old_rec.pop(_heavy_key, None)
        _save_session_memory()
        _release_memory()

        # TOOL 节点热加载：C 后台写的 TOOL 节点在此激活，下一轮 GP 可用
        try:
            from factory import activate_vault_tools
            _new_tools = activate_vault_tools(agent.tools)
            if _new_tools:
                logger.info(f"/auto tool_hotload | {_new_tools} new vault tools activated")
        except Exception as _e:
            logger.debug(f"/auto tool_hotload skip: {_e}")

        # ── Self-Evolution: 沙箱冷却追踪 + 自动应用 ──
        _apply_feedback = None
        if self_evolution and consecutive_error == 0:
            try:
                logger.debug(f"auto R{round_num} self_evolution.check_round start")
                _se_result = await self_evolution.check_round(round_num, channel)
                logger.debug(f"auto R{round_num} self_evolution.check_round done")
                if _se_result and _se_result.get("apply_attempted") and not _se_result.get("apply_succeeded"):
                    _apply_feedback = _se_result.get("apply_reason", "unknown")
            except Exception as _se_e:
                logger.warning(f"SelfEvolution check_round failed: {_se_e}")

        # Apply-failure feedback -> next round signals
        if _apply_feedback:
            _pending_apply_feedback = _apply_feedback

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
