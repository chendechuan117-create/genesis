"""
Genesis 后台守护进程 (Background Daemon)
职责：知识库 GC + 节点清理 + 签名审计 + Evidence Assessor 批量触发。

历史：曾包含 Scavenger（拾荒）、Fermentor（发酵）、Verifier（验证）三个 LLM 驱动任务。
经评估，三者产出零使用率或已被主循环知识驱动任务替代，于 2026-04-05 移除。
原文件归档于 archive/daemon_deprecated/。
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

sys.path.insert(0, str(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))))

from genesis.v4.manager import NodeVault
from genesis.v4.trace_pipeline.node_cleanup import cleanup as node_cleanup

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] Daemon: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("BackgroundDaemon")

# ── 周期配置 ──
CYCLE_INTERVAL_SECS = 1800   # 每 30 分钟跑一轮
GC_EVERY_N_CYCLES = 6        # 每 6 轮（约 3 小时）跑一次 GC


class BackgroundDaemon:
    """后台守护：GC + 节点清理 + 签名审计 + Evidence Assessor"""

    def __init__(self):
        self.vault = NodeVault(skip_vector_engine=True)
        self.cycle_count = 0

    # ════════════════════════════════════════════
    #  主循环
    # ════════════════════════════════════════════

    async def run_cycle(self):
        self.cycle_count += 1
        self.vault.heartbeat("daemon", "running", f"cycle #{self.cycle_count}")
        logger.info(f"Cycle #{self.cycle_count} 开始")

        gc_count = 0
        sig_fixed = 0

        # 签名审计（零 LLM 成本）
        if hasattr(self.vault, 'audit_signatures'):
            try:
                sig_stats = self.vault.audit_signatures(limit=50)
                sig_fixed = sig_stats.get("fixed_normalize", 0) + sig_stats.get("fixed_blacklist", 0) + sig_stats.get("fixed_contradiction", 0) + sig_stats.get("fixed_invalidation_reason", 0)
                if sig_fixed:
                    logger.info(f"签名审计: {sig_stats['audited']} 扫描, {sig_fixed} 修复")
            except Exception as e:
                logger.error(f"签名审计异常: {e}", exc_info=True)

        # GC（每 N 轮一次）
        hard_del = 0
        if self.cycle_count % GC_EVERY_N_CYCLES == 0:
            try:
                gc_count = self.vault.purge_forgotten_knowledge(days_threshold=7)
                logger.info(f"GC 清理了 {gc_count} 个废弃节点")
            except Exception as e:
                logger.error(f"GC 异常: {e}", exc_info=True)
            # 节点清理：未使用+超龄节点硬删
            try:
                cleanup_result = node_cleanup(dry_run=False)
                hard_del = cleanup_result.get("hard_deleted", 0)
                if hard_del:
                    logger.info(f"Node cleanup: 硬删 {hard_del}")
            except Exception as e:
                logger.error(f"Node cleanup 异常: {e}", exc_info=True)

        # Evidence Assessor 批量触发（每 GC 轮次同步运行）
        evidence_stats = {}
        if self.cycle_count % GC_EVERY_N_CYCLES == 0:
            try:
                from genesis.v4.trace_pipeline.runner import process_pending_traces
                batch_result = process_pending_traces(limit=200, rebuild_relationships=False)
                evidence_stats = batch_result.get("evidence_assessment", {})
                reinforced = len(evidence_stats.get("reinforced", []))
                weakened = len(evidence_stats.get("weakened", []))
                if reinforced or weakened:
                    logger.info(f"Evidence Assessor: reinforced={reinforced} weakened={weakened}")
            except Exception as e:
                logger.error(f"Evidence Assessor 异常: {e}", exc_info=True)

        logger.info(f"Cycle #{self.cycle_count} 完成 | 签名修复:{sig_fixed} GC:{gc_count} 硬删:{hard_del} 证据评估:{evidence_stats.get('reinforced', [])[:1]}")
        self.vault.heartbeat("daemon", "idle",
                              f"sig:{sig_fixed} gc:{gc_count} hdel:{hard_del}")


# ════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════

async def main():
    daemon = BackgroundDaemon()
    logger.info("Genesis 后台守护进程已启动（GC + 签名审计）")
    while True:
        try:
            await daemon.run_cycle()
        except Exception as e:
            logger.error(f"Cycle 异常: {e}", exc_info=True)
        logger.info(f"休眠 {CYCLE_INTERVAL_SECS // 60} 分钟...")
        await asyncio.sleep(CYCLE_INTERVAL_SECS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("后台守护进程手动终止。")

