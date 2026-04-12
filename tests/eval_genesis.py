"""
Multi-G 认知基准：Genesis 答卷生成器

运行 Genesis Multi-G 对 5 道考题，捕获每个透镜的完整输出，
生成可读的 Genesis 答卷，供与空白 Claude 对比。

运行：python tests/eval_genesis.py
输出：tests/eval_genesis_answers.md
"""

import sys, os, json, asyncio, logging, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesis.core.config import config
from genesis.core.registry import ToolRegistry
from genesis.core.provider_manager import ProviderRouter
from genesis.core.base import PerformanceMetrics
from genesis.v4.loop import V4Loop
from genesis.v4.blackboard import Blackboard, EvidenceEntry, HypothesisEntry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("eval")

# 5 道考题（与 eval_exam.md 一致）
EXAM = {
    "Q1_network": "Genesis 运行在一台 Linux 服务器上，通过 SOCKS5 代理访问 DeepSeek API 和 Discord API。最近出现间歇性的消息延迟（5-10 秒），但日志中没有明显错误。可能的原因是什么？你会怎么排查？",
    "Q2_search_perf": "NodeVault 使用 SQLite 存储知识节点，向量搜索用本地 embedding 模型（BAAI/bge-small-zh-v1.5）。当节点数超过 500 时搜索明显变慢。瓶颈可能在哪？如何优化？",
    "Q3_provider": "Genesis 需要支持多个 LLM provider（DeepSeek、OpenAI 兼容接口等），通过 HTTP 调用。如何设计一个健壮的 provider 容错机制？考虑：failover、超时、SSE 流式响应解析、JSON 修复。",
    "Q4_knowledge_quality": "Genesis 的 C 阶段会自动提取经验教训（LESSON 节点）写入知识库。时间一长，知识库可能出现：重复、过时、矛盾的节点。如何设计一个知识质量控制机制？",
    "Q5_multi_perspective": "Genesis 目前是单 agent 循环。如果要让 G 阶段从多个认知视角分析问题（类似让不同思维风格的人同时思考同一个问题），你会怎么设计这个多视角机制？考虑：如何让不同视角真正产生差异而不是重复？如何合并多个视角的结论？",
}

# 固定 5-lens（V3 测试中表现最佳的配置）
PERSONAS = ["ISTJ", "INTP", "ENFP", "INTJ", "ISTP"]


def create_tools() -> ToolRegistry:
    tools = ToolRegistry()
    from genesis.tools.node_tools import SearchKnowledgeNodesTool
    tools.register(SearchKnowledgeNodesTool())
    return tools


async def run_exam_question(qid: str, prompt: str, provider, tools) -> dict:
    """运行单道考题，返回完整的透镜输出"""
    loop = V4Loop(tools=tools, provider=provider, max_iterations=5)
    loop.user_input = prompt
    loop.inferred_signature = loop.vault.signature.infer(prompt)
    loop._select_personas = lambda target_count=3: PERSONAS
    loop.metrics = PerformanceMetrics()

    t0 = time.time()
    bb = await loop._run_lens_phase(prompt, step_callback=None)
    elapsed = time.time() - t0

    # 收集每个透镜的原始输出
    lens_outputs = []
    for entry in bb.entries:
        out = {
            "persona": entry.persona,
            "framework": entry.framework,
        }
        if isinstance(entry, EvidenceEntry):
            out["type"] = "evidence"
            out["node_ids"] = entry.evidence_node_ids or []
            out["verification_action"] = entry.verification_action or ""
        elif isinstance(entry, HypothesisEntry):
            out["type"] = "hypothesis"
            out["reasoning_chain"] = entry.reasoning_chain or ""
            out["search_directions"] = entry.suggested_search_directions or []
        lens_outputs.append(out)

    # 坍缩排名
    collapse = bb.collapse(loop.vault)

    # 查询引用节点的实际内容摘要（从 vault）
    all_nids = []
    for entry in bb.entries:
        if isinstance(entry, EvidenceEntry):
            all_nids.extend(entry.evidence_node_ids or [])
    all_nids = list(set(all_nids))
    node_briefs = {}
    if all_nids:
        briefs = loop.vault.get_node_briefs(all_nids)
        for nid, info in briefs.items():
            node_briefs[nid] = {
                "ntype": (info.get("type") or "?").upper(),
                "title": info.get("title", nid),
                "brief": (info.get("content", "") or "")[:150],
            }

    return {
        "qid": qid,
        "elapsed": round(elapsed, 1),
        "tokens": loop.metrics.g_tokens,
        "lens_outputs": lens_outputs,
        "collapse": collapse,
        "node_briefs": node_briefs,
        "voids": bb.search_voids,
    }


def format_answer_sheet(results: list) -> str:
    """生成可读的 Markdown 答卷"""
    lines = [
        "# Genesis Multi-G 答卷",
        "",
        f"配置：5-lens ({', '.join(PERSONAS)})",
        f"模型：DeepSeek-chat (通过 SOCKS5 代理)",
        f"知识库：NodeVault (本地 SQLite + 向量搜索)",
        "",
        "---",
        "",
    ]

    for r in results:
        qid = r["qid"]
        lines.append(f"## {qid}")
        lines.append(f"耗时: {r['elapsed']}s | Token: {r['tokens']:,}")
        lines.append("")

        # 坍缩排名
        lines.append("### 坍缩排名（得分从高到低）")
        for i, c in enumerate(r["collapse"]):
            marker = "** 冠军" if i == 0 else f"#{i+1}"
            entry = c["entry"]
            lines.append(f"- {marker} **{entry.persona}** score={c['score']:.2f} — {entry.framework}")
            if c.get("detail"):
                lines.append(f"  - 评分细节: {c['detail']}")
        lines.append("")

        # 每个透镜的详细输出
        lines.append("### 各透镜视角")
        for lo in r["lens_outputs"]:
            lines.append(f"#### Lens-{lo['persona']} ({lo['type']})")
            lines.append(f"**框架**: {lo['framework']}")
            if lo["type"] == "evidence":
                lines.append(f"**引用节点**: {', '.join(lo['node_ids'])}")
                lines.append(f"**验证动作**: {lo.get('verification_action', 'N/A')}")
            else:
                lines.append(f"**推理链**: {lo.get('reasoning_chain', 'N/A')}")
                dirs = lo.get("search_directions", [])
                if dirs:
                    lines.append(f"**建议搜索方向**: {'; '.join(dirs)}")
            lines.append("")

        # 引用节点内容
        if r["node_briefs"]:
            lines.append("### 引用的知识节点")
            for nid, info in r["node_briefs"].items():
                lines.append(f"- **{nid}** [{info['ntype']}]: {info['brief']}...")
            lines.append("")

        # 搜索空洞
        if r["voids"]:
            lines.append("### 搜索空洞（知识盲区）")
            for v in r["voids"]:
                lines.append(f"- {v.get('persona', '?')}: {v.get('query', '?')} → {v.get('reason', '未找到')}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


async def main():
    provider = ProviderRouter(config=config)
    tools = create_tools()

    results = []
    total = len(EXAM)

    for i, (qid, prompt) in enumerate(EXAM.items(), 1):
        logger.info(f"[{i}/{total}] 考题: {qid}")
        try:
            r = await run_exam_question(qid, prompt, provider, tools)
            results.append(r)
            ev_count = sum(1 for lo in r["lens_outputs"] if lo["type"] == "evidence")
            hyp_count = sum(1 for lo in r["lens_outputs"] if lo["type"] == "hypothesis")
            top = r['collapse'][0] if r['collapse'] else None
            logger.info(f"  → {r['elapsed']}s | {ev_count} evidence, {hyp_count} hypothesis | top={top['score']:.2f} ({top['entry'].persona})" if top else f"  → {r['elapsed']}s | no collapse")
        except Exception as e:
            logger.error(f"  考题 {qid} 失败: {e}", exc_info=True)
            results.append({"qid": qid, "error": str(e)})
        await asyncio.sleep(1)

    # 生成答卷
    answer_sheet = format_answer_sheet([r for r in results if "error" not in r])
    output_path = os.path.join(os.path.dirname(__file__), "eval_genesis_answers.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(answer_sheet)
    logger.info(f"答卷已生成: {output_path}")

    # 也保存原始 JSON
    json_path = os.path.join(os.path.dirname(__file__), "eval_genesis_answers.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"原始数据: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
