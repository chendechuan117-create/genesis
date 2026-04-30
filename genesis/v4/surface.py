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

# 入线数阈值策略：使用分布分位数而非固定值
# 概念要求："入线数较高"=基础，"入线数较低"=探索。阈值随知识库规模自适应。
# P75 意味着约 25% 节点被标记为基础，75% 为探索。库小时阈值低，库大时阈值自动升高。
BASIS_INCOMING_PERCENTILE = 75  # 入线数分布的百分位，>= 此分位数的节点为"基础"
BASIS_INCOMING_FLOOR = 1  # 最低阈值：即使 P75=0，至少入线数>=1 才算基础（避免空库全基础）


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
        # 预取 1-hop 邻居（填充阶段用方向性映射：reasoning_lines 只走 new→old，防止反向跳到前沿新点）
        neighbor_map = self._prefetch_neighbors(seed_ids, directional=True, weighted=True)
        for neighbors in neighbor_map.values():
            if isinstance(neighbors, list):
                for item in neighbors:
                    if isinstance(item, tuple):
                        all_candidate_ids.add(item[0])
                    else:
                        all_candidate_ids.add(item)
            else:
                all_candidate_ids.update(neighbors)

        incoming_counts = self.vault.get_incoming_line_counts_batch(list(all_candidate_ids))

        # 自适应阈值：基于入线数分布分位数，随知识库规模变化
        basis_threshold = self.vault.get_incoming_count_percentile(BASIS_INCOMING_PERCENTILE)
        basis_threshold = max(basis_threshold, BASIS_INCOMING_FLOOR)

        # 过滤消融节点（真理区分：ablation_active=1 的点从面中隐藏）
        ablation_ids = self._get_ablation_ids(all_candidate_ids)
        all_candidate_ids -= ablation_ids

        # 获取虚点饱和信号
        virtual_saturation = self.vault.get_virtual_saturation(list(all_candidate_ids))

        # ── 阶段一：填充（水流扩散）──
        fill_nodes = self._fill_phase(seed_ids, neighbor_map, incoming_counts, fill_budget, ablation_ids, basis_threshold, virtual_saturation)

        # ── 阶段二：推进（替换策略）──
        frontier_ids = self._collect_frontier(fill_nodes, incoming_counts, ablation_ids, basis_threshold)
        retained_fill, push_nodes = self._push_phase(fill_nodes, frontier_ids, incoming_counts, push_budget)

        # 合并结果：保留的 fill + 推进的 frontier
        all_node_ids = list(dict.fromkeys(
            [nid for nid, _ in retained_fill] + [nid for nid, _ in push_nodes]
        ))

        # 角色标注
        surface_nodes = []
        for nid in all_node_ids:
            role = "基础" if incoming_counts.get(nid, 0) >= basis_threshold else "探索"
            surface_nodes.append((nid, role))

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

    def _prefetch_neighbors(self, node_ids: List[str], directional: bool = False, weighted: bool = True) -> Dict[str, List]:
        """预取节点的 1-hop 邻居（委托 vault 公共 API）

        Args:
            directional: True=reasoning_lines只做 new→old 单向映射（填充阶段用），
                False=双向映射（默认，向后兼容）
            weighted: True=返回带权重的邻居，False=返回简单列表
        """
        return self.vault.get_neighbor_map(node_ids, include_reverse_reasoning=not directional, weighted=weighted)

    def _fill_phase(
        self,
        seed_ids: List[str],
        neighbor_map: Dict[str, List],
        incoming_counts: Dict[str, int],
        budget: int,
        excluded_ids: Set[str] = None,
        basis_threshold: int = 2,
        saturation_areas: List[Tuple[str, int]] = None,
    ) -> List[Tuple[str, str]]:
        """
        阶段一：水流扩散 BFS。
        沿高入线数方向优先扩散——入线数多的点阻力小。
        excluded_ids 中的节点不参与扩散（消融/虚点）。
        
        优化：
        - RELATED_TO边权重提升（2.0）
        - 饱和区域降权（0.5）
        - reasoning_lines中等权重（1.5）
        """
        excluded = excluded_ids or set()
        saturation_areas = saturation_areas or []
        candidate_ids = set(incoming_counts.keys()) | set(seed_ids)
        saturation_counts = {}
        if saturation_areas and hasattr(self.vault, "get_saturation_penalty_counts"):
            saturation_counts = self.vault.get_saturation_penalty_counts(list(candidate_ids), min_usage=3)
        visited = set()
        result = []
        queue = deque()

        def _calculate_priority(node_id: str, base_weight: float = 1.0) -> float:
            """计算节点优先级：入线数 * 边权重 * 饱和降权"""
            incoming = incoming_counts.get(node_id, 0)
            
            saturation_penalty = 0.5 if saturation_counts.get(node_id, 0) > 0 else 1.0
            
            return incoming * base_weight * saturation_penalty

        # 种子点入队（按优先级降序，跳过 excluded）
        seeds_with_priority = [(sid, _calculate_priority(sid)) for sid in seed_ids if sid not in excluded]
        seeds_with_priority.sort(key=lambda x: -x[1])
        for sid, _ in seeds_with_priority:
            if sid not in visited:
                queue.append(sid)
                visited.add(sid)

        while queue and len(result) < budget:
            node_id = queue.popleft()
            inc = incoming_counts.get(node_id, 0)
            role = "基础" if inc >= basis_threshold else "探索"
            result.append((node_id, role))

            # 扩展邻居（跳过 excluded，按权重优先级排序）
            neighbors = neighbor_map.get(node_id, [])
            neighbors_with_priority = []
            
            for neighbor in neighbors:
                if isinstance(neighbor, tuple):  # 带权重的情况：(neighbor_id, weight)
                    nid, weight = neighbor
                else:  # 简单列表的情况
                    nid, weight = neighbor, 1.0
                
                if nid not in visited and nid not in excluded:
                    priority = _calculate_priority(nid, weight)
                    neighbors_with_priority.append((nid, priority))
            
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
        basis_threshold: int = 2,
    ) -> List[str]:
        """收集前沿节点：入线数=0 或低入线数的最近创建节点（排除消融/虚点）"""
        excluded = excluded_ids or set()
        fill_ids = {nid for nid, _ in fill_nodes}
        frontier_ids = self.vault.get_frontier_node_ids(limit=50)
        return [fid for fid in frontier_ids if fid not in fill_ids and fid not in excluded and incoming_counts.get(fid, 0) < basis_threshold]

    def _push_phase(
        self,
        fill_nodes: List[Tuple[str, str]],
        frontier_ids: List[str],
        incoming_counts: Dict[str, int],
        budget: int,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """
        阶段二：推进（替换策略）。
        踢掉 fill 中入线数最低的节点（最不稳固=最适合被前沿替换），
        用前沿节点替换。返回 (retained_fill, push_nodes)。
        """
        if not frontier_ids or budget <= 0:
            return fill_nodes, []

        # 按入线数升序排列，低入线数 = 不稳固填充 = 优先踢掉
        fill_sorted = sorted(fill_nodes, key=lambda x: incoming_counts.get(x[0], 0))
        # 踢掉前 budget 个低入线数节点
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
