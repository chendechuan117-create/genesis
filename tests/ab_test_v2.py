"""
Multi-G A/B 测试 V2：多题库 × 多轮次 × 多配置

改进点：
1. 5 个不同 task_kind 的测试题（覆盖知识库的不同区域）
2. 每个配置跑 3 轮取平均 + 标准差
3. 新增"信息多样性"指标：不同透镜引用的独特节点数
4. 新增"收敛度"指标：透镜间引用节点的重叠率

运行：python tests/ab_test_v2.py
"""

import sys, os, time, json, asyncio, logging, math
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesis.core.config import config
from genesis.core.registry import ToolRegistry
from genesis.core.provider_manager import ProviderRouter
from genesis.core.base import PerformanceMetrics
from genesis.v4.loop import V4Loop
from genesis.v4.blackboard import Blackboard, EvidenceEntry, HypothesisEntry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ab_v2")

# ═══════════════════════════════════════════
#  题库：5 种 task_kind，难度各异
# ═══════════════════════════════════════════
TEST_PROMPTS = {
    "debug": {
        "prompt": "Genesis 的 discord_bot.py 最近偶尔出现消息延迟 5-10 秒的问题，但日志没有明显的错误输出。我怀疑是 event loop 阻塞或者 provider failover 导致的。请帮我诊断。",
        "expected_topics": ["proxy", "network", "asyncio", "timeout"],
    },
    "refactor": {
        "prompt": "Genesis 的 provider.py 里有多层 JSON 修复逻辑和 SSE 解析，代码比较脆弱。请分析重构方案，减少耦合度。",
        "expected_topics": ["provider", "json", "sse", "parse", "httpx"],
    },
    "optimize": {
        "prompt": "NodeVault 的 search_knowledge 方法在节点数 >500 时变慢。请分析性能瓶颈，提出优化方案。",
        "expected_topics": ["vector", "search", "sqlite", "embedding", "index"],
    },
    "design": {
        "prompt": "我想给 Genesis 添加一个多模态能力：让 Op 能处理用户上传的截图（OCR + 视觉理解）。请从架构角度分析需要修改哪些模块。",
        "expected_topics": ["image", "multimodal", "tool", "vision", "base64"],
    },
    "build": {
        "prompt": "请帮我为 Genesis 的后台守护进程（scavenger, fermentor, verifier）设计一个健康监控面板，显示各进程的状态、最近执行结果和知识库增长趋势。",
        "expected_topics": ["daemon", "health", "monitor", "scavenger", "fermentor"],
    },
}

# ═══════════════════════════════════════════
#  测试的透镜配置（基于前轮发现，聚焦关键拐点）
# ═══════════════════════════════════════════
LENS_CONFIGS = {
    "3-lens": ["ISTJ", "INTP", "ENFP"],
    "5-lens": ["ISTJ", "INTP", "ENFP", "INTJ", "ISTP"],
    "7-lens": ["ISTJ", "INTP", "ENFP", "INTJ", "ISTP", "ENTJ", "ISFJ"],
}

ROUNDS = 3  # 每个配置每题跑 3 轮


def create_tools() -> ToolRegistry:
    tools = ToolRegistry()
    try:
        from genesis.tools.node_tools import SearchKnowledgeNodesTool
        tools.register(SearchKnowledgeNodesTool())
    except Exception as e:
        logger.error(f"Failed to register search tool: {e}")
    return tools


def analyze_blackboard(bb: Blackboard) -> dict:
    """从黑板提取细粒度指标"""
    evidence = [e for e in bb.entries if isinstance(e, EvidenceEntry)]
    hypotheses = [e for e in bb.entries if isinstance(e, HypothesisEntry)]

    # 信息多样性：所有透镜引用的独特节点 ID 集合
    all_node_ids = []
    per_persona_nodes = {}
    for e in evidence:
        nodes = e.evidence_node_ids or []
        all_node_ids.extend(nodes)
        per_persona_nodes.setdefault(e.persona, set()).update(nodes)

    unique_nodes = set(all_node_ids)
    total_refs = len(all_node_ids)

    # 收敛度：节点引用的重复率 (高 = 透镜们找到了相同的东西)
    if total_refs > 0:
        convergence = 1.0 - len(unique_nodes) / total_refs
    else:
        convergence = 0.0

    # 透镜间独占节点数（只被一个透镜引用的节点）
    node_counter = Counter(all_node_ids)
    exclusive_nodes = sum(1 for nid, cnt in node_counter.items() if cnt == 1)

    # 搜索方向数（假设型条目提出的新方向）
    directions = bb.get_all_suggested_search_directions()

    return {
        "entries": bb.entry_count,
        "evidence": len(evidence),
        "hypotheses": len(hypotheses),
        "voids": len(bb.search_voids),
        "unique_nodes": len(unique_nodes),
        "total_refs": total_refs,
        "convergence": round(convergence, 3),
        "exclusive_nodes": exclusive_nodes,
        "directions": len(directions),
    }


async def run_single(prompt: str, personas: list, provider, tools) -> dict:
    """单次测试运行"""
    loop = V4Loop(tools=tools, provider=provider, max_iterations=5)
    loop.user_input = prompt
    loop.inferred_signature = loop.vault.infer_metadata_signature(prompt)
    loop._select_personas = lambda target_count=3: personas
    loop.metrics = PerformanceMetrics()

    t0 = time.time()
    try:
        bb = await loop._run_lens_phase(prompt, step_callback=None)
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}
    elapsed = time.time() - t0

    collapse = bb.collapse(loop.vault)
    analysis = analyze_blackboard(bb)

    return {
        "status": "OK",
        "elapsed": round(elapsed, 2),
        "tokens": loop.metrics.g_tokens,
        "top_score": round(collapse[0]["score"], 3) if collapse else 0,
        "score_spread": round(collapse[0]["score"] - collapse[-1]["score"], 3) if len(collapse) > 1 else 0,
        **analysis,
    }


async def main():
    provider = ProviderRouter(config=config)
    tools = create_tools()

    # 存储所有结果：results[task_kind][config_name] = [run1, run2, run3]
    all_results = {}

    total_runs = len(TEST_PROMPTS) * len(LENS_CONFIGS) * ROUNDS
    run_idx = 0

    for task_kind, task_info in TEST_PROMPTS.items():
        all_results[task_kind] = {}
        for config_name, personas in LENS_CONFIGS.items():
            runs = []
            for round_num in range(ROUNDS):
                run_idx += 1
                logger.info(f"[{run_idx}/{total_runs}] {task_kind} × {config_name} × round {round_num+1}")
                result = await run_single(task_info["prompt"], personas, provider, tools)
                runs.append(result)
                await asyncio.sleep(1)  # rate limit buffer
            all_results[task_kind][config_name] = runs

    # ═══════════════════════════════════════════
    #  汇总报告
    # ═══════════════════════════════════════════
    print("\n" + "=" * 100)
    print("  Multi-G A/B 测试 V2: 多题库 × 多轮次")
    print("=" * 100)

    # 按题目汇总
    for task_kind, configs in all_results.items():
        print(f"\n  ┌─ 题目: {task_kind} ─────────────────────────────────────────────────")
        print(f"  │  {TEST_PROMPTS[task_kind]['prompt'][:70]}...")
        print(f"  │")
        print(f"  │  {'配置':<8} {'T(s)':>6} {'Token':>8} {'条目':>4} {'证据':>4} {'Top分':>7} {'分差':>6} {'唯一节点':>8} {'收敛度':>6} {'独占节点':>8}")
        print(f"  │  {'─'*80}")

        for config_name, runs in configs.items():
            ok_runs = [r for r in runs if r["status"] == "OK"]
            if not ok_runs:
                print(f"  │  {config_name:<8} ALL FAILED")
                continue

            def avg(key): return sum(r[key] for r in ok_runs) / len(ok_runs)
            def std(key):
                m = avg(key)
                return math.sqrt(sum((r[key] - m) ** 2 for r in ok_runs) / max(len(ok_runs) - 1, 1))

            print(
                f"  │  {config_name:<8} "
                f"{avg('elapsed'):>5.1f}s "
                f"{avg('tokens'):>8,.0f} "
                f"{avg('entries'):>4.1f} "
                f"{avg('evidence'):>4.1f} "
                f"{avg('top_score'):>7.2f} "
                f"{avg('score_spread'):>6.2f} "
                f"{avg('unique_nodes'):>8.1f} "
                f"{avg('convergence'):>6.2f} "
                f"{avg('exclusive_nodes'):>8.1f}"
            )
            # 标准差行
            print(
                f"  │  {'  ±std':<8} "
                f"{std('elapsed'):>5.1f}  "
                f"{std('tokens'):>8,.0f} "
                f"{std('entries'):>4.1f} "
                f"{std('evidence'):>4.1f} "
                f"{std('top_score'):>7.2f} "
                f"{std('score_spread'):>6.2f} "
                f"{std('unique_nodes'):>8.1f} "
                f"{std('convergence'):>6.2f} "
                f"{std('exclusive_nodes'):>8.1f}"
            )

        print(f"  └{'─'*90}")

    # 跨题汇总
    print(f"\n{'='*100}")
    print("  跨题总汇总 (所有题目平均)")
    print(f"{'─'*100}")
    print(f"  {'配置':<8} {'Token':>8} {'证据率':>6} {'Top分':>7} {'唯一节点':>8} {'收敛度':>6} {'独占节点':>8}")
    print(f"  {'─'*80}")

    for config_name in LENS_CONFIGS:
        all_ok = []
        for task_kind in TEST_PROMPTS:
            all_ok.extend([r for r in all_results[task_kind][config_name] if r["status"] == "OK"])
        if not all_ok:
            continue
        avg_tok = sum(r["tokens"] for r in all_ok) / len(all_ok)
        avg_ev_rate = sum(r["evidence"] / max(r["entries"], 1) for r in all_ok) / len(all_ok)
        avg_top = sum(r["top_score"] for r in all_ok) / len(all_ok)
        avg_uniq = sum(r["unique_nodes"] for r in all_ok) / len(all_ok)
        avg_conv = sum(r["convergence"] for r in all_ok) / len(all_ok)
        avg_excl = sum(r["exclusive_nodes"] for r in all_ok) / len(all_ok)
        print(
            f"  {config_name:<8} "
            f"{avg_tok:>8,.0f} "
            f"{avg_ev_rate:>5.0%} "
            f"{avg_top:>7.2f} "
            f"{avg_uniq:>8.1f} "
            f"{avg_conv:>6.2f} "
            f"{avg_excl:>8.1f}"
        )

    print(f"\n{'='*100}")

    # 保存原始数据
    output_path = os.path.join(os.path.dirname(__file__), "ab_test_v2_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  原始数据: {output_path}")
    print(f"{'='*100}")


if __name__ == "__main__":
    asyncio.run(main())
