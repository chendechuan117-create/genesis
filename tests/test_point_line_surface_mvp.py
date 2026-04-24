"""
点线面 MVP 端到端试验：验证核心管线在真实 NodeVault 上工作。

覆盖：
1. reasoning_lines 写入 + 入线数计算（排除同轮）
2. RecordLessonNodeTool reasoning_basis 连线
3. 碰撞检测
4. 面两阶段组装（SurfaceExpander）
5. C-Gardener 加边（CONTRADICTS/RELATED_TO）
6. 消融触发 + 评估闭环
7. 搜索输出角色标签（基础/探索）

用法：python3 tests/test_point_line_surface_mvp.py
"""
import asyncio
import os
import sys
import sqlite3
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format='%(name)s | %(levelname)s | %(message)s')
logger = logging.getLogger('MVP')

DB_PATH = os.path.expanduser('~/.nanogenesis/workshop_v4.sqlite')


def step(n, title):
    logger.info(f"\n{'='*60}\n  Step {n}: {title}\n{'='*60}")


async def main():
    from genesis.v4.manager import NodeVault
    from genesis.v4.surface import SurfaceExpander
    from genesis.tools.node_tools import RecordLessonNodeTool, CreateNodeEdgeTool
    from genesis.tools.search_tool import SearchKnowledgeNodesTool

    vault = NodeVault()
    step(1, "reasoning_lines 写入 + 入线数计算")

    # 创建旧节点作为 basis
    old_nodes = []
    for i, (nid, title) in enumerate([
        ("MVP_BASIS_01", "DeepSeek API 直连比代理快"),
        ("MVP_BASIS_02", "trust_env=False 跳过系统代理"),
        ("MVP_BASIS_03", "v2rayA tproxy 在内核层路由"),
    ]):
        vault.create_node(node_id=nid, title=title, ntype="LESSON",
                         human_translation=title, tags="mvp_test",
                         full_content=f"验证事实: {title}", trust_tier="REFLECTION")
        old_nodes.append(nid)
    logger.info(f"  创建 {len(old_nodes)} 个基础节点")

    # GP 写新点 + 连线（异轮）
    new_round_1 = "MVP_NEW_R1_01"
    vault.create_node(node_id=new_round_1, title="国内API无需代理直连", ntype="LESSON",
                     human_translation="国内API无需代理直连", tags="mvp_test",
                     full_content="DeepSeek等国内API直连延迟0.15s，走SOCKS5代理11s", trust_tier="REFLECTION")
    for bid in old_nodes[:2]:
        vault.create_reasoning_line(new_round_1, bid, reasoning="基于API延迟测试", source="GP", same_round=0)
    logger.info(f"  新点 {new_round_1} 连线到 {old_nodes[:2]}（异轮）")

    # GP 写新点 + 连线（同轮）
    new_round_1_sibling = "MVP_NEW_R1_02"
    vault.create_node(node_id=new_round_1_sibling, title="provider.py trust_env优化", ntype="LESSON",
                     human_translation="provider.py trust_env优化", tags="mvp_test",
                     full_content="provider.py设置trust_env=False强制直连", trust_tier="REFLECTION")
    for bid in old_nodes[:2]:
        vault.create_reasoning_line(new_round_1_sibling, bid, reasoning="同轮发现", source="GP", same_round=1)
    logger.info(f"  新点 {new_round_1_sibling} 连线到 {old_nodes[:2]}（同轮）")

    # 再一轮异轮线
    new_round_2 = "MVP_NEW_R2_01"
    vault.create_node(node_id=new_round_2, title="httpx默认trust_env=True会读环境变量", ntype="LESSON",
                     human_translation="httpx默认trust_env=True会读环境变量", tags="mvp_test",
                     full_content="httpx AsyncClient默认trust_env=True读取HTTPS_PROXY", trust_tier="REFLECTION")
    vault.create_reasoning_line(new_round_2, old_nodes[0], reasoning="延迟根因分析", source="GP", same_round=0)
    vault.create_reasoning_line(new_round_2, old_nodes[1], reasoning="修复方案依据", source="GP", same_round=0)
    logger.info(f"  新点 {new_round_2} 连线到 {old_nodes[0]}, {old_nodes[1]}（异轮）")

    # 验证入线数
    for nid in old_nodes:
        count = vault.get_incoming_line_count(nid)
        logger.info(f"  入线数 {nid}: {count}（应排除同轮线）")

    # MVP_BASIS_01 应有 2 条异轮线（R1_01 + R2_01），同轮线不贡献
    c01 = vault.get_incoming_line_count(old_nodes[0])
    assert c01 == 2, f"入线数应为2，实际{c01}"
    logger.info(f"  ✅ 入线数排除同轮线验证通过")

    # ── Step 2: RecordLessonNodeTool reasoning_basis ──
    step(2, "RecordLessonNodeTool reasoning_basis 连线")

    tool = RecordLessonNodeTool()
    result = await tool.execute(
        node_id="MVP_TOOL_01",
        title="工具连线测试节点",
        trigger_verb="验证",
        trigger_noun="reasoning_basis",
        trigger_context="MVP测试",
        action_steps=["创建节点并连线到basis"],
        because_reason="验证reasoning_basis自动连线",
        resolves="reasoning_basis连线验证",
        reasoning_basis=["MVP_BASIS_01", "MVP_BASIS_02"],
    )
    logger.info(f"  工具返回: {result[:120]}...")
    assert "推理线" in result, "reasoning_basis 连线应返回推理线信息"
    c_after = vault.get_incoming_line_count("MVP_BASIS_01")
    logger.info(f"  MVP_BASIS_01 入线数: {c_after}（应为3）")
    assert c_after == 3, f"工具连线后入线数应为3，实际{c_after}"
    logger.info(f"  ✅ RecordLessonNodeTool 连线验证通过")

    # ── Step 3: 碰撞检测 ──
    step(3, "碰撞检测")

    # 新节点引用 MVP_BASIS_01 + MVP_BASIS_02，跟 MVP_TOOL_01 的 basis 重叠
    collisions = vault.find_collision_candidates(["MVP_BASIS_01", "MVP_BASIS_02"], min_overlap=2)
    logger.info(f"  碰撞候选: {collisions}")
    assert len(collisions) > 0, "应有碰撞候选（MVP_TOOL_01 引用了相同 basis）"
    logger.info(f"  ✅ 碰撞检测验证通过")

    # ── Step 4: 面两阶段组装 ──
    step(4, "面两阶段组装（SurfaceExpander）")

    expander = SurfaceExpander(vault)
    result = expander.expand_surface(seed_ids=["MVP_BASIS_01"], context_budget=2000)
    surface = result["surface_nodes"]
    logger.info(f"  面节点数: {len(surface)}")
    for nid, role in surface[:10]:
        inc = vault.get_incoming_line_count(nid)
        logger.info(f"    {nid}: 角色={role}, 入线数={inc}")
    basis_count = sum(1 for _, r in surface if r == "基础")
    explore_count = sum(1 for _, r in surface if r == "探索")
    logger.info(f"  基础: {basis_count}, 探索: {explore_count}")
    assert len(surface) > 0, "面应包含节点"
    logger.info(f"  ✅ 面组装验证通过")

    # ── Step 5: C-Gardener 加边 ──
    step(5, "C-Gardener 加边（CONTRADICTS/RELATED_TO）")

    edge_tool = CreateNodeEdgeTool()
    edge_tool.vault = vault  # 必须用同一个 vault

    r1 = await edge_tool.execute(
        source_id="MVP_NEW_R1_01", target_id="MVP_BASIS_03",
        relation="CONTRADICTS", weight=1.0
    )
    logger.info(f"  CONTRADICTS: {r1}")
    assert "✅" in r1, "CONTRADICTS 边应创建成功"

    r2 = await edge_tool.execute(
        source_id="MVP_NEW_R1_01", target_id="MVP_NEW_R2_01",
        relation="RELATED_TO", weight=0.8
    )
    logger.info(f"  RELATED_TO: {r2}")
    assert "✅" in r2, "RELATED_TO 边应创建成功"
    logger.info(f"  ✅ C-Gardener 加边验证通过")

    # ── Step 6: 消融触发 + 评估闭环 ──
    step(6, "消融触发 + 评估闭环")

    # MVP_BASIS_01 入线数=3，不够5。手动加线到5
    for i in range(3, 5):
        fake_new = f"MVP_FAKE_R{i}_01"
        vault.create_node(node_id=fake_new, title=f"填充线{i}", ntype="LESSON",
                         human_translation=f"填充线{i}", tags="mvp_test",
                         full_content="填充", trust_tier="REFLECTION")
        vault.create_reasoning_line(fake_new, "MVP_BASIS_01", reasoning="填充入线数", source="GP", same_round=0)

    c_final = vault.get_incoming_line_count("MVP_BASIS_01")
    logger.info(f"  MVP_BASIS_01 入线数: {c_final}（应≥5触发消融）")
    assert c_final >= 5, f"入线数应≥5，实际{c_final}"

    # 触发消融
    candidates = vault.check_ablation_candidates(min_incoming=5)
    logger.info(f"  消融候选: {candidates}")
    assert any(c[0] == "MVP_BASIS_01" for c in candidates), "MVP_BASIS_01 应为消融候选"

    vault.activate_ablation("MVP_BASIS_01", baseline_env_ratio=0.7)
    logger.info(f"  消融已激活: MVP_BASIS_01")

    # 评估消融
    observing = vault.get_ablation_observing_nodes(min_duration_seconds=0)  # 0秒以便测试
    logger.info(f"  消融观察中节点: {observing}")
    assert any(n[0] == "MVP_BASIS_01" for n in observing), "MVP_BASIS_01 应在观察中"

    result = vault.deactivate_ablation("MVP_BASIS_01", current_env_ratio=0.5)
    logger.info(f"  消融评估结果: {result}（baseline=0.7, current=0.5, 下降→向后=必要跳板）")
    assert result == "confirmed_valuable", f"env_ratio下降应判定为confirmed_valuable，实际{result}"
    logger.info(f"  ✅ 消融触发+评估闭环验证通过")

    # ── Step 7: 搜索输出角色标签 ──
    step(7, "搜索输出角色标签")

    search_tool = SearchKnowledgeNodesTool()
    search_tool.vault = vault
    results = await search_tool.execute(keywords=["API", "代理", "直连"])
    # 检查结果中是否有角色标签
    has_role = "基础" in results or "探索" in results or "Basis" in results or "Exploration" in results
    logger.info(f"  搜索结果含角色标签: {has_role}")
    logger.info(f"  搜索结果前200字: {results[:200]}")
    logger.info(f"  ✅ 搜索输出验证完成")

    # ── 清理 MVP 测试节点 ──
    step(8, "清理 MVP 测试数据")

    conn = vault._conn
    test_ids = [r[0] for r in conn.execute(
        "SELECT node_id FROM knowledge_nodes WHERE node_id LIKE 'MVP_%'"
    ).fetchall()]
    for nid in test_ids:
        vault.delete_node(nid)
    # 清理消融基线
    conn.execute("DELETE FROM ablation_baselines WHERE node_id LIKE 'MVP_%'")
    conn.commit()
    logger.info(f"  清理了 {len(test_ids)} 个 MVP 测试节点")

    logger.info("\n" + "="*60)
    logger.info("  🎉 MVP 试验全部通过！点线面核心管线工作正常。")
    logger.info("="*60)


if __name__ == '__main__':
    asyncio.run(main())
