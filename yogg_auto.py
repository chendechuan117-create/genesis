#!/usr/bin/env python3
"""
Yogg — Genesis 放生模式
无 Discord 依赖的独立 auto runner。直接循环跑 auto mode，崩溃自动重启。
支持自进化：在 Doctor 沙箱中修改代码 → 冷却期 → 自动应用到本体 → 重启。

用法:
    python -u yogg_auto.py                       # 默认 directive
    python -u yogg_auto.py "自定义探索方向"      # 自定义 directive

环境变量 (继承 auto_mode 全部配置):
    GENESIS_AUTO_SYNC_DOCTOR_SANDBOX=0   # 沙箱生命周期由 SelfEvolution 管理
    GENESIS_SELF_EVOLUTION=1             # 启用自进化（沙箱修改冷却后自动应用）
    GENESIS_SELF_EVOLUTION_COOLDOWN=10   # 冷却轮数（持久化，跨 session 累计）
    GENESIS_AUTO_MAX_ROUNDS=10           # 每 session 10 轮（防 OOM）
    GENESIS_AUTO_DRY_LIMIT=0             # 不因空转停止
"""

import asyncio
import contextlib
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

# ── 自进化模式：沙箱生命周期由 SelfEvolution 管理，不自动 reset ──
os.environ.setdefault("GENESIS_AUTO_SYNC_DOCTOR_SANDBOX", "0")  # 不在 session 开头 reset 沙箱
os.environ.setdefault("GENESIS_SELF_EVOLUTION", "1")             # SelfEvolution 接管沙箱
os.environ.setdefault("GENESIS_SELF_EVOLUTION_COOLDOWN", "10")
# 不因空转停止 — Yogg 是放生的，永远跑
os.environ.setdefault("GENESIS_AUTO_DRY_LIMIT", "0")
# 每 session 最多跑 10 轮，然后外循环重启新 session 释放内存（Yoga 只有 8G RAM）
os.environ.setdefault("GENESIS_AUTO_MAX_ROUNDS", "10")

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Yogg")


# ── 自进化安全网：在 import genesis 之前检查崩溃循环 ──
# 如果 apply 的代码有语法错误，genesis.auto_mode import 会直接失败
# 所以必须在 import 之前用纯标准库做崩溃检测和回滚

_CRASH_COUNTER_PATH = Path("runtime/.yogg_crash_counter")
_RESTART_MARKER_PATH = Path("runtime/.self_evolution_restart")
_ROLLBACK_CRASH_THRESHOLD = 3


def _pre_import_crash_guard():
    """在 import genesis 之前运行。持久化崩溃计数 + 回滚。"""
    # 递增持久化崩溃计数器
    crash_count = 0
    try:
        if _CRASH_COUNTER_PATH.exists():
            crash_count = int(_CRASH_COUNTER_PATH.read_text().strip())
    except Exception:
        pass
    crash_count += 1
    try:
        _CRASH_COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CRASH_COUNTER_PATH.write_text(str(crash_count))
    except Exception:
        pass

    logger.info(f"Yogg: startup crash_count={crash_count}")

    # 检查是否需要回滚
    if crash_count >= _ROLLBACK_CRASH_THRESHOLD and _RESTART_MARKER_PATH.exists():
        try:
            import subprocess
            data = json.loads(_RESTART_MARKER_PATH.read_text(encoding="utf-8"))
            rollback_commit = data.get("rollback_commit", "")
            if rollback_commit:
                logger.warning(
                    f"Yogg: {crash_count} consecutive crashes after self-evolution. "
                    f"Rolling back to {rollback_commit[:8]}..."
                )
                result = subprocess.run(
                    ["git", "reset", "--hard", rollback_commit],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    logger.warning(f"Yogg: ROLLBACK SUCCESS to {rollback_commit[:8]}")
                    _RESTART_MARKER_PATH.unlink(missing_ok=True)
                    _CRASH_COUNTER_PATH.unlink(missing_ok=True)
                    # 退出让 systemd 用回滚后的代码重启
                    sys.exit(42)
                else:
                    logger.error(f"Yogg: git reset failed: {result.stderr}")
        except Exception as e:
            logger.error(f"Yogg: rollback attempt failed: {e}")


_pre_import_crash_guard()

# ── 现在安全 import genesis（如果上面没有回滚退出的话） ──
from factory import create_agent
from genesis.auto_mode import run_auto, SelfEvolution

# ── 日志频道：替代 Discord channel ──

_LOG_DIR = Path("runtime/yogg_logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)


class LogChannel:
    """模拟 discord.TextChannel，将 send() 输出到日志文件 + stdout。"""

    def __init__(self, session_id: str):
        self.id = 90660  # 固定 channel id for Yogg
        self._log_path = _LOG_DIR / f"yogg_{session_id}.log"
        self._fh = open(self._log_path, "a", encoding="utf-8")
        logger.info(f"Yogg log: {self._log_path}")

    async def send(self, content: str, **kwargs):
        """写到日志文件 + stdout，模拟 channel.send()。"""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {content}"
        # stdout (简短版)
        preview = content[:200]
        if len(content) > 200:
            preview += "..."
        print(f"[Yogg {ts}] {preview}", flush=True)
        # 文件 (完整版)
        try:
            self._fh.write(line + "\n")
            self._fh.flush()
        except Exception:
            pass

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass


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


def _resolve_cgroup_file(name: str):
    try:
        lines = Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for line in lines:
        parts = line.strip().split(":", 2)
        if len(parts) != 3:
            continue
        hierarchy, controllers, rel_path = parts
        if hierarchy == "0" or controllers == "memory" or "memory" in controllers.split(","):
            rel_path = rel_path.lstrip("/")
            base = Path("/sys/fs/cgroup")
            return (base / rel_path / name) if rel_path else (base / name)
    return None


def _read_cgroup_int(name: str):
    path = _resolve_cgroup_file(name)
    if not path or not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not raw or raw == "max":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _format_bytes(value):
    if value is None:
        return "unknown"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{int(value)}B"


YOGG_EXIT_ON_SESSION_END = _env_bool("YOGG_EXIT_ON_SESSION_END", True)
YOGG_MEMORY_EXIT_THRESHOLD_MB = _env_int("YOGG_MEMORY_EXIT_THRESHOLD_MB", 0, minimum=0)
YOGG_MEMORY_HIGH_HEADROOM_MB = _env_int("YOGG_MEMORY_HIGH_HEADROOM_MB", 256, minimum=0)
YOGG_MEMORY_POLL_SECS = _env_int("YOGG_MEMORY_POLL_SECS", 15, minimum=5)


# ── 线程级看门狗：cgroup 节流冻结 asyncio 后的唯一逃生通道 ──
# 根因：cgroup memory.high 节流让进程进入 D 状态，asyncio 事件循环冻结，
# 所有 asyncio 定时器（wall_clock_timeout、memory guard）全部失效。
# 此看门狗在独立线程运行，不受事件循环影响。

def _start_cgroup_watchdog(poll_secs: int = 30, headroom_mb: int = 384):
    """启动线程级 cgroup 内存看门狗。

    当 cgroup memory.current 接近 memory.high 时，直接 os._exit(1)。
    这比 asyncio 版更暴力，但能穿透事件循环冻结。
    systemd 会自动重启进程。
    """
    def _watchdog_loop():
        consecutive_high = 0
        while True:
            time.sleep(poll_secs)
            current = _read_cgroup_int("memory.current")
            high = _read_cgroup_int("memory.high")
            if current is None or high is None:
                continue
            threshold = high - headroom_mb * 1024 * 1024
            if current >= threshold:
                consecutive_high += 1
                headroom_actual = (high - current) // 1048576
                if consecutive_high >= 2:
                    # 连续 2 次检测到高压 → 立即退出，不等 asyncio
                    logger.error(
                        "CGROUP WATCHDOG: memory pressure sustained! "
                        "current=%dMB high=%dMB headroom=%dMB consecutive=%d → force exit",
                        current // 1048576, high // 1048576, headroom_actual, consecutive_high
                    )
                    os._exit(1)
                else:
                    logger.warning(
                        "CGROUP WATCHDOG: memory pressure detected "
                        "current=%dMB high=%dMB headroom=%dMB (consecutive=%d, will exit on next)",
                        current // 1048576, high // 1048576, headroom_actual, consecutive_high
                    )
            else:
                consecutive_high = 0

    t = threading.Thread(target=_watchdog_loop, daemon=True, name="cgroup-watchdog")
    t.start()
    logger.info(f"Cgroup watchdog started: poll={poll_secs}s headroom={headroom_mb}MB")


async def _run_session(agent, directive: str, session_num: int):
    """单次 auto session。"""
    session_ts = time.strftime("%Y%m%d_%H%M%S")
    session_id = f"yogg_{session_num:03d}_{session_ts}"
    channel = LogChannel(session_id)
    auto_state = {channel.id: {"active": True}}

    logger.info(f"=== Yogg session #{session_num} start ({session_id}) ===")
    session_task = asyncio.create_task(run_auto(channel, agent, auto_state, directive=directive))
    memory_watch_task = None
    if YOGG_MEMORY_EXIT_THRESHOLD_MB > 0 or _read_cgroup_int("memory.high") is not None:
        memory_watch_task = asyncio.create_task(_watch_memory_pressure(channel, session_task))
    try:
        if memory_watch_task:
            done, _ = await asyncio.wait({session_task, memory_watch_task}, return_when=asyncio.FIRST_COMPLETED)
            if memory_watch_task in done:
                memory_exit_state = await memory_watch_task
                if memory_exit_state and not session_task.done():
                    session_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await session_task
                else:
                    await session_task
                return memory_exit_state
        await session_task
        return None
    finally:
        if memory_watch_task:
            memory_watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await memory_watch_task
        if not session_task.done():
            session_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session_task
        channel.close()
        logger.info(f"=== Yogg session #{session_num} end ===")


def _clear_crash_counter():
    """Session 正常启动后清除崩溃计数器。"""
    try:
        _CRASH_COUNTER_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _get_provider_override_kwargs():
    api_key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        return {}
    return {
        "api_key": api_key,
        "base_url": (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").strip(),
        "model": (os.environ.get("GENESIS_MODEL") or "deepseek/deepseek-reasoner").strip(),
    }


def _get_memory_exit_state():
    current = _read_cgroup_int("memory.current")
    if current is None:
        return None
    if YOGG_MEMORY_EXIT_THRESHOLD_MB > 0:
        threshold = YOGG_MEMORY_EXIT_THRESHOLD_MB * 1024 * 1024
    else:
        memory_high = _read_cgroup_int("memory.high")
        if memory_high is None:
            return None
        headroom = YOGG_MEMORY_HIGH_HEADROOM_MB * 1024 * 1024
        if memory_high <= headroom:
            return None
        threshold = memory_high - headroom
    if current < threshold:
        return None
    return {
        "current": current,
        "threshold": threshold,
        "memory_high": _read_cgroup_int("memory.high"),
        "memory_max": _read_cgroup_int("memory.max"),
    }


async def _watch_memory_pressure(channel: LogChannel, session_task: asyncio.Task):
    while not session_task.done():
        await asyncio.sleep(YOGG_MEMORY_POLL_SECS)
        if session_task.done():
            break
        memory_state = _get_memory_exit_state()
        if not memory_state:
            continue
        logger.warning(
            "Yogg memory guard triggered | current=%s threshold=%s high=%s max=%s",
            _format_bytes(memory_state["current"]),
            _format_bytes(memory_state["threshold"]),
            _format_bytes(memory_state["memory_high"]),
            _format_bytes(memory_state["memory_max"]),
        )
        await channel.send("♻️ 内存水位接近阈值，当前 session 将结束并交给 systemd 拉起新进程。")
        return memory_state
    return None


async def main():
    directive = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""
    provider_kwargs = _get_provider_override_kwargs()

    # 正常启动成功，清除崩溃计数器
    _clear_crash_counter()
    SelfEvolution.check_and_rollback_if_needed()

    logger.info("Yogg initializing agent...")
    if provider_kwargs:
        logger.info(
            f"Yogg provider override enabled: model={provider_kwargs['model']!r}, base_url={provider_kwargs['base_url']!r}"
        )
    agent = create_agent(**provider_kwargs)
    logger.info(f"Yogg ready. directive={directive[:100]!r}")
    if YOGG_MEMORY_EXIT_THRESHOLD_MB > 0:
        logger.info(
            f"Yogg memory guard enabled: threshold={YOGG_MEMORY_EXIT_THRESHOLD_MB}MiB poll={YOGG_MEMORY_POLL_SECS}s"
        )
    elif _read_cgroup_int("memory.high") is not None:
        logger.info(
            f"Yogg memory guard enabled: headroom={YOGG_MEMORY_HIGH_HEADROOM_MB}MiB poll={YOGG_MEMORY_POLL_SECS}s"
        )

    # 线程级 cgroup 看门狗：asyncio 冻结后的唯一逃生通道
    if _read_cgroup_int("memory.high") is not None:
        _start_cgroup_watchdog(poll_secs=30, headroom_mb=384)

    session_num = 0
    consecutive_crash = 0
    MAX_BACKOFF = 300  # 最大 5 分钟

    while True:
        session_num += 1
        try:
            memory_exit_state = await _run_session(agent, directive, session_num)
            # 正常结束 (planner 建议停止等)
            consecutive_crash = 0
            if memory_exit_state:
                logger.warning(
                    "Yogg exiting for clean restart after memory pressure | current=%s threshold=%s",
                    _format_bytes(memory_exit_state["current"]),
                    _format_bytes(memory_exit_state["threshold"]),
                )
                return
            if YOGG_EXIT_ON_SESSION_END:
                logger.info("Session ended normally. Exiting for clean systemd restart.")
                return
            logger.info("Session ended normally. Restarting in 30s...")
            await asyncio.sleep(30)

        except KeyboardInterrupt:
            logger.info("Yogg: KeyboardInterrupt, exiting.")
            break

        except Exception as e:
            consecutive_crash += 1
            backoff = min(30 * consecutive_crash, MAX_BACKOFF)
            logger.error(
                f"Yogg session #{session_num} crashed: {e!r} "
                f"(consecutive={consecutive_crash}, backoff={backoff}s)",
                exc_info=True,
            )

            await asyncio.sleep(backoff)

            # 每 5 次连续崩溃重建 agent (防内存泄漏)
            if consecutive_crash % 5 == 0:
                logger.warning("Yogg: rebuilding agent after 5 consecutive crashes")
                try:
                    agent = create_agent(**provider_kwargs)
                except Exception as rebuild_e:
                    logger.error(f"Yogg: agent rebuild failed: {rebuild_e}")
                    await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
