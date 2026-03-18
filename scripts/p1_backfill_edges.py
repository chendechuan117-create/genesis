#!/usr/bin/env python3
"""
一次性图谱边回填脚本 (P1)
逻辑:
1. 找出所有孤儿节点 (不在 node_edges 中的节点)
2. 利用 LLM (Fermentor的逻辑) 对这些孤儿节点进行向量召回
3. 让 LLM 自动建立 REQUIRES/RESOLVES/RELATED_TO 边
"""
import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from genesis.core.config import ConfigManager
from genesis.core.provider_manager import ProviderRouter
from genesis.core.base import Message, MessageRole
from genesis.v4.manager import NodeVault
from genesis.tools.node_tools import CreateNodeEdgeTool
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("backfill")

async def run_backfill():
    print("=" * 50)
    print("Genesis Graph Edge Backfill (P1)")
    print("=" * 50)

    vault = NodeVault()
    if not vault.vector_engine.is_ready:
        print("❌ VectorEngine not ready!")
        return

    # 1. 查找孤儿节点 (Orphan Nodes)
    # 不在边表里，且不是对话记录，且是具备业务意义的类型
    query = """
    SELECT node_id, type, title, resolves, tags 
    FROM knowledge_nodes 
    WHERE node_id NOT LIKE 'MEM_CONV%' 
      AND node_id NOT IN (SELECT source_id FROM node_edges)
      AND node_id NOT IN (SELECT target_id FROM node_edges)
      AND type IN ('LESSON', 'CONTEXT', 'ASSET', 'TOOL')
    ORDER BY created_at DESC
    """
    orphans = [dict(r) for r in vault._conn.execute(query).fetchall()]
    
    print(f"找到 {len(orphans)} 个高质量孤儿节点待处理。")
    if not orphans:
        return

    # 2. 初始化 LLM 
    import genesis.providers
    from genesis.providers.cloud_providers import _build_qianfan, _build_zhipu, _build_siliconflow, _build_deepseek
    config = ConfigManager()
    
    # 强制注入 .env 里的 KEY
    qianfan_key = os.environ.get("QIANFAN_API_KEY")
    zhipu_key = os.environ.get("ZHIPU_API_KEY")
    sf_key = os.environ.get("SILICONFLOW_API_KEY")
    ds_key = os.environ.get("DEEPSEEK_API_KEY")
    
    provider = None
    if sf_key:
        config._config.siliconflow_api_key = sf_key
        provider = _build_siliconflow(config)
        print("选用 LLM 路由: siliconflow")
    elif zhipu_key:
        config._config.zhipu_api_key = zhipu_key
        provider = _build_zhipu(config)
        print("选用 LLM 路由: zhipu")
    elif ds_key:
        config._config.deepseek_api_key = ds_key
        provider = _build_deepseek(config)
        print("选用 LLM 路由: deepseek")
    else:
        print("未找到免费 LLM 兜底，请在 .env 配置可用 API KEY")
        return
    
    edge_tool = CreateNodeEdgeTool()
    edge_tool.vault = vault  # 共享 vault 避免重复加载模型
    schema = [edge_tool.to_schema()]
    
    # 3. 逐个进行关联推断
    edges_created = 0
    # 为了避免跑太久，我们这里做个批量，或者每次跑最多处理 30 个
    batch = orphans[:30]
    print(f"\n[开始处理前 30 个孤儿节点...]")
    
    for i, node in enumerate(batch):
        node_id = node['node_id']
        title = node['title']
        ntype = node['type']
        
        print(f"[{i+1}/{len(batch)}] 正在分析: {node_id} - {title}")
        
        # 使用向量搜索召回最相似的 5 个节点
        search_results = []
        vec = vault.vector_engine.encode(f"{title} {node.get('tags','')} {node.get('resolves','')}")
        if vec:
            sim_ids = vault.vector_engine.search(" ".join([title, str(node.get('resolves',''))]), top_k=6)
            for sid, score in sim_ids:
                if sid != node_id:
                    cand = vault._conn.execute("SELECT node_id, type, title FROM knowledge_nodes WHERE node_id=?", (sid,)).fetchone()
                    if cand:
                        search_results.append(dict(cand))
                        
        if not search_results:
            print("  -> 无相似候选，跳过")
            continue
            
        # 组装 prompt
        prompt = f"""你是 Genesis 的自动发酵进程 (The Weaver)。
任务：分析目标节点与候选节点之间是否存在明确的逻辑关联。

目标节点 (孤儿):
ID: {node_id}
类型: {ntype}
标题: {title}

候选节点:
"""
        for j, cand in enumerate(search_results, 1):
            prompt += f"--- 候选 {j} ---\nID: {cand['node_id']}\n类型: {cand['type']}\n标题: {cand['title']}\n\n"
            
        prompt += """
判断规则：
如果目标节点与某个候选节点有强烈的逻辑关系，请**必须**使用 `create_node_edge` 工具建立连线。
关系类型仅限：
- `REQUIRES`: 目标执行强制依赖候选节点 (比如 TOOL 依赖 CONTEXT，或者 LESSON 依赖 TOOL)
- `RESOLVES`: 目标解决了候选节点提出的问题，或者反之
- `RELATED_TO`: 强相关背景概念 (如同属一个框架，同属一个报错类别)
- `LOCATED_AT`: 物理位置关系

你可以调用多次 `create_node_edge` 工具。如果没有明确关系，不要强行连线。
请直接输出工具调用。不要输出多余废话。
"""
        messages = [Message(role=MessageRole.SYSTEM, content=prompt).to_dict()]
        
        try:
            response = await provider.chat(messages, tools=schema, stream=False)
            if response.tool_calls:
                for tc in response.tool_calls:
                    if tc.name == "create_node_edge":
                        args = tc.arguments
                        if isinstance(args, str):
                            args = json.loads(args)
                        res = await edge_tool.execute(**args)
                        print(f"  -> {res}")
                        edges_created += 1
            else:
                print("  -> LLM 认为无关联")
        except Exception as e:
            print(f"  -> 请求失败: {e}")

    print("=" * 50)
    print(f"处理完成！本次运行新建了 {edges_created} 条图谱边。")
    print("你可以多次运行此脚本，直到孤儿节点全部连入网络。")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(run_backfill())
