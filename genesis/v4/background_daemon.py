"""
Genesis 后台智能体 (Background Daemon)
合并 Scavenger + Fermentor + Verifier 为统一的 free-API 后台进程。

本质：一个只有 G（思考/搜索）和 C（沉淀）能力的廉价智能体，没有 Op 派发权。
利用免费 LLM 在后台静默运行以下任务：

1. Scavenge (拾荒): 从种子节点发散，搜索互联网，提纯入库
2. Ferment (发酵): 边缘发现 + 概念蒸馏 + 假设引擎
3. Verify (验证): 审计过时/低置信度节点
4. GC (垃圾回收): 清理低置信度且长期未使用的节点
"""

import os
import sys
import json
import re
import time
import asyncio
import logging
import random
from typing import List, Dict, Any, Optional, Tuple

sys.path.insert(0, str(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))))

from genesis.core.config import ConfigManager
from genesis.core.base import Message, MessageRole
from genesis.core.provider_manager import ProviderRouter
from genesis.v4.manager import NodeVault
from genesis.tools.node_tools import CreateMetaNodeTool, CreateNodeEdgeTool
from genesis.tools.web_tool import WebSearchTool
from genesis.tools.url_tool import ReadUrlTool

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
    """统一后台智能体：拾荒 + 发酵 + 验证 + GC"""

    def __init__(self, use_free_pool_only: bool = True):
        self.config = ConfigManager().config
        self.vault = NodeVault(skip_vector_engine=True)

        # 工具实例（直接创建，不依赖 NodeManagementTools）
        self.search_tool = WebSearchTool()
        self.url_tool = ReadUrlTool()
        self.create_meta_tool = CreateMetaNodeTool()
        self.create_edge_tool = CreateNodeEdgeTool()

        self.provider = self._init_provider(use_free_pool_only)
        self.cycle_count = 0

    def _init_provider(self, use_free_pool_only: bool) -> ProviderRouter:
        router = ProviderRouter(self.config)
        if use_free_pool_only:
            free_providers = ["groq", "dashscope", "qianfan", "zhipu", "siliconflow", "cloudflare", "zen"]
            available = [p for p in free_providers if p in router.providers]
            if not available:
                logger.warning("No free LLM configured. Daemon will consume main model tokens.")
                if "deepseek" in router.providers:
                    router._switch_provider("deepseek")
                else:
                    logger.error("No valid providers found.")
                    sys.exit(1)
            else:
                random.shuffle(available)
                router.failover_order = available
                router._switch_provider(available[0])
                router._preferred_provider_name = available[0]
                logger.info(f"Free pool failover: {' → '.join(available)}")
        return router

    # ════════════════════════════════════════════
    #  主循环
    # ════════════════════════════════════════════

    async def run_cycle(self):
        self.cycle_count += 1
        self.vault.heartbeat("daemon", "running", f"cycle #{self.cycle_count}")
        logger.info("=" * 50)
        logger.info(f"🔄 后台智能体 Cycle #{self.cycle_count} 开始")
        logger.info("=" * 50)

        stats = {"scavenged": 0, "edges": 0, "concepts": 0, "hypotheses": 0, "verified": 0, "gc": 0}

        # 1. 拾荒
        try:
            stats["scavenged"] = await self._task_scavenge()
        except Exception as e:
            logger.error(f"拾荒异常: {e}", exc_info=True)

        # 2. 发酵（边缘发现 + 概念蒸馏 + 假设引擎）
        try:
            stats["edges"] = await self._task_discover_edges()
        except Exception as e:
            logger.error(f"边缘发现异常: {e}", exc_info=True)

        try:
            stats["concepts"] = await self._task_distill_concepts()
        except Exception as e:
            logger.error(f"概念蒸馏异常: {e}", exc_info=True)

        try:
            stats["hypotheses"] = await self._task_generate_hypotheses()
        except Exception as e:
            logger.error(f"假设引擎异常: {e}", exc_info=True)

        # 3. 验证
        try:
            stats["verified"] = await self._task_verify()
        except Exception as e:
            logger.error(f"验证异常: {e}", exc_info=True)

        # 4. GC（每 N 轮一次）
        if self.cycle_count % GC_EVERY_N_CYCLES == 0:
            try:
                stats["gc"] = self.vault.purge_forgotten_knowledge(days_threshold=7)
                logger.info(f"🗑️ GC 清理了 {stats['gc']} 个废弃节点")
            except Exception as e:
                logger.error(f"GC 异常: {e}", exc_info=True)

        logger.info("=" * 50)
        logger.info(f"🏁 Cycle #{self.cycle_count} 完成 | "
                     f"拾荒:{stats['scavenged']} 连线:{stats['edges']} "
                     f"概念:{stats['concepts']} 假设:{stats['hypotheses']} "
                     f"验证:{stats['verified']} GC:{stats['gc']}")
        logger.info("=" * 50)
        self.vault.heartbeat("daemon", "idle",
                              f"s:{stats['scavenged']} e:{stats['edges']} c:{stats['concepts']} "
                              f"h:{stats['hypotheses']} v:{stats['verified']} gc:{stats['gc']}")

    # ════════════════════════════════════════════
    #  Task 1: 拾荒 (Scavenge)
    # ════════════════════════════════════════════

    async def _task_scavenge(self) -> int:
        logger.info("[1/4] 🎒 拾荒 (Scavenge)...")
        seed = self._pick_seed_node(min_confidence=0.7)
        if not seed:
            logger.info("  知识库为空或无合适种子。")
            return 0

        logger.info(f"  🌱 种子: [{seed['node_id']}] {seed['title']}")

        # 发散探索方向
        queries = await self._generate_curiosity_queries(seed)
        if not queries:
            logger.info("  本次未产生有价值的探索方向。")
            return 0

        ingested = 0
        for query in queries[:2]:
            logger.info(f"  🔍 探索: {query}")
            raw_content, source_url = await self._forage_information(query)
            if not raw_content:
                logger.info(f"    未获取有效内容，跳过。")
                continue

            ok = await self._distill_and_ingest(seed, query, raw_content, source_url)
            if ok:
                ingested += 1
            break  # 一个方向就够

        return ingested

    def _pick_seed_node(self, min_confidence: float = 0.5) -> Optional[Dict[str, Any]]:
        row = self.vault._conn.execute(
            """SELECT k.node_id, k.title, nc.full_content AS content, k.type, k.confidence_score
               FROM knowledge_nodes k
               LEFT JOIN node_contents nc ON k.node_id = nc.node_id
               WHERE k.confidence_score >= ? AND k.node_id NOT LIKE 'MEM_CONV%'
               ORDER BY RANDOM() LIMIT 1""",
            (min_confidence,)
        ).fetchone()
        if row:
            return dict(row)
        return None

    async def _generate_curiosity_queries(self, seed: Dict[str, Any]) -> List[str]:
        content_preview = (seed.get('content') or '')[:500]
        prompt = f"""你是 Genesis 的"好奇心引擎"。从现有知识中发散出新的探索方向。

当前知识节点:
标题: {seed['title']}
内容: {content_preview}{'...' if len(content_preview) >= 500 else ''}

请提出 1-2 个具体的、可搜索的发散性问题或搜索词。
规则：指向最新发展、最佳实践、常见陷阱或相关工具。
如果没有发散价值，直接输出 "NO_CURIOSITY"。
每行一个搜索词。"""
        try:
            resp = await self.provider.chat(
                messages=[{"role": "system", "content": prompt}], stream=False
            )
            text = resp.content.strip()
            if "NO_CURIOSITY" in text:
                return []
            return [q.strip() for q in text.split('\n') if q.strip()][:2]
        except Exception as e:
            logger.error(f"  生成探索方向异常: {e}")
            return []

    async def _forage_information(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            search_results = await self.search_tool.execute(query, num_results=3)
            target_url = None
            for line in search_results.split('\n'):
                if line.strip().startswith('http'):
                    target_url = line.strip()
                    break
            if not target_url:
                return None, None

            page_content = await self.url_tool.execute(target_url)
            if len(page_content) < 200:
                return None, None
            if len(page_content) > 15000:
                page_content = page_content[:15000] + "...(truncated)"
            return page_content, target_url
        except Exception as e:
            logger.error(f"  拾荒失败: {e}")
            return None, None

    async def _distill_and_ingest(self, seed: Dict, query: str, raw: str, url: str) -> bool:
        prompt = f"""你是 Genesis 的知识提纯器。防止信息污染。
针对问题 "{query}" 抓取到的网页内容。转化为极高密度的干货。

来源: {url}
内容:
{raw[:8000]}

提纯规则：
1. 剔除营销废话、客套话、导航栏等无效信息。
2. 提取核心：机制原理、最佳实践、踩坑记录、代码/命令模板。
3. 内容陈旧或没有实际价值 → 直接输出 "GARBAGE"。
4. 否则使用 create_meta_node 工具创建节点。"""
        try:
            resp = await self.provider.chat(
                messages=[{"role": "system", "content": prompt}],
                tools=[self.create_meta_tool.to_schema()],
                stream=False
            )
            if "GARBAGE" in (resp.content or ""):
                logger.info("    🗑️ 判定为无效信息。")
                return False
            if resp.tool_calls:
                for tc in resp.tool_calls:
                    if tc.name == "create_meta_node":
                        args = tc.arguments
                        if isinstance(args, str):
                            args = json.loads(args)
                        args["ntype"] = "ASSET"
                        args["title"] = f"[拾荒] {args.get('title', '未知发现')}"
                        await self.create_meta_tool.execute(**args)
                        self._mark_as_scavenged(url, seed['node_id'])
                        logger.info(f"    ✨ 入库成功")
                        return True
            return False
        except Exception as e:
            logger.error(f"  提纯入库异常: {e}")
            return False

    def _mark_as_scavenged(self, url: str, seed_id: str):
        try:
            row = self.vault._conn.execute(
                "SELECT node_id, metadata_signature FROM knowledge_nodes ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row:
                new_id = row['node_id']
                sig = self.vault.parse_metadata_signature(row['metadata_signature']) if row['metadata_signature'] else {}
                sig['validation_status'] = 'unverified'
                self.vault._conn.execute(
                    "UPDATE knowledge_nodes SET confidence_score = 0.4, verification_source = ?, "
                    "metadata_signature = ?, trust_tier = 'SCAVENGED' WHERE node_id = ?",
                    (f"scavenger ({url})", json.dumps(sig, ensure_ascii=False), new_id)
                )
                self.vault._conn.execute(
                    "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation, weight) VALUES (?, ?, ?, ?)",
                    (seed_id, new_id, "inspired_by", 0.5)
                )
                self.vault._conn.commit()
                logger.info(f"    📌 标记 {new_id} 为 SCAVENGED, conf=0.4, seed={seed_id}")
        except Exception as e:
            logger.error(f"  标记拾荒状态失败: {e}")

    # ════════════════════════════════════════════
    #  Task 2: 发酵 — 边缘发现 (Edge Discovery)
    # ════════════════════════════════════════════

    async def _task_discover_edges(self) -> int:
        logger.info("[2/4] 🔗 边缘发现 (Edge Discovery)...")
        seeds = self.vault._conn.execute(
            "SELECT node_id, title, type FROM knowledge_nodes "
            "WHERE confidence_score >= 0.5 AND node_id NOT LIKE 'MEM_CONV%' "
            "ORDER BY RANDOM() LIMIT 3"
        ).fetchall()
        if not seeds:
            logger.info("  知识库为空。")
            return 0

        edges_created = 0
        for seed in seeds:
            node_id, title, node_type = seed['node_id'], seed['title'], seed['type']
            logger.info(f"  > 分析: [{node_id}] ({node_type})")

            # 无向量引擎，用关键词匹配找候选邻居
            keywords = [w for w in re.split(r'[\s_,/]+', title) if len(w) >= 2]
            if not keywords:
                continue
            kw_conds = " OR ".join(["(title LIKE ? OR tags LIKE ?)"] * len(keywords))
            kw_params = []
            for kw in keywords:
                kw_params.extend([f"%{kw}%", f"%{kw}%"])
            cand_rows = self.vault._conn.execute(
                f"SELECT node_id, type, title FROM knowledge_nodes "
                f"WHERE node_id != ? AND node_id NOT LIKE 'MEM_CONV%' AND ({kw_conds}) "
                f"ORDER BY RANDOM() LIMIT 3",
                (node_id, *kw_params)
            ).fetchall()
            candidates = [dict(r) for r in cand_rows]
            if not candidates:
                continue

            prompt = f"""你是 Genesis 的自动发酵进程 (The Weaver)。
分析种子节点与候选节点之间是否存在明确的逻辑关联。

种子节点:
ID: {node_id} | 类型: {node_type} | 标题: {title}
内容: {self.vault.get_node_content(node_id)[:500]}

候选节点:
"""
            for i, c in enumerate(candidates, 1):
                prompt += f"--- 候选 {i} ---\nID: {c['node_id']} | 类型: {c['type']} | 标题: {c['title']}\n\n"

            prompt += """如果有强烈的逻辑关系，使用 create_node_edge 工具建立连线。
关系类型：REQUIRES, RESOLVES, RELATED_TO, TRIGGERS
没有明确关系 → 输出 "NO_ACTION"。"""

            try:
                resp = await self.provider.chat(
                    messages=[{"role": "system", "content": prompt}],
                    tools=[self.create_edge_tool.to_schema()],
                    stream=False
                )
                if resp.tool_calls:
                    for tc in resp.tool_calls:
                        if tc.name == "create_node_edge":
                            args = tc.arguments
                            if isinstance(args, str):
                                args = json.loads(args)
                            try:
                                await self.create_edge_tool.execute(**args)
                                edges_created += 1
                                logger.info(f"    🔗 新连线: {args.get('source_id')} --[{args.get('relation')}]--> {args.get('target_id')}")
                            except Exception as e:
                                logger.error(f"    建立连线失败: {e}")
            except Exception as e:
                logger.error(f"  边缘发现请求异常: {e}")

        return edges_created

    # ════════════════════════════════════════════
    #  Task 2b: 发酵 — 概念蒸馏 (Concept Distillation)
    # ════════════════════════════════════════════

    async def _task_distill_concepts(self) -> int:
        logger.info("[2/4] ✨ 概念蒸馏 (Concept Distillation)...")
        # 找孤立的 LESSON（没有出边的）
        lessons = self.vault._conn.execute(
            """SELECT k.node_id, k.title, c.full_content
               FROM knowledge_nodes k
               JOIN node_contents c ON k.node_id = c.node_id
               WHERE k.type = 'LESSON' AND k.confidence_score >= 0.5
                 AND k.node_id NOT IN (SELECT source_id FROM node_edges)
               ORDER BY k.created_at DESC LIMIT 3"""
        ).fetchall()
        if len(lessons) < 2:
            logger.info("  孤立 LESSON 不足 2 个，跳过。")
            return 0

        prompt = "你是 Genesis 的自动发酵进程 (The Alchemist)。\n阅读以下零散教训，尝试抽象出更高阶的底层规律或长期资产(ASSET)。\n\n"
        for idx, lesson in enumerate(lessons, 1):
            prompt += f"--- LESSON {idx} ({lesson['node_id']}) ---\n标题: {lesson['title']}\n内容:\n{(lesson['full_content'] or '')[:500]}\n\n"
        prompt += """如果存在共性规律，使用 create_meta_node 创建 ASSET 节点。
同时用 create_node_edge 关联来源 LESSON（relation: RELATED_TO）。
没有强烈共性 → 输出 "NO_ACTION"。"""

        try:
            resp = await self.provider.chat(
                messages=[{"role": "system", "content": prompt}],
                tools=[self.create_meta_tool.to_schema(), self.create_edge_tool.to_schema()],
                stream=False
            )
            meta_created = 0
            if resp.tool_calls:
                for tc in resp.tool_calls:
                    args = tc.arguments
                    if isinstance(args, str):
                        args = json.loads(args)
                    try:
                        if tc.name == "create_meta_node":
                            await self.create_meta_tool.execute(**args)
                            meta_created += 1
                            logger.info(f"    ✨ 新概念: {args.get('title', '?')}")
                        elif tc.name == "create_node_edge":
                            await self.create_edge_tool.execute(**args)
                            logger.info(f"    🔗 关联: {args.get('source_id')} → {args.get('target_id')}")
                    except Exception as e:
                        logger.error(f"    工具执行失败: {e}")
            return meta_created
        except Exception as e:
            logger.error(f"  概念蒸馏请求异常: {e}")
            return 0

    # ════════════════════════════════════════════
    #  Task 2c: 发酵 — 假设引擎 (Hypothesis Engine)
    # ════════════════════════════════════════════

    async def _task_generate_hypotheses(self) -> int:
        logger.info("[2/4] 💡 假设引擎 (Hypothesis Engine)...")
        seeds = self.vault._conn.execute(
            """SELECT node_id, title, resolves, tags
               FROM knowledge_nodes
               WHERE type = 'LESSON' AND node_id NOT LIKE 'MEM_CONV%'
               ORDER BY confidence_score DESC, RANDOM()
               LIMIT 2"""
        ).fetchall()
        if not seeds:
            logger.info("  无 LESSON 可作启发。")
            return 0

        created = 0
        for seed in seeds:
            seed = dict(seed)
            content = self.vault.get_node_content(seed['node_id'])
            prompt = f"""你是 Genesis 的"假设引擎" (The Speculator)。
阅读已有经验教训，提出一个【未经验证但极具价值的假设】。

启发源:
ID: {seed['node_id']} | 标题: {seed['title']} | 解决: {seed.get('resolves', '')}
内容:
{(content or '')[:1000]}

指令：
1. 思考此教训是否在其他领域/框架/更复杂场景中也适用。
2. 提出一个具体的、可测试的假设。
3. 使用 create_meta_node 创建 EPISODE 节点，标题以 [假设] 开头。
4. 在内容中描述假设及验证步骤。标签包含 hypothesis,unverified。"""

            try:
                resp = await self.provider.chat(
                    messages=[{"role": "system", "content": prompt}],
                    tools=[self.create_meta_tool.to_schema()],
                    stream=False
                )
                if resp.tool_calls:
                    for tc in resp.tool_calls:
                        if tc.name == "create_meta_node":
                            args = tc.arguments
                            if isinstance(args, str):
                                args = json.loads(args)
                            await self.create_meta_tool.execute(**args)
                            # 盖上 FERMENTED 出生证
                            if 'node_id' in args:
                                self.vault._conn.execute(
                                    "UPDATE knowledge_nodes SET trust_tier = 'FERMENTED', confidence_score = 0.45 WHERE node_id = ?",
                                    (args['node_id'],)
                                )
                                self.vault._conn.execute(
                                    "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation, weight) VALUES (?, ?, ?, ?)",
                                    (seed['node_id'], args['node_id'], "inspired_hypothesis", 0.7)
                                )
                                self.vault._conn.commit()
                            created += 1
                            logger.info(f"    💡 假设: {args.get('title', '?')}")
            except Exception as e:
                logger.error(f"  假设引擎异常: {e}")

        return created

    # ════════════════════════════════════════════
    #  Task 3: 验证 (Verify)
    # ════════════════════════════════════════════

    async def _task_verify(self, limit: int = 3) -> int:
        logger.info("[3/4] 🛡️ 验证 (Verify)...")
        candidates = self.vault._conn.execute(
            """SELECT node_id, type, title, resolves, tags
               FROM knowledge_nodes
               WHERE node_id NOT LIKE 'MEM_CONV%'
                 AND type IN ('LESSON', 'CONTEXT')
                 AND (last_verified_at IS NULL OR datetime(last_verified_at) < datetime('now', '-7 days'))
               ORDER BY usage_fail_count DESC, confidence_score ASC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        if not candidates:
            logger.info("  没有需要验证的节点。")
            return 0

        verified = 0
        for cand in candidates:
            cand = dict(cand)
            node_id = cand['node_id']
            content = self.vault.get_node_content(node_id)
            logger.info(f"  > 审计: [{node_id}] {cand['title']}")

            prompt = f"""你是 Genesis 的自动验证进程 (The Auditor)。
审查以下知识节点是否依然合理、是否过时。

ID: {node_id} | 类型: {cand['type']} | 标题: {cand['title']}
关联: {cand.get('resolves', '')} | 标签: {cand.get('tags', '')}
内容:
{(content or '')[:1500]}

请严格输出 JSON（不要有额外文字）：
{{"status": "VALID" | "OBSOLETE" | "NEEDS_REVISION", "reason": "简短理由", "suggested_confidence_delta": 0.0, "validation_status": "validated" | "unverified" | "outdated"}}"""

            try:
                resp = await self.provider.chat(
                    messages=[{"role": "system", "content": prompt}], stream=False
                )
                json_match = re.search(r'\{.*\}', resp.content.strip(), re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                    delta = float(result.get('suggested_confidence_delta', 0.0))
                    v_status = result.get('validation_status', 'unverified')
                    logger.info(f"    -> {result.get('status')}: {result.get('reason')}")

                    if delta > 0:
                        self.vault.promote_node_confidence(node_id, boost=delta)
                    elif delta < 0:
                        self.vault.decay_node_confidence(node_id, penalty=abs(delta))

                    sig_row = self.vault._conn.execute(
                        "SELECT metadata_signature FROM knowledge_nodes WHERE node_id=?", (node_id,)
                    ).fetchone()
                    sig = self.vault.parse_metadata_signature(sig_row[0]) if sig_row and sig_row[0] else {}
                    sig['validation_status'] = v_status
                    self.vault._conn.execute(
                        "UPDATE knowledge_nodes SET metadata_signature = ?, "
                        "last_verified_at = CURRENT_TIMESTAMP, verification_source = 'auditor_daemon' WHERE node_id = ?",
                        (json.dumps(sig, ensure_ascii=False), node_id)
                    )
                    self.vault._conn.commit()
                    verified += 1
                else:
                    logger.warning(f"    -> 解析失败: {resp.content[:100]}")
            except Exception as e:
                logger.error(f"    -> 验证异常: {e}")

        return verified


# ════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════

async def main():
    daemon = BackgroundDaemon(use_free_pool_only=True)
    logger.info("🚀 Genesis 后台智能体已启动")
    while True:
        try:
            await daemon.run_cycle()
        except Exception as e:
            logger.error(f"Cycle 异常: {e}", exc_info=True)
        logger.info(f"💤 休眠 {CYCLE_INTERVAL_SECS // 60} 分钟...")
        await asyncio.sleep(CYCLE_INTERVAL_SECS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("后台智能体手动终止。")
