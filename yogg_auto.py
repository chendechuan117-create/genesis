#!/usr/bin/env python3
"""
Yogg — Genesis 放生模式
无 Discord 依赖的独立 auto runner。直接循环跑 auto mode，崩溃自动重启。

用法:
    python -u yogg_auto.py                       # 默认 directive
    python -u yogg_auto.py "自定义探索方向"      # 自定义 directive

环境变量 (继承 auto_mode 全部配置):
    GENESIS_AUTO_SYNC_DOCTOR_SANDBOX=0   # 强制关闭沙箱同步 (Yogg 就是沙箱本身)
    GENESIS_AUTO_MAX_ROUNDS=0            # 不限轮次
    GENESIS_AUTO_DRY_LIMIT=0             # 不因空转停止
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# ── 强制关闭沙箱同步 (在 import auto_mode 之前设置) ──
os.environ["GENESIS_AUTO_SYNC_DOCTOR_SANDBOX"] = "0"
# 不因空转停止 — Yogg 是放生的，永远跑
os.environ.setdefault("GENESIS_AUTO_DRY_LIMIT", "0")

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Yogg")

from factory import create_agent
from genesis.auto_mode import run_auto

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


async def _run_session(agent, directive: str, session_num: int):
    """单次 auto session。"""
    session_ts = time.strftime("%Y%m%d_%H%M%S")
    session_id = f"yogg_{session_num:03d}_{session_ts}"
    channel = LogChannel(session_id)
    auto_state = {channel.id: {"active": True}}

    logger.info(f"=== Yogg session #{session_num} start ({session_id}) ===")
    try:
        await run_auto(channel, agent, auto_state, directive=directive)
    finally:
        channel.close()
        logger.info(f"=== Yogg session #{session_num} end ===")


async def main():
    directive = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""

    logger.info("Yogg initializing agent...")
    agent = create_agent()
    logger.info(f"Yogg ready. directive={directive[:100]!r}")

    session_num = 0
    consecutive_crash = 0
    MAX_BACKOFF = 300  # 最大 5 分钟

    while True:
        session_num += 1
        try:
            await _run_session(agent, directive, session_num)
            # 正常结束 (planner 建议停止等)
            consecutive_crash = 0
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
                    agent = create_agent()
                except Exception as rebuild_e:
                    logger.error(f"Yogg: agent rebuild failed: {rebuild_e}")
                    await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
