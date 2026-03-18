"""
Genesis 拾荒者精灵 (Scavenger Daemon) - "盲盒发散模式"

此进程在后台静默运行，利用廉价/免费的 LLM (如 SiliconFlow/DashScope) 主动探索互联网。
核心目标：打破 AI 回音壁，主动从现有知识中发散，搜集并提纯最新的社区最佳实践、工具更新或边缘知识，充实元信息。

工作流：
1. Seed (起念): 随机抽取知识库中的节点，LLM 扮演“好奇心引擎”，提出 1-2 个发散性问题或搜索词。
2. Forage (拾荒): 使用 web_search 搜索，使用 read_url 深度抓取网页内容。
3. Distill (提纯): LLM 扮演“知识漏斗”，严格过滤无用信息/营销废话，提炼出极高密度的干货。
4. Ingest (入库): 存入 NodeVault (带有较低的初始 confidence_score 和特殊的 source 标记)，供主 Agent 未来参考。
"""

import os
import sys
import time
import json
import asyncio
import logging
import random
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))))

from genesis.core.config import ConfigManager
from genesis.core.base import Message, MessageRole
from genesis.core.provider_manager import ProviderRouter
from genesis.v4.manager import NodeVault, NodeManagementTools
from genesis.tools.node_tools import CreateMetaNodeTool
from genesis.tools.web_tool import WebSearchTool
from genesis.tools.url_tool import ReadUrlTool

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] Scavenger: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Scavenger")


class ScavengerDaemon:
    def __init__(self, use_free_pool_only: bool = True):
        self.config = ConfigManager().config
        self.vault = NodeVault()
        
        # Tools for foraging
        self.search_tool = WebSearchTool()
        self.url_tool = ReadUrlTool()
        self.create_meta_tool = CreateMetaNodeTool()
        
        self.provider = self._init_provider(use_free_pool_only)

    def _init_provider(self, use_free_pool_only: bool) -> ProviderRouter:
        router = ProviderRouter(self.config)
        if use_free_pool_only:
            free_providers = ["siliconflow", "dashscope", "qianfan", "zhipu"]
            available = [p for p in free_providers if p in router.providers]
            
            if not available:
                logger.warning("No free LLM configured. Scavenger will consume main model tokens.")
                if "deepseek" in router.providers:
                    router._switch_provider("deepseek")
                else:
                    logger.error("No valid providers found for Scavenger.")
                    sys.exit(1)
            else:
                chosen = random.choice(available)
                logger.info(f"Using Free/Cheap Provider: {chosen}")
                router._switch_provider(chosen)
        return router

    async def run_cycle(self):
        logger.info("=========================================")
        logger.info("🎒 拾荒者 (Scavenger) 开启新的远征")
        logger.info("=========================================")
        
        # 1. 抽取种子节点 (Seed)
        seed_node = self._pick_seed_node()
        if not seed_node:
            logger.info("知识库为空，等待主流程产生初始知识。")
            return
            
        logger.info(f"🌱 灵感种子: [{seed_node['node_id']}] {seed_node['title']}")
        
        # 2. 发散探索方向 (Curiosity)
        queries = await self._generate_curiosity_queries(seed_node)
        if not queries:
            logger.info("🧠 本次未产生有价值的探索方向。")
            return
            
        # 3. 执行拾荒 (Forage)
        for query in queries:
            logger.info(f"🔍 探索方向: {query}")
            raw_content, source_url = await self._forage_information(query)
            
            if not raw_content:
                logger.info(f"   ❌ 未能获取有效网页内容，跳过该方向。")
                continue
                
            # 4. 提纯入库 (Distill & Ingest)
            await self._distill_and_ingest(seed_node, query, raw_content, source_url)
            
            # 探索一个方向就够了，避免单次循环太久
            break
            
        logger.info("=========================================")
        logger.info("🏕️ 远征结束，返回营地休整。")
        logger.info("=========================================")

    def _pick_seed_node(self) -> Optional[Dict[str, Any]]:
        cursor = self.vault._conn.execute("""
            SELECT k.node_id, k.title, k.type, c.full_content 
            FROM knowledge_nodes k
            LEFT JOIN node_contents c ON k.node_id = c.node_id
            WHERE k.node_id NOT LIKE 'MEM_CONV%'
            ORDER BY RANDOM() LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def _generate_curiosity_queries(self, seed: Dict[str, Any]) -> List[str]:
        prompt = f"""你是 Genesis 的后台拾荒者 (The Scavenger)。你的目标是打破 AI 的信息茧房。
请阅读以下我们已知的知识节点，发挥你的发散思维，提出 1 到 2 个值得深入探索的问题或搜索关键词。

已知节点 ({seed['type']}):
标题: {seed['title']}
内容: {str(seed.get('full_content', ''))[:800]}

思考方向建议：
1. 这个技术/概念最新有什么突破性进展？
2. 社区里对于这个问题有没有更优雅的替代方案 (Best Practices)？
3. 它在与其他现代技术栈结合时有什么盲区？

请只输出一个 JSON 数组，包含 1-2 个精准的英文或中文搜索关键词，例如：
["n8n 2026 latest alternatives", "EndeavourOS pacman optimization tricks"]
不要输出任何其他解释文本。"""

        try:
            resp = await self.provider.chat([Message(role=MessageRole.SYSTEM, content=prompt).to_dict()])
            content = resp.content.strip()
            # 清理可能的 markdown 标记
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            queries = json.loads(content)
            if isinstance(queries, list):
                return queries[:2]
        except Exception as e:
            logger.error(f"发散思考失败: {e}")
        return []

    async def _forage_information(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        import re
        logger.info("   > 正在使用 web_search...")
        try:
            # 搜索结果是格式化的字符串
            search_res_str = await self.search_tool.execute(query)
            
            # 使用正则提取 URL
            urls = re.findall(r'(https?://[^\s]+)', search_res_str)
            
            if not urls:
                logger.info(f"   ❌ web_search 未返回有效链接: {search_res_str[:100]}")
                return None, None
                
            # 优先选择非垃圾站点的链接，排除广告或聚合站
            target_url = urls[0]
            for u in urls:
                if any(domain in u for domain in ["github.com", "stackoverflow.com", "medium.com", "dev.to", "official"]):
                    target_url = u
                    break
                    
            logger.info(f"   > 锁定目标网址: {target_url}，正在深度抓取...")
            page_content = await self.url_tool.execute(target_url)
            
            # 如果内容太短，可能是抓取失败或被屏蔽
            if len(page_content) < 200:
                logger.warning("   > 网页内容过短，放弃。")
                return None, None
                
            # 截断超长内容，防止爆 token
            if len(page_content) > 15000:
                page_content = page_content[:15000] + "...(truncated)"
                
            return page_content, target_url
            
        except Exception as e:
            logger.error(f"拾荒过程异常: {e}")
            return None, None

    async def _distill_and_ingest(self, seed: Dict[str, Any], query: str, raw_content: str, source_url: str):
        logger.info("   > 开始提纯知识 (Distillation)...")
        prompt = f"""你是 Genesis 的知识提纯器。你的任务是防止信息污染。
以下是针对问题 "{query}" 抓取到的网页内容。你需要将其转化为极高密度的干货。

来源: {source_url}
内容:
{raw_content[:8000]}

提纯规则：
1. 剔除所有营销废话、客套话、导航栏等无效信息。
2. 提取最核心的：机制原理、最佳实践、踩坑记录、代码/命令模板。
3. 如果这篇文章内容陈旧或没有实际价值，请直接输出 "GARBAGE"。
4. 否则，请按要求输出一个高质量的知识片段，以便主系统未来参考。
"""
        try:
            messages = [Message(role=MessageRole.SYSTEM, content=prompt).to_dict()]
            tools = [self.create_meta_tool.to_schema()]
            
            resp = await self.provider.chat(messages=messages, tools=tools)
            
            if "GARBAGE" in resp.content:
                logger.info("   🗑️ 判定为无效信息，已丢弃。")
                return
                
            if resp.tool_calls:
                for tc in resp.tool_calls:
                    if tc.name == "create_meta_node":
                        logger.info("   ✨ 提纯成功！准备入库...")
                        args = tc.arguments
                        # 强制覆写置信度和标签，因为是野外搜集的
                        if isinstance(args, str):
                            args = json.loads(args)
                        args["ntype"] = "ASSET" # 野外搜集作为参考资产
                        args["title"] = f"[拾荒] {args.get('title', '未知发现')}"
                        
                        # 把参数重新编码
                        tc.arguments = json.dumps(args)
                        
                        await self.create_meta_tool.execute(**args)
                        
                        # 找到刚写入的节点 (最新创建的 ASSET)
                        # 并强行降低置信度，增加标记
                        self._mark_as_scavenged(source_url, seed['node_id'])
            else:
                logger.info("   ⚠️ 模型未调用节点创建工具。")
                
        except Exception as e:
            logger.error(f"提纯入库异常: {e}")

    def _mark_as_scavenged(self, url: str, seed_id: str):
        try:
            # 找到最新的一个节点
            cursor = self.vault._conn.execute("SELECT node_id FROM knowledge_nodes ORDER BY created_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                new_id = row[0]
                # 降低置信度 (0.4) 并标记来源
                self.vault._conn.execute(
                    "UPDATE knowledge_nodes SET confidence_score = 0.4, verification_source = ? WHERE node_id = ?",
                    (f"scavenger_bot ({url})", new_id)
                )
                # 建立关联：此知识是从 seed 发散出来的
                self.vault._conn.execute(
                    "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation, weight) VALUES (?, ?, ?, ?)",
                    (seed_id, new_id, "inspired_by", 0.5)
                )
                self.vault._conn.commit()
                logger.info(f"   📌 已将节点 {new_id} 标记为拾荒来源，置信度 0.4，并链接到种子 {seed_id}。")
        except Exception as e:
            logger.error(f"标记拾荒状态失败: {e}")


async def main():
    daemon = ScavengerDaemon(use_free_pool_only=True)
    while True:
        await daemon.run_cycle()
        
        # 随机休眠 30~60 分钟，避免请求过于频繁
        sleep_time = random.randint(1800, 3600)
        logger.info(f"💤 拾荒者进入休眠，{sleep_time//60} 分钟后再次出发...")
        await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("拾荒者手动终止。")
