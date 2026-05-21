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
from datetime import datetime, timezone, timedelta

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

            # 心跳活墓园清理：删除已死亡且超过 24h 的旧心跳
            try:
                cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)).isoformat()
                hb_deleted = self.vault.cleanup_stale_heartbeats(cutoff)
                if hb_deleted:
                    logger.info(f"Heartbeat cleanup: 清理了 {hb_deleted} 个过期心跳")
            except Exception as e:
                logger.error(f"Heartbeat cleanup 异常: {e}", exc_info=True)

        # ── Trace Pipeline 三阶段（每 GC 轮次同步运行）──
        # Phase 1: 实体提取（增量，轻量）
        # Phase 2: 关系重建 + 社区检测（全量，较重）
        # Phase 3: Evidence Assessment（被动评估已有节点一致性）
        evidence_stats = {}
        if self.cycle_count % GC_EVERY_N_CYCLES == 0:
            try:
                from genesis.v4.trace_pipeline.runner import process_pending_traces
                batch_result = process_pending_traces(limit=200, rebuild_relationships=True)
                processed = batch_result.get("processed", 0)
                skipped = batch_result.get("skipped", 0)
                total_entities = batch_result.get("total_entities", 0)
                rel_stats = batch_result.get("relationship_stats", {})
                community_stats = batch_result.get("community_stats", {})
                evidence_stats = batch_result.get("evidence_assessment", {})

                # 三阶段可见性日志
                phase1_info = f"entities={total_entities} new_canonical={batch_result.get('new_canonical', 0)}"
                phase2_info = f"co_occurs={rel_stats.get('co_occurrence', 0)} diagnosed_by={rel_stats.get('error_patterns', 0)} communities={community_stats.get('valid', 0)}/{community_stats.get('total', 0)}"
                reinforced = len(evidence_stats.get("reinforced", []))
                weakened = len(evidence_stats.get("weakened", []))
                phase3_info = f"reinforced={reinforced} weakened={weakened}"

                logger.info(f"Trace Pipeline: processed={processed} skipped={skipped}")
                logger.info(f"  Phase1 [extract]: {phase1_info}")
                logger.info(f"  Phase2 [rebuild]: {phase2_info}")
                logger.info(f"  Phase3 [evidence]: {phase3_info}")
            except Exception as e:
                logger.error(f"Trace Pipeline 异常: {e}", exc_info=True)

        # ── 干跑审计报告（每 GC 轮次，只读不修改）──
        if self.cycle_count % GC_EVERY_N_CYCLES == 0:
            try:
                void_report = self.vault.void_maintenance_report(stale_days=14)
                if void_report["stale_count"] or void_report["duplicate_count"]:
                    logger.info(
                        f"VOID audit: stale={void_report['stale_count']} "
                        f"duplicate={void_report['duplicate_count']} "
                        f"resolvable={void_report['resolvable_count']}"
                    )
            except Exception as e:
                logger.error(f"VOID audit 异常: {e}", exc_info=True)

            try:
                topo_report = self.vault.topology_audit_report()
                if topo_report["orphan_count"] or topo_report["zero_incoming_count"] or topo_report["virtual_nodes"]["total"] or topo_report["contradicts_edges"]["total"]:
                    logger.info(
                        f"Topology audit: orphan_edges={topo_report['orphan_count']} "
                        f"zero_incoming={topo_report['zero_incoming_count']} "
                        f"virtual={topo_report['virtual_nodes']['total']} "
                        f"contradicts={topo_report['contradicts_edges']['total']} "
                        f"schema_issues={topo_report['schema_issue_count']}"
                    )
            except Exception as e:
                logger.error(f"Topology audit 异常: {e}", exc_info=True)

        logger.info(f"Cycle #{self.cycle_count} 完成 | 签名修复:{sig_fixed} GC:{gc_count} 硬删:{hard_del}")
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

