"""
面（Surface）= 一次性的信息引用组合，由点构成，每轮搜索后组装一次，用完即弃。

两阶段组装：
1. 填充（水流扩散）：BFS 沿高入线数方向扩散，优先走已被反复验证的推理通道
2. 推进（替换策略）：逐步将核心旧点替换成边缘新点，GP 被推向知识前沿
"""

import logging
from collections import deque
from typing import List, Dict, Set, Tuple, Optional

logger = logging.getLogger(__name__)

# 入线数阈值：>= 此值标记为"基础"，< 此值标记为"探索"
BASIS_INCOMING_THRESHOLD = 2


class SurfaceExpander:
    """面组装器：从种子点出发，两阶段 BFS 扩散组装面"""

    def __init__(self, vault):
        self.vault = vault

    def expand_surface(
        self,
        seed_ids: List[str],
        context_budget: int = 100,
        replace_ratio: float = 0.6,
    ) -> Dict:
        """
        两阶段组装面。

        Args:
            seed_ids: 搜索命中的种子点 ID 列表
            context_budget: 面容纳的最大点数（近似 token 预算 / 单点 token 估算）
            replace_ratio: 填充阶段占预算的比例，剩余留给推进阶段

        Returns:
            {
                "surface_nodes": [(node_id, role), ...],  # role = "基础" | "探索"
                "fill_count": int,
                "push_count": int,
                "virtual_saturation": [(area_hint, count), ...],  # 虚点饱和信号
            }
        """
        if not seed_ids:
            return {"surface_nodes": [], "fill_count": 0, "push_count": 0, "virtual_saturation": []}

        fill_budget = int(context_budget * replace_ratio)
        push_budget = context_budget - fill_budget

        # 批量获取入线数（一次查询）
        # 先收集所有可能涉及的节点 ID，再批量查
        all_candidate_ids = set(seed_ids)
        # 预取 1-hop 邻居
        neighbor_map = self._prefetch_neighbors(seed_ids)
        for neighbors in neighbor_map.values():
            all_candidate_ids.update(neighbors)

        incoming_counts = self.vault.get_incoming_line_counts_batch(list(all_candidate_ids))

        # 过滤消融节点（真理区分：ablation_active=1 的点从面中隐藏）
        ablation_ids = self._get_ablation_ids(all_candidate_ids)
        all_candidate_ids -= ablation_ids

        # ── 阶段一：填充（水流扩散）──
        fill_nodes = self._fill_phase(seed_ids, neighbor_map, incoming_counts, fill_budget, ablation_ids)

        # ── 阶段二：推进（替换策略）──
        frontier_ids = self._collect_frontier(fill_nodes, incoming_counts, ablation_ids)
        retained_fill, push_nodes = self._push_phase(fill_nodes, frontier_ids, incoming_counts, push_budget)

        # 合并结果：保留的 fill + 推进的 frontier
        all_node_ids = list(dict.fromkeys(
            [nid for nid, _ in retained_fill] + [nid for nid, _ in push_nodes]
        ))

        # 角色标注
        surface_nodes = []
        for nid in all_node_ids:
            role = "基础" if incoming_counts.get(nid, 0) >= BASIS_INCOMING_THRESHOLD else "探索"
            surface_nodes.append((nid, role))

        # 虚点饱和信号
        virtual_saturation = self._check_virtual_saturation(all_node_ids)

        fill_count = sum(1 for _, r in surface_nodes if r == "基础")
        push_count = sum(1 for _, r in surface_nodes if r == "探索")

        logger.info(
            f"Surface: {len(surface_nodes)} nodes ({fill_count} basis, {push_count} frontier) "
            f"from {len(seed_ids)} seeds, budget={context_budget}"
        )

        return {
            "surface_nodes": surface_nodes,
            "fill_count": fill_count,
            "push_count": push_count,
            "virtual_saturation": virtual_saturation,
        }

    def _prefetch_neighbors(self, node_ids: List[str]) -> Dict[str, List[str]]:
        """预取节点的 1-hop 邻居（委托 vault 公共 API）"""
        return self.vault.get_neighbor_map(node_ids)

    def _fill_phase(
        self,
        seed_ids: List[str],
        neighbor_map: Dict[str, List[str]],
        incoming_counts: Dict[str, int],
        budget: int,
        excluded_ids: Set[str] = None,
    ) -> List[Tuple[str, str]]:
        """
        阶段一：水流扩散 BFS。
        沿高入线数方向优先扩散——入线数多的点阻力小。
        excluded_ids 中的节点不参与扩散（消融/虚点）。
        """
        excluded = excluded_ids or set()
        visited = set()
        result = []
        queue = deque()

        # 种子点入队（按入线数降序，跳过 excluded）
        seeds_with_priority = [(sid, incoming_counts.get(sid, 0)) for sid in seed_ids if sid not in excluded]
        seeds_with_priority.sort(key=lambda x: -x[1])
        for sid, _ in seeds_with_priority:
            if sid not in visited:
                queue.append(sid)
                visited.add(sid)

        while queue and len(result) < budget:
            node_id = queue.popleft()
            inc = incoming_counts.get(node_id, 0)
            role = "基础" if inc >= BASIS_INCOMING_THRESHOLD else "探索"
            result.append((node_id, role))

            # 扩展邻居（跳过 excluded，按入线数排序）
            neighbors = neighbor_map.get(node_id, [])
            neighbors_with_priority = [(n, incoming_counts.get(n, 0)) for n in neighbors if n not in visited and n not in excluded]
            neighbors_with_priority.sort(key=lambda x: -x[1])

            for nid, _ in neighbors_with_priority:
                if nid not in visited and len(result) + len(queue) < budget * 2:
                    queue.append(nid)
                    visited.add(nid)

        return result

    def _collect_frontier(
        self,
        fill_nodes: List[Tuple[str, str]],
        incoming_counts: Dict[str, int],
        excluded_ids: Set[str] = None,
    ) -> List[str]:
        """收集前沿节点：入线数=0 或低入线数的最近创建节点（排除消融/虚点）"""
        excluded = excluded_ids or set()
        fill_ids = {nid for nid, _ in fill_nodes}
        frontier_ids = self.vault.get_frontier_node_ids(limit=50)
        return [fid for fid in frontier_ids if fid not in fill_ids and fid not in excluded and incoming_counts.get(fid, 0) < BASIS_INCOMING_THRESHOLD]

    def _push_phase(
        self,
        fill_nodes: List[Tuple[str, str]],
        frontier_ids: List[str],
        incoming_counts: Dict[str, int],
        budget: int,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """
        阶段二：推进（替换策略）。
        踢掉 fill 中入线数最高的节点（最核心=最不需要在面中展示），
        用前沿节点替换。返回 (retained_fill, push_nodes)。
        """
        if not frontier_ids or budget <= 0:
            return fill_nodes, []

        # 按入线数降序排列，高入线数 = 核心 = 优先踢掉
        fill_sorted = sorted(fill_nodes, key=lambda x: -incoming_counts.get(x[0], 0))
        # 踢掉前 budget 个高入线数节点
        evicted = {nid for nid, _ in fill_sorted[:budget]}
        retained_fill = [(nid, role) for nid, role in fill_nodes if nid not in evicted]

        # 用前沿节点替换
        push_count = min(budget, len(frontier_ids))
        push_nodes = [(fid, "探索") for fid in frontier_ids[:push_count]]

        return retained_fill, push_nodes

    def _check_virtual_saturation(self, node_ids: List[str]) -> List[Tuple[str, int]]:
        """检查虚点饱和信号：查询面节点邻域内的虚点，按区域聚合"""
        return self.vault.get_virtual_saturation(node_ids)

    def _get_ablation_ids(self, candidate_ids: set) -> set:
        """获取消融中的节点 ID 集合（委托 vault 公共 API）"""
        return self.vault.get_excluded_ids(list(candidate_ids))

    def render_surface(self, surface_result: Dict) -> str:
        """将面结果渲染为 GP 可读的文本"""
        surface_nodes = surface_result.get("surface_nodes", [])
        if not surface_nodes:
            return ""

        # 批量获取标题
        all_ids = [nid for nid, _ in surface_nodes]
        titles = self.vault.batch_get_titles(all_ids)

        lines = []
        basis_nodes = [(nid, role) for nid, role in surface_nodes if role == "基础"]
        frontier_nodes = [(nid, role) for nid, role in surface_nodes if role == "探索"]

        if basis_nodes:
            items = [f"{titles.get(nid, nid[:12])}[{nid}]" for nid, _ in basis_nodes[:10]]
            lines.append(f"[基础] {len(basis_nodes)} 个已验证节点：{', '.join(items)}")
        if frontier_nodes:
            items = [f"{titles.get(nid, nid[:12])}[{nid}]" for nid, _ in frontier_nodes[:10]]
            lines.append(f"[探索] {len(frontier_nodes)} 个前沿节点：{', '.join(items)}")

        # 虚点饱和信号
        virtual_sat = surface_result.get("virtual_saturation", [])
        for area_hint, count in virtual_sat:
            lines.append(f"[饱和] {area_hint} 已有 {count} 个虚点 = 知识饱和")

        return "\n".join(lines)
