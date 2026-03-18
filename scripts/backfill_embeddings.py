#!/usr/bin/env python3
"""
一次性迁移脚本：为知识库中所有缺少 embedding 的节点回填向量。
运行方式：python scripts/backfill_embeddings.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from genesis.v4.manager import NodeVault

def main():
    print("=" * 50)
    print("Genesis Embedding Backfill")
    print("=" * 50)
    
    vault = NodeVault()
    
    # 回填前统计
    before_count = vault._conn.execute(
        "SELECT COUNT(*) FROM knowledge_nodes WHERE embedding IS NOT NULL AND node_id NOT LIKE 'MEM_CONV%'"
    ).fetchone()[0]
    total_count = vault._conn.execute(
        "SELECT COUNT(*) FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'"
    ).fetchone()[0]
    
    print(f"\n回填前: {before_count}/{total_count} 节点有向量 ({before_count*100//max(total_count,1)}%)")
    print(f"VectorEngine ready: {vault.vector_engine.is_ready}")
    
    if not vault.vector_engine.is_ready:
        print("\n❌ VectorEngine 未就绪（可能缺少 sentence_transformers 或模型未下载）")
        sys.exit(1)
    
    print("\n开始回填...")
    result = vault.backfill_embeddings()
    
    # 回填后统计
    after_count = vault._conn.execute(
        "SELECT COUNT(*) FROM knowledge_nodes WHERE embedding IS NOT NULL AND node_id NOT LIKE 'MEM_CONV%'"
    ).fetchone()[0]
    
    print(f"\n{'=' * 50}")
    print(f"回填结果:")
    print(f"  待处理: {result['total_missing']}")
    print(f"  成功:   {result['success']}")
    print(f"  失败:   {result['failed']}")
    print(f"  跳过:   {result['skipped']}")
    print(f"\n回填后: {after_count}/{total_count} 节点有向量 ({after_count*100//max(total_count,1)}%)")
    print(f"语义搜索覆盖率: {before_count*100//max(total_count,1)}% → {after_count*100//max(total_count,1)}%")
    print("=" * 50)

if __name__ == "__main__":
    main()
