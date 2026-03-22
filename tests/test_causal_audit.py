"""
因果闭环审计验证测试
覆盖本次修改的所有关键路径：
  1. cache_stats (heartbeat 输出缓存命中率)
  2. token_efficiency (滑动窗口)
  3. provider_stats (类级计数器)
  4. kb_entropy (知识库熵增)
  5. persona_stats + dynamic swap (task_kind 细分统计)
  6. learned_markers (C-Phase 盲区自动学习)
"""

import asyncio
import sys
import os
import json
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("test_causal_audit")

# 测试问题设计：
# Q1: debug 类型 → persona 选 ISTJ/INTP/INTJ → 触发搜索 + C-Phase
# Q2: refactor 类型 → persona 选 INTP/ENFP/ENTJ → 不同 persona 组合
# Q3: deploy 类型 → 测试 provider_stats 累积 + token_efficiency 窗口
# Q4: 重复前缀 → 测试 cache hit rate 提升
# Q5: 新领域 → 测试 learned_markers + kb_entropy

TEST_QUESTIONS = [
    {
        "label": "Q1_debug",
        "input": "帮我调试一个 Python asyncio 的问题：我的协程在 await gather 时偶尔会卡死，可能是什么原因？",
        "expect_task_kind": "debug",
        "covers": ["persona_stats", "cache_stats", "provider_stats", "token_efficiency"],
    },
    {
        "label": "Q2_refactor",
        "input": "帮我重构一下这段代码的错误处理逻辑，让它更健壮：try/except 包了太多层，异常类型太笼统",
        "expect_task_kind": "refactor",
        "covers": ["persona_stats(different set)", "cache_stats(warm)", "token_efficiency(window grows)"],
    },
    {
        "label": "Q3_deploy",
        "input": "/quick 检查一下我的 Docker 容器日志，看看有没有 OOM killer 的痕迹",
        "expect_task_kind": "deploy",
        "covers": ["persona_stats(third set)", "provider_stats(accumulate)", "kb_entropy"],
    },
]


async def run_single_test(agent, q: dict, idx: int):
    """运行单个测试问题"""
    label = q["label"]
    logger.info(f"\n{'='*60}")
    logger.info(f"TEST {idx+1}/{len(TEST_QUESTIONS)}: [{label}]")
    logger.info(f"Input: {q['input'][:80]}...")
    logger.info(f"Expected task_kind: {q.get('expect_task_kind', '?')}")
    logger.info(f"Covers: {q['covers']}")
    logger.info(f"{'='*60}")
    
    start = time.time()
    try:
        result = await agent.process(q["input"])
        elapsed = time.time() - start
        metrics = result["metrics"]
        response = result["response"][:200]
        
        logger.info(f"\n--- RESULT [{label}] ({elapsed:.1f}s) ---")
        logger.info(f"Response preview: {response}...")
        logger.info(f"Tokens: in={metrics.input_tokens} out={metrics.output_tokens} total={metrics.total_tokens}")
        logger.info(f"Cache: hit={metrics.prompt_cache_hit_tokens} rate={metrics.prompt_cache_hit_tokens/max(metrics.input_tokens,1)*100:.1f}%")
        logger.info(f"Phases: G={metrics.g_tokens}t Op={metrics.op_tokens}t C={metrics.c_tokens}t")
        logger.info(f"Success: {metrics.success}")
        
        return {
            "label": label,
            "success": metrics.success,
            "elapsed": elapsed,
            "input_tokens": metrics.input_tokens,
            "output_tokens": metrics.output_tokens,
            "cache_hit_tokens": metrics.prompt_cache_hit_tokens,
            "cache_hit_rate": round(metrics.prompt_cache_hit_tokens / max(metrics.input_tokens, 1), 3),
            "total_tokens": metrics.total_tokens,
        }
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"FAILED [{label}] ({elapsed:.1f}s): {e}")
        import traceback
        traceback.print_exc()
        return {"label": label, "success": False, "error": str(e), "elapsed": elapsed}


async def main():
    from factory import create_agent
    
    logger.info("Creating Genesis V4 agent...")
    agent = create_agent()
    agent.c_phase_blocking = True  # 等 C-Phase 完成再返回
    
    # 采集基线
    from genesis.core.provider import NativeHTTPProvider
    from genesis.v4.loop import V4Loop
    from genesis.v4.blackboard import Blackboard
    
    logger.info(f"Baseline provider_stats: {NativeHTTPProvider.get_provider_stats()}")
    logger.info(f"Baseline token_efficiency: {V4Loop.get_token_efficiency_stats()}")
    logger.info(f"Baseline persona_stats: {Blackboard.get_persona_stats()}")
    logger.info(f"Baseline persona_task_stats keys: {list(Blackboard._persona_task_stats.keys())}")
    
    # 运行测试
    results = []
    for idx, q in enumerate(TEST_QUESTIONS):
        r = await run_single_test(agent, q, idx)
        results.append(r)
        # 每个问题之间短暂等待，模拟真实使用
        if idx < len(TEST_QUESTIONS) - 1:
            await asyncio.sleep(2)
    
    # 采集最终状态
    logger.info(f"\n{'='*60}")
    logger.info("FINAL DIAGNOSTICS")
    logger.info(f"{'='*60}")
    
    final_provider = NativeHTTPProvider.get_provider_stats()
    final_token = V4Loop.get_token_efficiency_stats()
    final_persona = Blackboard.get_persona_stats()
    final_task_stats = dict(Blackboard._persona_task_stats)
    
    logger.info(f"provider_stats: {json.dumps(final_provider, indent=2)}")
    logger.info(f"token_efficiency: {json.dumps(final_token, indent=2) if final_token else 'None'}")
    logger.info(f"persona_stats: {json.dumps(final_persona, indent=2)}")
    logger.info(f"persona_task_stats: {json.dumps(final_task_stats, indent=2)}")
    
    # kb_entropy
    from genesis.v4.manager import NodeVault
    vault = NodeVault()
    kb = vault.get_kb_entropy()
    logger.info(f"kb_entropy: {json.dumps(kb, indent=2) if kb else 'None'}")
    
    # learned_markers
    learned = getattr(vault, '_learned_markers', {})
    logger.info(f"learned_markers: {len(learned)} dims, total {sum(len(v) for v in learned.values())} markers")
    for k, v in learned.items():
        logger.info(f"  {k}: {v}")
    
    # 汇总
    logger.info(f"\n{'='*60}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*60}")
    total_cache_hit = sum(r.get("cache_hit_tokens", 0) for r in results)
    total_input = sum(r.get("input_tokens", 0) for r in results)
    for r in results:
        cache_pct = f"{r.get('cache_hit_rate', 0)*100:.1f}%" if 'cache_hit_rate' in r else "N/A"
        status = "✓" if r.get("success") else "✗"
        logger.info(f"  {status} {r['label']}: {r.get('elapsed', 0):.1f}s, "
                    f"tokens={r.get('total_tokens', '?')}, cache={cache_pct}")
    
    if total_input > 0:
        logger.info(f"\nOverall cache hit rate: {total_cache_hit}/{total_input} = {total_cache_hit/total_input*100:.1f}%")
    
    passed = sum(1 for r in results if r.get("success"))
    logger.info(f"\nPassed: {passed}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
