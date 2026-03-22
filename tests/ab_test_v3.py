"""
Multi-G A/B 测试 V3：认知框架优化对照

对照组设计：
- 使用与 V2 完全相同的 5 题库 × 3 配置(3/5/7) × 2 轮
- 新增 "adaptive" 配置组（探针搜索自适应选择透镜数量）
- 测试完毕后自动加载 V2 结果，生成 V2 vs V3 对照表

新增指标（V3 独有）：
- diversity_bonus: 坍缩评分中多样性加分总和
- ntype_coverage: 所有条目引用的节点类型种数
- convergence_voids: 收敛度检测产生的软空洞数

运行：python tests/ab_test_v3.py
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
logger = logging.getLogger("ab_v3")

# ═══════════════════════════════════════════
#  题库（与 V2 完全一致，确保可对比）
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
#  配置组：固定 3/5/7 + 自适应
# ═══════════════════════════════════════════
LENS_CONFIGS = {
    "3-lens": ["ISTJ", "INTP", "ENFP"],
    "5-lens": ["ISTJ", "INTP", "ENFP", "INTJ", "ISTP"],
    "7-lens": ["ISTJ", "INTP", "ENFP", "INTJ", "ISTP", "ENTJ", "ISFJ"],
    "adaptive": None,  # 标记：不覆盖 _select_personas，让系统自适应
}

ROUNDS = 2  # 每配置每题跑 2 轮（5题×4配置×2轮=40 次调用）


def create_tools() -> ToolRegistry:
    tools = ToolRegistry()
    try:
        from genesis.tools.node_tools import SearchKnowledgeNodesTool
        tools.register(SearchKnowledgeNodesTool())
    except Exception as e:
        logger.error(f"Failed to register search tool: {e}")
    return tools


def analyze_blackboard(bb: Blackboard, collapse_results: list) -> dict:
    """从黑板提取细粒度指标（含 V3 新增的多样性指标）"""
    evidence = [e for e in bb.entries if isinstance(e, EvidenceEntry)]
    hypotheses = [e for e in bb.entries if isinstance(e, HypothesisEntry)]

    all_node_ids = []
    per_persona_nodes = {}
    all_ntypes = set()
    for e in evidence:
        nodes = e.evidence_node_ids or []
        all_node_ids.extend(nodes)
        per_persona_nodes.setdefault(e.persona, set()).update(nodes)

    unique_nodes = set(all_node_ids)
    total_refs = len(all_node_ids)

    if total_refs > 0:
        convergence = 1.0 - len(unique_nodes) / total_refs
    else:
        convergence = 0.0

    node_counter = Counter(all_node_ids)
    exclusive_nodes = sum(1 for nid, cnt in node_counter.items() if cnt == 1)

    directions = bb.get_all_suggested_search_directions()

    # V3 新增：从坍缩结果中提取多样性加分
    diversity_bonus_total = 0.0
    for cr in collapse_results:
        detail = cr.get("detail", "")
        # 从 detail 字符串中提取 div=X.X
        if "div=" in detail:
            try:
                div_part = detail.split("div=")[1].split("(")[0]
                diversity_bonus_total += float(div_part)
            except (IndexError, ValueError):
                pass

    # V3 新增：收敛度空洞数
    convergence_voids = sum(1 for v in bb.search_voids if v.get("source") == "convergence_detection")

    # V3 新增：ntype 覆盖（需要从 vault 查 brief，但这里近似用 collapse detail 中的 ntype 信息）
    ntype_count = 0
    for cr in collapse_results:
        detail = cr.get("detail", "")
        if "ntype=" in detail:
            try:
                nt_part = detail.split("ntype=")[1].split("(")[0]
                # 这是单条的加分，但我们要总 ntype 种数
            except (IndexError, ValueError):
                pass

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
        "diversity_bonus": round(diversity_bonus_total, 2),
        "convergence_voids": convergence_voids,
    }


async def run_single(prompt: str, personas: list | None, provider, tools) -> dict:
    """单次测试运行。personas=None 时使用自适应模式。"""
    loop = V4Loop(tools=tools, provider=provider, max_iterations=5)
    loop.user_input = prompt
    loop.inferred_signature = loop.vault.infer_metadata_signature(prompt)

    if personas is not None:
        loop._select_personas = lambda target_count=3: personas
    # personas=None → 不覆盖，使用自适应 _select_personas + _probe_knowledge_density

    loop.metrics = PerformanceMetrics()

    t0 = time.time()
    try:
        bb = await loop._run_lens_phase(prompt, step_callback=None)
    except Exception as e:
        logger.error(f"Run failed: {e}", exc_info=True)
        return {"status": "FAILED", "error": str(e)}
    elapsed = time.time() - t0

    collapse = bb.collapse(loop.vault)
    analysis = analyze_blackboard(bb, collapse)

    # 自适应模式下记录实际使用的透镜数
    actual_personas = set()
    for entry in bb.entries:
        actual_personas.add(entry.persona)

    return {
        "status": "OK",
        "elapsed": round(elapsed, 2),
        "tokens": loop.metrics.g_tokens,
        "top_score": round(collapse[0]["score"], 3) if collapse else 0,
        "score_spread": round(collapse[0]["score"] - collapse[-1]["score"], 3) if len(collapse) > 1 else 0,
        "actual_lenses": len(actual_personas),
        **analysis,
    }


def avg_metric(runs, key):
    ok = [r for r in runs if r["status"] == "OK"]
    if not ok:
        return 0
    return sum(r.get(key, 0) for r in ok) / len(ok)


def std_metric(runs, key):
    ok = [r for r in runs if r["status"] == "OK"]
    if len(ok) < 2:
        return 0
    m = avg_metric(runs, key)
    return math.sqrt(sum((r.get(key, 0) - m) ** 2 for r in ok) / (len(ok) - 1))


def load_v2_results() -> dict | None:
    """尝试加载 V2 结果作为基线"""
    path = os.path.join(os.path.dirname(__file__), "ab_test_v2_results.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


async def main():
    provider = ProviderRouter(config=config)
    tools = create_tools()

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
                if result["status"] == "OK":
                    logger.info(
                        f"  → {result['elapsed']:.1f}s | {result['tokens']} tok | "
                        f"{result['evidence']}ev/{result['entries']}ent | "
                        f"top={result['top_score']:.2f} | "
                        f"uniq={result['unique_nodes']} excl={result['exclusive_nodes']} "
                        f"conv={result['convergence']:.2f} div_bonus={result['diversity_bonus']:.1f}"
                    )
                await asyncio.sleep(1)
            all_results[task_kind][config_name] = runs

    # ═══════════════════════════════════════════
    #  V3 报告
    # ═══════════════════════════════════════════
    print("\n" + "=" * 120)
    print("  Multi-G A/B 测试 V3: 认知框架优化 (cognitive_frame + diversity bonus + adaptive)")
    print("=" * 120)

    for task_kind, configs in all_results.items():
        print(f"\n  ┌─ {task_kind} ─────────────────────────────────────────────────────────")
        print(f"  │  {TEST_PROMPTS[task_kind]['prompt'][:70]}...")
        print(f"  │")
        print(f"  │  {'配置':<10} {'T(s)':>6} {'Token':>8} {'条目':>4} {'证据':>4} {'Top分':>7} {'分差':>6} {'唯一':>5} {'收敛':>5} {'独占':>5} {'div+':>5} {'c_void':>6} {'实际镜':>6}")
        print(f"  │  {'─'*100}")

        for config_name in LENS_CONFIGS:
            runs = configs[config_name]
            ok_runs = [r for r in runs if r["status"] == "OK"]
            if not ok_runs:
                print(f"  │  {config_name:<10} ALL FAILED")
                continue

            print(
                f"  │  {config_name:<10} "
                f"{avg_metric(runs, 'elapsed'):>5.1f}s "
                f"{avg_metric(runs, 'tokens'):>8,.0f} "
                f"{avg_metric(runs, 'entries'):>4.1f} "
                f"{avg_metric(runs, 'evidence'):>4.1f} "
                f"{avg_metric(runs, 'top_score'):>7.2f} "
                f"{avg_metric(runs, 'score_spread'):>6.2f} "
                f"{avg_metric(runs, 'unique_nodes'):>5.1f} "
                f"{avg_metric(runs, 'convergence'):>5.2f} "
                f"{avg_metric(runs, 'exclusive_nodes'):>5.1f} "
                f"{avg_metric(runs, 'diversity_bonus'):>5.1f} "
                f"{avg_metric(runs, 'convergence_voids'):>6.1f} "
                f"{avg_metric(runs, 'actual_lenses'):>6.1f}"
            )

        print(f"  └{'─'*110}")

    # ═══════════════════════════════════════════
    #  跨题汇总
    # ═══════════════════════════════════════════
    print(f"\n{'='*120}")
    print("  跨题总汇总 (V3)")
    print(f"{'─'*120}")
    print(f"  {'配置':<10} {'Token':>8} {'证据率':>6} {'Top分':>7} {'唯一':>5} {'收敛':>5} {'独占':>5} {'div+':>5} {'c_void':>6}")
    print(f"  {'─'*80}")

    for config_name in LENS_CONFIGS:
        all_ok = []
        for task_kind in TEST_PROMPTS:
            all_ok.extend([r for r in all_results[task_kind][config_name] if r["status"] == "OK"])
        if not all_ok:
            continue
        n = len(all_ok)
        avg_tok = sum(r["tokens"] for r in all_ok) / n
        avg_ev_rate = sum(r["evidence"] / max(r["entries"], 1) for r in all_ok) / n
        avg_top = sum(r["top_score"] for r in all_ok) / n
        avg_uniq = sum(r["unique_nodes"] for r in all_ok) / n
        avg_conv = sum(r["convergence"] for r in all_ok) / n
        avg_excl = sum(r["exclusive_nodes"] for r in all_ok) / n
        avg_div = sum(r.get("diversity_bonus", 0) for r in all_ok) / n
        avg_cvoid = sum(r.get("convergence_voids", 0) for r in all_ok) / n
        print(
            f"  {config_name:<10} "
            f"{avg_tok:>8,.0f} "
            f"{avg_ev_rate:>5.0%} "
            f"{avg_top:>7.2f} "
            f"{avg_uniq:>5.1f} "
            f"{avg_conv:>5.2f} "
            f"{avg_excl:>5.1f} "
            f"{avg_div:>5.1f} "
            f"{avg_cvoid:>6.1f}"
        )

    # ═══════════════════════════════════════════
    #  V2 vs V3 对照表
    # ═══════════════════════════════════════════
    v2_data = load_v2_results()
    if v2_data:
        print(f"\n{'='*120}")
        print("  V2 vs V3 对照 (相同配置，相同题目)")
        print(f"{'─'*120}")
        print(f"  {'题目':<10} {'配置':<10} │ {'V2 Top分':>8} {'V3 Top分':>8} {'Δ':>6} │ {'V2 唯一':>7} {'V3 唯一':>7} {'Δ':>4} │ {'V2 收敛':>7} {'V3 收敛':>7} {'Δ':>6} │ {'V2 独占':>7} {'V3 独占':>7}")
        print(f"  {'─'*120}")

        for task_kind in TEST_PROMPTS:
            for config_name in ["3-lens", "5-lens", "7-lens"]:
                v2_runs = v2_data.get(task_kind, {}).get(config_name, [])
                v3_runs = all_results.get(task_kind, {}).get(config_name, [])

                v2_ok = [r for r in v2_runs if r.get("status") == "OK"]
                v3_ok = [r for r in v3_runs if r.get("status") == "OK"]

                if not v2_ok or not v3_ok:
                    continue

                def v2_avg(key): return sum(r.get(key, 0) for r in v2_ok) / len(v2_ok)
                def v3_avg(key): return sum(r.get(key, 0) for r in v3_ok) / len(v3_ok)

                v2_top = v2_avg("top_score")
                v3_top = v3_avg("top_score")
                v2_uniq = v2_avg("unique_nodes")
                v3_uniq = v3_avg("unique_nodes")
                v2_conv = v2_avg("convergence")
                v3_conv = v3_avg("convergence")
                v2_excl = v2_avg("exclusive_nodes")
                v3_excl = v3_avg("exclusive_nodes")

                top_delta = v3_top - v2_top
                uniq_delta = v3_uniq - v2_uniq
                conv_delta = v3_conv - v2_conv

                top_arrow = "▲" if top_delta > 0.05 else ("▼" if top_delta < -0.05 else "─")
                uniq_arrow = "▲" if uniq_delta > 0.3 else ("▼" if uniq_delta < -0.3 else "─")
                conv_arrow = "▼" if conv_delta < -0.03 else ("▲" if conv_delta > 0.03 else "─")  # 收敛度低更好

                print(
                    f"  {task_kind:<10} {config_name:<10} │ "
                    f"{v2_top:>8.2f} {v3_top:>8.2f} {top_arrow}{abs(top_delta):>+.2f} │ "
                    f"{v2_uniq:>7.1f} {v3_uniq:>7.1f} {uniq_arrow:>3} │ "
                    f"{v2_conv:>7.2f} {v3_conv:>7.2f} {conv_arrow}{abs(conv_delta):>+.2f} │ "
                    f"{v2_excl:>7.1f} {v3_excl:>7.1f}"
                )

        print(f"  {'─'*120}")
        print(f"  图例: ▲=V3更优  ▼=V3更差  ─=持平  (Top分/独占:越高越好, 收敛度:越低越好)")
    else:
        print(f"\n  ⚠️ 未找到 V2 结果文件 (tests/ab_test_v2_results.json)，跳过对照表")

    print(f"\n{'='*120}")

    # 保存原始数据
    output_path = os.path.join(os.path.dirname(__file__), "ab_test_v3_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  原始数据: {output_path}")
    print(f"{'='*120}")


if __name__ == "__main__":
    asyncio.run(main())
