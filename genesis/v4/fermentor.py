"""
Genesis 知识发酵池 (Knowledge Fermentation Pool)

此进程在后台静默运行，使用免费的 LLM (如 SiliconFlow/DashScope)
对知识库(NodeVault)进行以下操作：
1. Edge Discovery (节点关联): 发现孤立节点之间的隐藏关联，创建 `node_edges`。
2. Concept Distillation (概念抽象): 从多个具体的 CONTEXT/LESSON 节点中提炼出更高阶的 ASSET 节点。
3. Trust Verification (信任验证): 交叉验证节点内容的正确性，更新 `confidence_score`。
"""

import os
import sys
import time
import asyncio
import logging
import random
from typing import List, Dict, Any

# Ensure project root is in path for standalone execution
sys.path.insert(0, str(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))))

from genesis.core.config import ConfigManager
from genesis.core.provider_manager import ProviderRouter
from genesis.core.registry import provider_registry
from genesis.core.base import Message, MessageRole
from genesis.tools.node_tools import CreateNodeEdgeTool, CreateMetaNodeTool
from genesis.v4.manager import NodeVault, NodeManagementTools
from genesis.v4.vector_engine import VectorEngine

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] Fermentor: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Fermentor")


class FermentorDaemon:
    """后台知识发酵精灵"""

    def __init__(self, use_free_pool_only: bool = True):
        self.config = ConfigManager().config
        self.vault = NodeVault()
        self.tools = NodeManagementTools(self.vault)
        self.vector = VectorEngine()
        self.vector.initialize()
        
        # Initialize Free Pool Provider Router
        self.provider = self._init_provider(use_free_pool_only)

    def _init_provider(self, use_free_pool_only: bool) -> ProviderRouter:
        """初始化专用于发酵的廉价/免费 LLM 路由"""
        router = ProviderRouter(self.config)
        
        # 如果强制只使用免费池，我们覆盖路由的默认行为
        if use_free_pool_only:
            free_providers = ["siliconflow", "dashscope", "qianfan", "zhipu"]
            available = [p for p in free_providers if p in router.providers]
            
            if not available:
                logger.warning("没有配置任何免费 LLM (SiliconFlow, DashScope等)！发酵池可能消耗大量主模型 Token。")
                if "deepseek" in router.providers:
                    logger.info("使用 DeepSeek 兜底（注意 API 费用）。")
                    router._switch_provider("deepseek")
                else:
                    logger.error("没有任何可用的 LLM 提供商，发酵池退出。")
                    sys.exit(1)
            else:
                # 随机挑一个免费模型，避免只薅一家羊毛
                chosen = random.choice(available)
                logger.info(f"发酵池选用免费/廉价提供商: {chosen}")
                router._switch_provider(chosen)
                
        return router

    async def run_cycle(self):
        """运行一次发酵循环"""
        logger.info("=========================================")
        logger.info("🌟 知识发酵池 (Fermentation Cycle) 启动")
        logger.info("=========================================")
        
        stats = {"edges_created": 0, "meta_created": 0, "hypotheses_generated": 0}
        
        try:
            # 1. 寻找未关联的节点 (Edge Discovery)
            edges = await self._discover_edges()
            stats["edges_created"] = edges
            
            # 2. 知识沉淀抽象 (Concept Distillation)
            meta = await self._distill_concepts()
            stats["meta_created"] = meta
            
            # 3. 假设引擎 (Hypothesis Generation)
            hypotheses = await self._generate_hypotheses()
            stats["hypotheses_generated"] = hypotheses
            
        except Exception as e:
            logger.error(f"发酵循环异常: {e}", exc_info=True)
            
        logger.info("=========================================")
        logger.info(f"🏁 发酵完成. 连线: {stats['edges_created']}, 概念: {stats['meta_created']}, 假设: {stats['hypotheses_generated']}")
        logger.info("=========================================")

    async def _generate_hypotheses(self) -> int:
        """
        假设引擎 (Hypothesis Engine):
        扫描现有 LESSON，发现知识的空白地带，生成假设（Hypothesis）。
        这是 Hyperspace AGI 第一阶段的思想。
        """
        logger.info("[任务 3/3] 假设引擎 (Hypothesis Generation)...")
        # 挑选最近或高置信度的 LESSON 节点作为启发源
        cursor = self.vault._conn.execute(
            """
            SELECT node_id, title, resolves, tags 
            FROM knowledge_nodes 
            WHERE type = 'LESSON' 
            ORDER BY confidence_score DESC, RANDOM() 
            LIMIT 2
            """
        )
        seeds = [dict(r) for r in cursor.fetchall()]
        
        if not seeds:
            logger.info("没有足够的 LESSON 作为假设启发源。")
            return 0
            
        hypotheses_created = 0
        create_meta_tool = CreateMetaNodeTool()
        create_meta_tool.vault = self.vault
        schema = [create_meta_tool.to_schema()]
        
        for seed in seeds:
            logger.info(f"  > 基于节点提出假设: {seed['node_id']} ({seed['title']})")
            content = self.vault.get_node_content(seed['node_id'])
            
            prompt = f"""你是 Genesis 的"假设引擎" (The Speculator)。
你的任务是阅读已有的经验教训 (LESSON)，并基于它提出一个【未经验证但极具价值的假设】。

启发源：
ID: {seed['node_id']}
标题: {seed['title']}
目标: {seed.get('resolves', '')}

内容:
{content[:1000]}

指令：
1. 思考："如果这个教训是真的，那么它在其他领域、其他框架、或更复杂的场景下，是否也适用？" 或者 "这个排错路线是否可以被编写成一个自动化脚本？"
2. 提出一个具体的、可测试的假设。
3. 使用 `create_meta_node` 工具，创建一个 `EPISODE` 类型的节点，标题必须以 `[假设] ` 开头。
4. 在节点内容中详细描述这个假设，以及未来验证这个假设所需的测试步骤。
5. 标签请包含 `hypothesis,unverified`。
"""
            messages = [Message(role=MessageRole.SYSTEM, content=prompt).to_dict()]
            
            try:
                response = await self.provider.chat(messages, tools=schema, stream=False)
                if response.tool_calls:
                    for tc in response.tool_calls:
                        if tc.name == "create_meta_node":
                            args = tc.arguments
                            if isinstance(args, str):
                                import json
                                args = json.loads(args)
                            res = await create_meta_tool.execute(**args)
                            logger.info(f"  -> {res}")
                            hypotheses_created += 1
                            
                            # 建立关联
                            import json as pyjson
                            if 'node_id' in args:
                                self.vault._conn.execute(
                                    "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation, weight) VALUES (?, ?, ?, ?)",
                                    (seed['node_id'], args['node_id'], "inspired_hypothesis", 0.7)
                                )
                                self.vault._conn.commit()
            except Exception as e:
                logger.error(f"  -> 生成假设请求异常: {e}")
                
        return hypotheses_created

    async def _discover_edges(self) -> int:
        """
        随机抽取 5 个最近活跃的节点，利用向量搜索找出相似节点，
        然后让 LLM 判断它们之间是否有逻辑联系（如 prerequisite, resolves, related）。
        """
        logger.info("[任务 1/2] 边缘发现 (Edge Discovery)...")
        # 1. 获取种子节点
        cursor = self.vault._conn.execute("SELECT node_id, title, type FROM knowledge_nodes ORDER BY RANDOM() LIMIT 3")
        seed_nodes = cursor.fetchall()
            
        if not seed_nodes:
            logger.info("知识库为空，跳过。")
            return 0

        edges_created = 0
        for node_id, title, node_type in seed_nodes:
            logger.info(f"  > 分析种子节点: {node_id} ({node_type})")
            
            # 2. 向量召回最相似的 3 个候选节点
            results = self.vault.search_knowledge(title, limit=3)
            candidates = [r for r in results if r["node_id"] != node_id]
            
            if not candidates:
                continue
                
            # 3. 让 LLM 判断连线
            prompt = f"""你是 Genesis 的自动发酵进程 (The Weaver)。
任务：分析种子节点与候选节点之间是否存在明确的逻辑关联。

种子节点:
ID: {node_id}
类型: {node_type}
标题: {title}
内容: {self.vault.get_node_content(node_id)[:500]}

候选节点:
"""
            for i, cand in enumerate(candidates, 1):
                prompt += f"--- 候选 {i} ---\n"
                prompt += f"ID: {cand['node_id']}\n类型: {cand['type']}\n标题: {cand['title']}\n\n"

            prompt += """
判断规则：
如果种子节点与某个候选节点有强烈的逻辑关系，请使用 `create_node_edge` 工具建立连线。
关系类型仅限：
- `prerequisite`: 种子是候选的前置条件（或反之，注意方向）
- `resolves`: 种子解决了候选提出的问题
- `related`: 强相关背景概念
- `conflicts`: 两者存在冲突或矛盾

如果没有明确关系，请输出 "NO_ACTION"。你可以调用多次工具。
"""
            messages = [Message(role=MessageRole.SYSTEM, content=prompt)]
            schema = [self.tools.create_node_edge_tool().to_schema()]
            
            response = await self.provider.chat(messages=[m.to_dict() for m in messages], tools=schema)
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    if tc.name == "create_node_edge":
                        logger.info(f"    🔗 发现新连线: {tc.arguments}")
                        try:
                            await self.tools.execute(tc.name, tc.arguments)
                            edges_created += 1
                        except Exception as e:
                            logger.error(f"建立连线失败: {e}")
                            
        return edges_created

    async def _distill_concepts(self) -> int:
        """
        收集最近未被消化的 LESSON / EPISODE，尝试抽象成更高维度的 ASSET 或 PATTERN。
        """
        logger.info("[任务 2/2] 概念蒸馏 (Concept Distillation)...")
        # 找几个没连过线的 LESSON
        cursor = self.vault._conn.execute("""
            SELECT k.node_id, k.title, c.full_content 
            FROM knowledge_nodes k
            JOIN node_contents c ON k.node_id = c.node_id
            WHERE k.type = 'LESSON' 
            AND k.node_id NOT IN (SELECT source_id FROM node_edges)
            ORDER BY k.created_at DESC LIMIT 3
        """)
        lessons = cursor.fetchall()
            
        if len(lessons) < 2:
            logger.info("  孤立 LESSON 数量不足，暂不进行抽象。")
            return 0
            
        prompt = "你是 Genesis 的自动发酵进程 (The Alchemist)。\n任务：阅读以下近期积累的零散教训(LESSON)，尝试抽象出更高阶的底层规律或长期资产(ASSET)。\n\n"
        for idx, (nid, title, content) in enumerate(lessons, 1):
            prompt += f"--- LESSON {idx} ({nid}) ---\n标题: {title}\n内容:\n{content[:500]}\n\n"
            
        prompt += """
判断规则：
如果这些教训中存在共性，或者揭示了某个通用的系统性问题/解决方案，请使用 `create_meta_node` 创建一个全新的 ASSET 节点。
同时使用 `create_node_edge` 将新的 ASSET 节点与这些来源 LESSON 节点关联起来 (relation: 'abstracted_from')。

如果没有发现强烈的共性规律，不要强行制造，直接输出 "NO_ACTION"。
"""
        messages = [Message(role=MessageRole.SYSTEM, content=prompt)]
        schema = [
            self.tools.create_meta_node_tool().to_schema(),
            self.tools.create_node_edge_tool().to_schema()
        ]
        
        response = await self.provider.chat(messages=[m.to_dict() for m in messages], tools=schema)
        
        meta_created = 0
        if response.tool_calls:
            for tc in response.tool_calls:
                logger.info(f"    ✨ 抽象动作: {tc.name} -> {tc.arguments}")
                try:
                    await self.tools.execute(tc.name, tc.arguments)
                    if tc.name == "create_meta_node":
                        meta_created += 1
                except Exception as e:
                    logger.error(f"抽象节点失败: {e}")
                    
        return meta_created


async def main():
    daemon = FermentorDaemon(use_free_pool_only=True)
    while True:
        await daemon.run_cycle()
        # 发酵周期：每小时运行一次
        logger.info("💤 发酵池进入休眠，1 小时后唤醒...")
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("发酵池手动终止。")
