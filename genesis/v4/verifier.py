import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import asyncio
import logging
import random
import time
from typing import Dict, Any, List

from genesis.core.config import ConfigManager
from genesis.core.provider_manager import ProviderRouter
from genesis.core.base import Message, MessageRole
from genesis.v4.manager import NodeVault

logger = logging.getLogger("verifier")

class KnowledgeVerifier:
    """
    独立后台验证循环 (Verification Loop)
    定期扫描 LESSON 和 CONTEXT 节点，用 LLM 模拟测试场景，判断知识是否仍然正确。
    相当于给静态知识加上了客观验证层。
    """
    
    def __init__(self, use_free_pool_only: bool = True):
        self.config = ConfigManager()
        self.vault = NodeVault()
        self.provider = self._init_provider(use_free_pool_only)
        
    def _init_provider(self, use_free_pool_only: bool):
        from genesis.providers.cloud_providers import _build_qianfan, _build_zhipu, _build_siliconflow, _build_deepseek, _build_groq, _build_cloudflare, _build_zen
        import os
        
        qianfan_key = os.environ.get("QIANFAN_API_KEY")
        zhipu_key = os.environ.get("ZHIPU_API_KEY")
        sf_key = os.environ.get("SILICONFLOW_API_KEY")
        ds_key = os.environ.get("DEEPSEEK_API_KEY")
        groq_key = os.environ.get("GROQ_API_KEY")
        cf_key = os.environ.get("CLOUDFLARE_API_KEY")
        zen_key = os.environ.get("ZEN_API_KEY")
        
        if groq_key:
            self.config._config.groq_api_key = groq_key
            logger.info("验证池选用廉价提供商: groq")
            return _build_groq(self.config)
        elif zen_key:
            self.config._config.zen_api_key = zen_key
            logger.info("验证池选用廉价提供商: zen")
            return _build_zen(self.config)
        elif cf_key:
            self.config._config.cloudflare_api_key = cf_key
            logger.info("验证池选用廉价提供商: cloudflare")
            return _build_cloudflare(self.config)
        elif sf_key:
            self.config._config.siliconflow_api_key = sf_key
            logger.info("验证池选用廉价提供商: siliconflow")
            return _build_siliconflow(self.config)
        elif qianfan_key:
            self.config._config.qianfan_api_key = qianfan_key
            logger.info("验证池选用廉价提供商: qianfan")
            return _build_qianfan(self.config)
        elif zhipu_key:
            self.config._config.zhipu_api_key = zhipu_key
            logger.info("验证池选用廉价提供商: zhipu")
            return _build_zhipu(self.config)
        elif ds_key:
            self.config._config.deepseek_api_key = ds_key
            logger.info("验证池选用提供商: deepseek")
            return _build_deepseek(self.config)
            
        logger.error("No valid API keys found for verifier")
        return None

    async def verify_cycle(self, limit: int = 3):
        """执行一次验证循环"""
        logger.info("=========================================")
        logger.info("🛡️ 知识验证池 (Verification Cycle) 启动")
        logger.info("=========================================")
        
        # 挑选久未验证或置信度较低的 LESSON/CONTEXT
        # 或者挑选那些竞技场中经常失败的节点
        cursor = self.vault._conn.execute(
            """
            SELECT node_id, type, title, resolves, tags
            FROM knowledge_nodes 
            WHERE node_id NOT LIKE 'MEM_CONV%' 
              AND type IN ('LESSON', 'CONTEXT')
              AND (last_verified_at IS NULL OR datetime(last_verified_at) < datetime('now', '-7 days'))
            ORDER BY usage_fail_count DESC, confidence_score ASC
            LIMIT ?
            """, (limit,)
        )
        candidates = [dict(r) for r in cursor.fetchall()]
        
        if not candidates:
            logger.info("没有需要验证的节点。")
            return
            
        for cand in candidates:
            await self._verify_single_node(cand)
            
        logger.info("=========================================")
        logger.info("🏁 验证循环完成。")
        logger.info("=========================================")

    async def _verify_single_node(self, node: Dict[str, Any]):
        node_id = node['node_id']
        title = node['title']
        content = self.vault.get_node_content(node_id)
        
        logger.info(f"  > 验证目标: [{node_id}] {title}")
        
        prompt = f"""你是 Genesis 的自动验证进程 (The Auditor)。
任务：审查以下知识节点的内容是否依然合理、是否存在明显漏洞，或是否随技术演进而过时。

审查对象：
ID: {node_id}
标题: {title}
类型: {node['type']}
主要解决/关联: {node.get('resolves', '')}
标签: {node.get('tags', '')}

内容:
{content[:1500]}

[指令]
1. 仔细阅读节点内容，构建一个虚拟的"使用者视角"。
2. 寻找潜在的：死链、废弃的API、已经被现代框架淘汰的做法、明显的逻辑漏洞、缺失的前置条件。
3. 请严格输出以下 JSON 格式的审查报告（不要有任何额外文字）：
{{
    "status": "VALID" | "OBSOLETE" | "NEEDS_REVISION",
    "reason": "简短的理由说明",
    "suggested_confidence_delta": 0.0, // 如果 VALID 给个微小正数(如 0.05), OBSOLETE 给大负数(-0.3)
    "validation_status": "validated" | "unverified" | "outdated"
}}
"""
        messages = [Message(role=MessageRole.SYSTEM, content=prompt).to_dict()]
        
        try:
            response = await self.provider.chat(messages, stream=False)
            result_text = response.content.strip()
            
            # 提取 JSON
            import re
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                status = result.get('status')
                delta = float(result.get('suggested_confidence_delta', 0.0))
                v_status = result.get('validation_status', 'unverified')
                
                logger.info(f"    -> 审计结果: {status}, 理由: {result.get('reason')}")
                
                # 更新数据库
                if delta > 0:
                    self.vault.promote_node_confidence(node_id, boost=delta)
                elif delta < 0:
                    self.vault.decay_node_confidence(node_id, penalty=abs(delta))
                    
                import json as pyjson
                # 更新签名里的 validation_status
                row = self.vault._conn.execute("SELECT metadata_signature FROM knowledge_nodes WHERE node_id=?", (node_id,)).fetchone()
                sig = self.vault.parse_metadata_signature(row[0]) if row and row[0] else {}
                sig['validation_status'] = v_status
                
                self.vault._conn.execute(
                    "UPDATE knowledge_nodes SET metadata_signature = ?, last_verified_at = CURRENT_TIMESTAMP, verification_source = 'auditor_daemon' WHERE node_id = ?",
                    (pyjson.dumps(sig, ensure_ascii=False), node_id)
                )
                self.vault._conn.commit()
            else:
                logger.warning(f"    -> 解析验证结果失败: {result_text[:100]}")
                
        except Exception as e:
            logger.error(f"    -> 验证请求异常: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    verifier = KnowledgeVerifier(use_free_pool_only=True)
    asyncio.run(verifier.verify_cycle())
