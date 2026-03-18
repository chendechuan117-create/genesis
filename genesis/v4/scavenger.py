"""
Genesis 拾荒者精灵 (Scavenger Daemon) - "盲盒发散模式"
集成AgentBrowserTool版本

此进程在后台静默运行，利用廉价/免费的 LLM (如 SiliconFlow/DashScope) 主动探索互联网。
核心目标：打破 AI 回音壁，主动从现有知识中发散，搜集并提纯最新的社区最佳实践、工具更新或边缘知识，充实元信息。

工作流：
1. Seed (起念): 随机抽取知识库中的节点，LLM 扮演"好奇心引擎"，提出 1-2 个发散性问题或搜索词。
2. Forage (拾荒): 使用 web_search 搜索，使用 read_url 深度抓取网页内容，使用 agent_browser 作为备选方案。
3. Distill (提纯): LLM 扮演"知识漏斗"，严格过滤无用信息/营销废话，提炼出极高密度的干货。
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
from genesis.skills.agent_browser_tool import AgentBrowserTool

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] Scavenger: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Scavenger")


class ScavengerDaemon:
    def __init__(self, use_free_pool_only: bool = True, use_browser_tool: bool = True):
        self.config = ConfigManager().config
        self.vault = NodeVault()
        
        # Tools for foraging
        self.search_tool = WebSearchTool()
        self.url_tool = ReadUrlTool()
        self.create_meta_tool = CreateMetaNodeTool()
        
        # 浏览器工具作为备选方案
        self.use_browser_tool = use_browser_tool
        self.browser_tool = None
        if use_browser_tool:
            try:
                self.browser_tool = AgentBrowserTool()
                logger.info("✅ AgentBrowserTool 已加载")
            except Exception as e:
                logger.warning(f"⚠️ 无法加载AgentBrowserTool: {e}")
                logger.info("将仅使用WebSearchTool和ReadUrlTool")
                self.use_browser_tool = False
        
        self.provider = self._init_provider(use_free_pool_only)

    def _init_provider(self, use_free_pool_only: bool) -> ProviderRouter:
        router = ProviderRouter(self.config)
        if use_free_pool_only:
            free_providers = ["siliconflow", "dashscope", "qianfan", "zhipu", "groq", "cloudflare", "zen"]
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
            SELECT k.node_id, k.title, k.content, k.ntype, k.confidence_score
            FROM knowledge_nodes k
            WHERE k.confidence_score >= 0.7
            ORDER BY RANDOM()
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return {
                'node_id': row[0],
                'title': row[1],
                'content': row[2],
                'ntype': row[3],
                'confidence_score': row[4]
            }
        return None

    async def _generate_curiosity_queries(self, seed: Dict[str, Any]) -> List[str]:
        """生成发散性问题/搜索词"""
        prompt = f"""你是 Genesis 的"好奇心引擎"。你的任务是从现有知识中发散出新的探索方向。

当前知识节点:
标题: {seed['title']}
内容: {seed['content'][:500]}{'...' if len(seed['content']) > 500 else ''}

请基于这个知识，提出 1-2 个具体的、有价值的发散性问题或搜索词。
规则：
1. 问题应该指向该知识的最新发展、最佳实践、常见陷阱或相关工具。
2. 搜索词应该具体、可搜索，避免过于宽泛。
3. 如果这个知识已经非常陈旧或没有发散价值，请直接输出 "NO_CURIOSITY"。

请直接输出问题或搜索词，每行一个。"""
        
        try:
            messages = [Message(role=MessageRole.SYSTEM, content=prompt).to_dict()]
            resp = await self.provider.chat(messages=messages)
            
            content = resp.content.strip()
            if "NO_CURIOSITY" in content:
                return []
                
            # 按行分割，过滤空行
            queries = [q.strip() for q in content.split('\n') if q.strip()]
            return queries[:2]  # 最多返回2个
            
        except Exception as e:
            logger.error(f"生成探索方向异常: {e}")
            return []

    async def _forage_information(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """执行信息拾荒"""
        logger.info("   > 开始信息拾荒 (Foraging)...")
        
        # 策略1: 首先尝试Web搜索
        try:
            logger.info("   > 策略1: 使用WebSearchTool搜索...")
            search_results = await self.search_tool.execute(query, num_results=3)
            
            # 解析搜索结果，获取第一个有效URL
            lines = search_results.split('\n')
            target_url = None
            for line in lines:
                if line.startswith('   http'):
                    target_url = line.strip()
                    break
            
            if not target_url:
                logger.info("   > 未找到有效URL，尝试备选策略...")
                return await self._try_alternative_forage_strategy(query)
            
            logger.info(f"   > 锁定目标网址: {target_url}，正在深度抓取...")
            
            # 策略2: 尝试使用ReadUrlTool抓取内容
            try:
                page_content = await self.url_tool.execute(target_url)
                
                # 如果内容太短，可能是抓取失败或被屏蔽
                if len(page_content) < 200:
                    logger.warning("   > 网页内容过短，尝试浏览器工具...")
                    return await self._try_browser_tool(target_url, query)
                    
                # 截断超长内容，防止爆 token
                if len(page_content) > 15000:
                    page_content = page_content[:15000] + "...(truncated)"
                    
                return page_content, target_url
                
            except Exception as e:
                logger.warning(f"   > ReadUrlTool抓取失败: {e}，尝试浏览器工具...")
                return await self._try_browser_tool(target_url, query)
                
        except Exception as e:
            logger.error(f"   > Web搜索失败: {e}")
            return await self._try_alternative_forage_strategy(query)

    async def _try_alternative_forage_strategy(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """尝试备选拾荒策略"""
        # 策略2: 如果Web搜索失败，尝试直接使用浏览器工具搜索
        if self.use_browser_tool and self.browser_tool:
            try:
                logger.info("   > 策略2: 使用AgentBrowserTool直接访问搜索引擎...")
                
                # 构建搜索URL
                search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                
                # 使用浏览器工具获取页面内容
                result = await self.browser_tool.execute("snapshot", url=search_url)
                
                # 从快照中提取文本内容
                if "页面快照获取成功" in result:
                    # 提取快照中的文本内容
                    lines = result.split('\n')
                    text_content = []
                    for line in lines:
                        if line.strip() and not line.startswith('@e') and not line.startswith('✅') and not line.startswith('元素数量'):
                            text_content.append(line.strip())
                    
                    content = '\n'.join(text_content[:50])  # 取前50行
                    if len(content) > 500:
                        return content, search_url
                
            except Exception as e:
                logger.warning(f"   > AgentBrowserTool也失败: {e}")
        
        # 策略3: 如果所有方法都失败，返回None
        return None, None

    async def _try_browser_tool(self, url: str, query: str) -> tuple[Optional[str], Optional[str]]:
        """尝试使用浏览器工具抓取内容"""
        if self.use_browser_tool and self.browser_tool:
            try:
                logger.info(f"   > 使用AgentBrowserTool抓取: {url}")
                
                # 获取页面快照（包含可访问性树）
                result = await self.browser_tool.execute("snapshot", url=url)
                
                if "页面快照获取成功" in result:
                    # 从快照中提取文本内容
                    lines = result.split('\n')
                    text_content = []
                    for line in lines:
                        if line.strip() and not line.startswith('@e') and not line.startswith('✅') and not line.startswith('元素数量'):
                            # 移除ANSI颜色代码
                            import re
                            clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                            text_content.append(clean_line.strip())
                    
                    content = '\n'.join(text_content[:100])  # 取前100行
                    if len(content) > 200:
                        return content, url
                
            except Exception as e:
                logger.error(f"   > AgentBrowserTool抓取失败: {e}")
        
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
            cursor = self.vault._conn.execute("SELECT node_id, metadata_signature FROM knowledge_nodes ORDER BY created_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                new_id = row[0]
                # 注入 validation_status='unverified' 到 metadata_signature
                existing_sig = self.vault.parse_metadata_signature(row[1]) if row[1] else {}
                existing_sig['validation_status'] = 'unverified'
                sig_json = json.dumps(existing_sig, ensure_ascii=False)
                # 降低置信度 (0.4)，标记来源，标记为未验证
                self.vault._conn.execute(
                    "UPDATE knowledge_nodes SET confidence_score = 0.4, verification_source = ?, metadata_signature = ? WHERE node_id = ?",
                    (f"scavenger_bot ({url})", sig_json, new_id)
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
    # 可以通过环境变量控制是否使用浏览器工具
    use_browser_tool = os.environ.get("SCAVENGER_USE_BROWSER", "true").lower() == "true"
    
    daemon = ScavengerDaemon(use_free_pool_only=True, use_browser_tool=use_browser_tool)
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