"""
Multi-G A/B 测试：1 / 3 / 5 个透镜的性价比对比

运行方式：
  python tests/ab_test_multi_g.py

测试流程：
  1. 用同一个复杂任务，分别用 1、3、5 个透镜跑 lens phase
  2. 收集：耗时、token 消耗、黑板条目数、证据/假设比、搜索空洞数、坍缩分差
  3. 输出对比表
"""

import sys
import os
import time
import json
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesis.core.config import config
from genesis.core.registry import ToolRegistry
from genesis.core.provider_manager import ProviderRouter
from genesis.core.base import PerformanceMetrics
from genesis.v4.loop import V4Loop
from genesis.v4.blackboard import Blackboard, EvidenceEntry, HypothesisEntry
from genesis.v4.manager import PERSONA_ACTIVATION_MAP, PERSONA_LENS_PROFILES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ab_test")

# ─── 测试用的复杂任务 ───
TEST_PROMPT = """Genesis 的 discord_bot.py 最近偶尔出现消息延迟 5-10 秒的问题，
但日志没有明显的错误输出。我怀疑是 event loop 阻塞或者 provider failover 导致的。
请帮我诊断这个问题，找到根因并提出修复方案。"""

# ─── 要测试的透镜配置 ───
LENS_CONFIGS = {
    "1-lens": ["ISTJ"],
    "3-lens": ["ISTJ", "INTP", "ENFP"],
    "5-lens": ["ISTJ", "INTP", "ENFP", "INTJ", "ISTP"],
    "7-lens": ["ISTJ", "INTP", "ENFP", "INTJ", "ISTP", "ENTJ", "ISFJ"],
    "9-lens": ["ISTJ", "INTP", "ENFP", "INTJ", "ISTP", "ENTJ", "ISFJ", "ESTJ", "INFJ"],
}


def create_minimal_tools() -> ToolRegistry:
    """只注册 search_knowledge_nodes，足够透镜使用"""
    tools = ToolRegistry()
    try:
        from genesis.tools.node_tools import SearchKnowledgeNodesTool
        tools.register(SearchKnowledgeNodesTool())
    except Exception as e:
        logger.error(f"Failed to register search tool: {e}")
    return tools


async def run_lens_test(config_name: str, personas: list, provider: ProviderRouter, tools: ToolRegistry) -> dict:
    """运行单次透镜测试，返回指标"""
    logger.info(f"\n{'='*60}")
    logger.info(f"  A/B 测试: {config_name} ({', '.join(personas)})")
    logger.info(f"{'='*60}")

    loop = V4Loop(
        tools=tools,
        provider=provider,
        max_iterations=5,  # 只跑 lens phase，不需要完整循环
    )

    # 初始化必要状态
    loop.user_input = TEST_PROMPT
    loop.inferred_signature = loop.vault.infer_metadata_signature(TEST_PROMPT)

    # 猴子补丁：覆盖 _select_personas 让它返回我们要测试的人格列表
    loop._select_personas = lambda target_count=3: personas

    # 重置 metrics
    loop.metrics = PerformanceMetrics()

    t0 = time.time()

    try:
        blackboard = await loop._run_lens_phase(TEST_PROMPT, step_callback=None)
    except Exception as e:
        logger.error(f"  ❌ Lens phase failed: {e}", exc_info=True)
        return {
            "config": config_name,
            "personas": personas,
            "status": "FAILED",
            "error": str(e),
        }

    elapsed = time.time() - t0

    # 分析黑板
    evidence_count = sum(1 for e in blackboard.entries if isinstance(e, EvidenceEntry))
    hypothesis_count = sum(1 for e in blackboard.entries if isinstance(e, HypothesisEntry))
    void_count = len(blackboard.search_voids)
    directions = blackboard.get_all_suggested_search_directions()

    # 坍缩
    collapse = blackboard.collapse(loop.vault)
    top_score = collapse[0]["score"] if collapse else 0
    bottom_score = collapse[-1]["score"] if collapse else 0
    score_spread = top_score - bottom_score

    # Token 消耗
    g_tokens = loop.metrics.g_tokens

    result = {
        "config": config_name,
        "personas": personas,
        "status": "OK",
        "elapsed_sec": round(elapsed, 2),
        "g_tokens": g_tokens,
        "total_entries": blackboard.entry_count,
        "evidence_entries": evidence_count,
        "hypothesis_entries": hypothesis_count,
        "search_voids": void_count,
        "suggested_directions": len(directions),
        "top_score": round(top_score, 3),
        "bottom_score": round(bottom_score, 3),
        "score_spread": round(score_spread, 3),
        "collapse_ranking": [
            f"{item['entry'].persona}({item['entry'].entry_type[0].upper()})={item['score']:.3f}"
            for item in collapse
        ],
        "board_preview": blackboard.render_for_g()[:500],
    }

    logger.info(f"  ✅ 完成: {elapsed:.1f}s, {g_tokens}t, {blackboard.entry_count} entries")
    return result


async def main():
    logger.info("=" * 60)
    logger.info("  Multi-G A/B 测试: 1 vs 3 vs 5 透镜")
    logger.info("=" * 60)
    logger.info(f"  测试任务: {TEST_PROMPT[:80]}...")
    logger.info("")

    provider = ProviderRouter(config=config)
    tools = create_minimal_tools()

    results = []

    for config_name, personas in LENS_CONFIGS.items():
        result = await run_lens_test(config_name, personas, provider, tools)
        results.append(result)
        # 冷却 2 秒，避免触发 rate limit
        await asyncio.sleep(2)

    # ─── 汇总报告 ───
    print("\n")
    print("=" * 80)
    print("  Multi-G A/B 测试结果")
    print("=" * 80)
    print(f"  测试任务: {TEST_PROMPT[:60]}...")
    print("-" * 80)
    print(f"{'配置':<12} {'状态':<8} {'耗时(s)':<10} {'Token':<10} {'条目':<6} {'证据':<6} {'假设':<6} {'空洞':<6} {'Top分':<8} {'分差':<8}")
    print("-" * 80)

    for r in results:
        if r["status"] != "OK":
            print(f"{r['config']:<12} {'FAIL':<8} {'-':<10} {'-':<10} {'-':<6} {'-':<6} {'-':<6} {'-':<6} {'-':<8} {'-':<8}")
            continue
        print(
            f"{r['config']:<12} "
            f"{'OK':<8} "
            f"{r['elapsed_sec']:<10} "
            f"{r['g_tokens']:<10} "
            f"{r['total_entries']:<6} "
            f"{r['evidence_entries']:<6} "
            f"{r['hypothesis_entries']:<6} "
            f"{r['search_voids']:<6} "
            f"{r['top_score']:<8} "
            f"{r['score_spread']:<8}"
        )

    print("-" * 80)

    # 性价比分析
    ok_results = [r for r in results if r["status"] == "OK"]
    if len(ok_results) >= 2:
        print("\n  [性价比分析]")
        baseline = ok_results[0]  # 1-lens 作为基线
        for r in ok_results[1:]:
            token_ratio = r["g_tokens"] / max(baseline["g_tokens"], 1)
            entry_ratio = r["total_entries"] / max(baseline["total_entries"], 1)
            evidence_ratio = r["evidence_entries"] / max(baseline["evidence_entries"], 1)
            spread_ratio = r["score_spread"] / max(baseline["score_spread"], 0.001)
            print(f"  {r['config']} vs {baseline['config']}:")
            print(f"    Token 倍数: {token_ratio:.1f}x | 条目倍数: {entry_ratio:.1f}x | 证据倍数: {evidence_ratio:.1f}x | 分差倍数: {spread_ratio:.1f}x")
            efficiency = (entry_ratio + evidence_ratio) / (2 * token_ratio)
            print(f"    信息效率 (条目+证据增益 / Token消耗): {efficiency:.2f} (>1.0 = 有性价比)")
        print("")

    # 坍缩排名详情
    print("  [各配置坍缩排名]")
    for r in ok_results:
        print(f"  {r['config']}: {' > '.join(r['collapse_ranking'])}")

    print("\n  [黑板内容预览]")
    for r in ok_results:
        print(f"\n  --- {r['config']} ---")
        print(f"  {r['board_preview'][:300]}")

    print("\n" + "=" * 80)

    # 保存原始数据
    output_path = os.path.join(os.path.dirname(__file__), "ab_test_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  原始数据已保存: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
