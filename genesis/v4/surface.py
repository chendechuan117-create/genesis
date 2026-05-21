"""
面（Surface）= 一次性的认知场，由点构成，每轮搜索后组装一次，用完即弃。

三层组装：
1. 填充（水流扩散）：BFS 沿高入线数方向扩散，优先走已被反复验证的推理通道
2. 推进（替换策略）：保留高入线基础，逐步将低入线填充点替换成边缘新点
3. 共场（受控走神）：少量未被显性路径消费的点共同出现，诱发"或许？"
"""

import logging
from collections import deque
from typing import List, Dict, Set, Tuple, Optional, Any

logger = logging.getLogger(__name__)

# 入线数阈值策略：使用分布分位数而非固定值
# 概念要求："入线数较高"=基础，"入线数较低"=探索。阈值随知识库规模自适应。
# P75 意味着约 25% 节点被标记为基础，75% 为探索。库小时阈值低，库大时阈值自动升高。
BASIS_INCOMING_PERCENTILE = 75  # 入线数分布的百分位，>= 此分位数的节点为"基础"
BASIS_INCOMING_FLOOR = 1  # 最低阈值：即使 P75=0，至少入线数>=1 才算基础（避免空库全基础）
CO_PRESENCE_RATIO = 0.15


class SurfaceExpander:
    """面组装器：从种子点出发组装基础、推进、共场三层认知场"""

    def __init__(self, vault):
        self.vault = vault

    def expand_surface(
        self,
        seed_ids: List[str],
        context_budget: int = 100,
        replace_ratio: float = 0.6,
        query_text: Optional[str] = None,
    ) -> Dict:
        """
        三层组装面。

        Args:
            seed_ids: 搜索命中的种子点 ID 列表
            context_budget: 面容纳的最大点数（近似 token 预算 / 单点 token 估算）
            replace_ratio: 填充阶段占预算的比例，剩余留给推进阶段
            query_text: 可选的查询文本，用于 V6 主动概率门控

        Returns:
            {
                "surface_nodes": [(node_id, role), ...],  # role = "基础" | "探索" | "游离"
                "fill_count": int,
                "push_count": int,
                "co_presence_count": int,
                "virtual_saturation": [(area_hint, count), ...],  # 虚点饱和信号
                "potential_samples": [{"type": str, "title": str, "detail": str, ...}, ...],
            }
        """
        if not seed_ids:
            return {"surface_nodes": [], "fill_count": 0, "push_count": 0, "co_presence_count": 0, "virtual_saturation": [], "potential_samples": []}

        fill_budget = int(context_budget * replace_ratio)
        replacement_budget = context_budget - fill_budget
        co_presence_budget = min(int(context_budget * CO_PRESENCE_RATIO), max(0, replacement_budget))
        push_budget = max(0, replacement_budget - co_presence_budget)

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

        # V6 神经网络前置概率门控拦截
        if query_text:
            all_candidate_ids = self._v6_gating_filter(all_candidate_ids, query_text)

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
        frontier_ids = self._surface_diversity_guard(frontier_ids)
        retained_fill, push_nodes = self._push_phase(fill_nodes, frontier_ids, incoming_counts, push_budget)

        retained_ids = {nid for nid, _ in retained_fill}
        used_ids = retained_ids | {nid for nid, _ in push_nodes}
        evicted_fill = [(nid, role) for nid, role in fill_nodes if nid not in retained_ids]

        # ── 阶段三：共场（受控走神）──
        co_presence_nodes = self._co_presence_phase(
            evicted_fill,
            neighbor_map,
            incoming_counts,
            co_presence_budget,
            used_ids,
            ablation_ids,
            basis_threshold,
        )

        # 合并结果：保留的 fill + 推进的 frontier + 共场游离点
        all_node_ids = list(dict.fromkeys(
            [nid for nid, _ in retained_fill] + [nid for nid, _ in push_nodes] + [nid for nid, _ in co_presence_nodes]
        ))
        co_presence_ids = {nid for nid, _ in co_presence_nodes}

        # 角色标注
        surface_nodes = []
        for nid in all_node_ids:
            if nid in co_presence_ids:
                role = "游离"
            else:
                role = "基础" if incoming_counts.get(nid, 0) >= basis_threshold else "探索"
            surface_nodes.append((nid, role))

        fill_count = sum(1 for _, r in surface_nodes if r == "基础")
        push_count = sum(1 for _, r in surface_nodes if r == "探索")
        co_presence_count = sum(1 for _, r in surface_nodes if r == "游离")

        logger.info(
            f"Surface: {len(surface_nodes)} nodes ({fill_count} basis, {push_count} frontier, {co_presence_count} co-presence) "
            f"from {len(seed_ids)} seeds, budget={context_budget}"
        )

        potential_samples = self._build_potential_samples(
            retained_fill=retained_fill,
            push_nodes=push_nodes,
            co_presence_nodes=co_presence_nodes,
            virtual_saturation=virtual_saturation,
            fill_count=fill_count,
            push_count=push_count,
            co_presence_count=co_presence_count,
        )

        return {
            "surface_nodes": surface_nodes,
            "fill_count": fill_count,
            "push_count": push_count,
            "co_presence_count": co_presence_count,
            "virtual_saturation": virtual_saturation,
            "potential_samples": potential_samples,
        }

    def _build_potential_samples(
        self,
        retained_fill: List[Tuple[str, str]],
        push_nodes: List[Tuple[str, str]],
        co_presence_nodes: List[Tuple[str, str]],
        virtual_saturation: List[Tuple[str, int]],
        fill_count: int,
        push_count: int,
        co_presence_count: int,
    ) -> List[Dict[str, Any]]:
        samples: List[Dict[str, Any]] = []
        if co_presence_nodes:
            samples.append({
                "type": "co_presence",
                "title": "游离点共场形成“或许？”",
                "detail": "这些点只提供弱关系感；如果后续被验证，才沉淀为新的点和线。",
                "node_ids": [nid for nid, _ in co_presence_nodes[:8]],
                "evidence": {"co_presence_count": co_presence_count},
            })
        if virtual_saturation:
            for area_hint, count in virtual_saturation[:3]:
                samples.append({
                    "type": "saturation",
                    "title": f"饱和势：{area_hint}",
                    "detail": "该区域路径重叠频繁，继续深挖的边际收益可能下降。",
                    "node_ids": [],
                    "evidence": {"area_hint": area_hint, "count": count},
                })
        if fill_count == 0 and push_count > 0:
            samples.append({
                "type": "missing_basis",
                "title": "当前面缺少基础锚点",
                "detail": "当前更像探索前沿，沉淀新点前应先补足依据或验证链路。",
                "node_ids": [nid for nid, _ in push_nodes[:8]],
                "evidence": {"fill_count": fill_count, "push_count": push_count},
            })
        elif retained_fill and push_nodes:
            samples.append({
                "type": "frontier_pressure",
                "title": "基础与前沿同时在场",
                "detail": "当前面已提供脚下基础和附近前沿，适合沿当前问题推进，而不是为形式扩大搜索面。",
                "node_ids": [nid for nid, _ in retained_fill[:4]] + [nid for nid, _ in push_nodes[:4]],
                "evidence": {"fill_count": fill_count, "push_count": push_count},
            })
        return samples[:5]

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
        budget = min(budget, len(frontier_ids))
        # 踢掉前 budget 个低入线数节点
        evicted = {nid for nid, _ in fill_sorted[:budget]}
        retained_fill = [(nid, role) for nid, role in fill_nodes if nid not in evicted]

        # 用前沿节点替换
        push_nodes = [(fid, "探索") for fid in frontier_ids[:budget]]

        return retained_fill, push_nodes

    def _surface_diversity_guard(
        self,
        frontier_ids: List[str],
        overlap_threshold: float = 0.8,
    ) -> List[str]:
        if len(frontier_ids) <= 1:
            return frontier_ids
        if not hasattr(self.vault, "get_basis_set_for_node"):
            return frontier_ids
        selected: List[str] = []
        selected_basis: Dict[str, Set[str]] = {}
        for node_id in frontier_ids:
            basis = self.vault.get_basis_set_for_node(node_id, include_same_round=False)
            if not basis:
                selected.append(node_id)
                selected_basis[node_id] = set()
                continue
            too_similar = False
            for existing_basis in selected_basis.values():
                if not existing_basis:
                    continue
                union = basis | existing_basis
                if not union:
                    continue
                overlap = len(basis & existing_basis) / len(union)
                if overlap >= overlap_threshold:
                    too_similar = True
                    break
            if not too_similar:
                selected.append(node_id)
                selected_basis[node_id] = basis
        if len(selected) < len(frontier_ids):
            logger.debug(
                "Surface diversity guard reduced frontier candidates from %s to %s",
                len(frontier_ids),
                len(selected),
            )
        return selected

    def _co_presence_phase(
        self,
        evicted_fill: List[Tuple[str, str]],
        neighbor_map: Dict[str, List],
        incoming_counts: Dict[str, int],
        budget: int,
        used_ids: Set[str],
        excluded_ids: Set[str] = None,
        basis_threshold: int = 2,
    ) -> List[Tuple[str, str]]:
        """收集共场游离点：只共同出现，不声明推理关系"""
        if budget <= 0:
            return []

        excluded = excluded_ids or set()
        candidates: Dict[str, float] = {}

        for nid, _ in evicted_fill:
            if nid not in used_ids and nid not in excluded:
                candidates[nid] = max(candidates.get(nid, 0.0), 3.0)

        for neighbors in neighbor_map.values():
            for neighbor in neighbors:
                if isinstance(neighbor, tuple):
                    nid, weight = neighbor
                else:
                    nid, weight = neighbor, 1.0
                if nid in used_ids or nid in excluded:
                    continue
                incoming = incoming_counts.get(nid, 0)
                if incoming >= basis_threshold:
                    continue
                novelty = 1.0 / (1.0 + incoming)
                candidates[nid] = max(candidates.get(nid, 0.0), float(weight) + novelty)

        ranked = sorted(candidates.items(), key=lambda x: (-x[1], x[0]))
        return [(nid, "游离") for nid, _ in ranked[:budget]]

    def _check_virtual_saturation(self, node_ids: List[str]) -> List[Tuple[str, int]]:
        """检查虚点饱和信号：查询面节点邻域内的虚点，按区域聚合"""
        return self.vault.get_virtual_saturation(node_ids)

    def _get_ablation_ids(self, candidate_ids: set) -> set:
        """获取消融中的节点 ID 集合（委托 vault 公共 API）"""
        return self.vault.get_excluded_ids(list(candidate_ids))

    def _v6_gating_filter(self, candidate_ids: Set[str], query_text: str) -> Set[str]:
        """
        V6 神经网络前合流概率门控（Implicit Gating / Space Bending）。
        根据当前 query_text，利用 NumPy 小脑在 1ms 内计算激活概率空间，
        将未被概率激活（与当前推理任务极不相关）的长尾节点在进入 Context 前过滤。
        """
        try:
            from genesis.v6.dataset_compiler import DEFAULT_VOCAB_PATH
            from genesis.v6.brain import DEFAULT_WEIGHTS_PATH, ContinuousBrain
            import os
            import json
            import numpy as np
            
            # 检查是否启用 V6 拦截环境变量
            if str(os.environ.get("V6_ACTIVE_GATING", "0")).lower() not in ("1", "true", "yes"):
                return candidate_ids
                
            if not DEFAULT_VOCAB_PATH.exists() or not DEFAULT_WEIGHTS_PATH.exists():
                return candidate_ids
                
            # 加载词表
            with open(DEFAULT_VOCAB_PATH, "r", encoding="utf-8") as f:
                vocab_data = json.load(f)
                label_to_index = vocab_data["label_to_index"]
                index_to_label = vocab_data["index_to_label"]
                
            # 初始化小脑并加载权重
            brain = ContinuousBrain(output_dim=len(index_to_label))
            if not brain.load_weights():
                return candidate_ids
                
            # 编码 Query 文本
            from genesis.v4.vector_engine import VectorEngine
            ve = VectorEngine()
            if not ve.is_ready:
                return candidate_ids
            q_vector = ve.encode(query_text)
            if q_vector is None:
                return candidate_ids
                
            # 前向计算概率
            X = np.array([q_vector], dtype=np.float32)
            probabilities = brain.forward(X)[0]
            
            # 门控概率阈值
            threshold = float(os.environ.get("V6_GATING_THRESHOLD", "0.15"))
            active_label_indices = np.where(probabilities >= threshold)[0]
            active_labels = {index_to_label[idx] for idx in active_label_indices}
            
            if not active_labels:
                return candidate_ids
                
            # 比对候选节点特征，对未落入激活概率空间的多标签节点进行概率弯曲过滤
            rows = self.vault._conn.execute(
                f"SELECT node_id, metadata_signature FROM knowledge_nodes WHERE node_id IN ({','.join('?' * len(candidate_ids))})",
                list(candidate_ids)
            ).fetchall()
            
            allowed_ids = set()
            for row in rows:
                nid = row["node_id"]
                sig_str = row["metadata_signature"]
                if not sig_str:
                    allowed_ids.add(nid)
                    continue
                try:
                    sig = json.loads(sig_str)
                    if not sig:
                        allowed_ids.add(nid)
                        continue
                    
                    node_matched = False
                    for field in ["error_kind", "framework", "task_kind", "runtime", "target_kind"]:
                        val = sig.get(field)
                        if val:
                            vals = val if isinstance(val, list) else [val]
                            for v in vals:
                                label_key = f"{field}:{str(v).strip().lower()}"
                                if label_key in active_labels:
                                    node_matched = True
                                    break
                        if node_matched:
                            break
                            
                    if node_matched:
                        allowed_ids.add(nid)
                except Exception:
                    allowed_ids.add(nid)
                    
            logger.info(f"V6 Active Gating: bent candidate space from {len(candidate_ids)} to {len(allowed_ids)} nodes.")
            return allowed_ids
        except Exception as e:
            logger.error(f"V6 Active Gating exception: {e}")
            return candidate_ids

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
        co_presence_nodes = [(nid, role) for nid, role in surface_nodes if role == "游离"]

        if basis_nodes:
            items = [f"{titles.get(nid, nid[:12])}[{nid}]" for nid, _ in basis_nodes[:10]]
            lines.append(f"[基础] 有可复用的基础候选：{', '.join(items)}")
        if frontier_nodes:
            items = [f"{titles.get(nid, nid[:12])}[{nid}]" for nid, _ in frontier_nodes[:10]]
            lines.append(f"[探索] 有待验证的前沿节点：{', '.join(items)}")
        if co_presence_nodes:
            items = [f"{titles.get(nid, nid[:12])}[{nid}]" for nid, _ in co_presence_nodes[:10]]
            lines.append(f"[游离] 存在共场游离点：{', '.join(items)}")
            lines.append("[共场] 游离点用于触发“或许？”，不是必须处理的任务，也不代表关系已成立")

        potential_samples = surface_result.get("potential_samples", [])
        if potential_samples:
            lines.append("[势] 以下只是当轮“或许？”样本，不是事实或任务")
            for sample in potential_samples[:3]:
                title = sample.get("title", "未命名势")
                detail = sample.get("detail", "")
                lines.append(f"  - {title}：{detail}")

        # 虚点饱和信号
        virtual_sat = surface_result.get("virtual_saturation", [])
        for area_hint, _ in virtual_sat:
            lines.append(f"[饱和] {area_hint}：该区域有饱和倾向，优先转向不饱和邻域")

        return "\n".join(lines)
