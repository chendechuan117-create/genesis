# 点线面工程实施笔记

> 按顺序执行，每步记录逻辑和总结。设计文档见 point_line_surface.md

---

## Step 1：创建 reasoning_lines 表 + 写入接口 ✅

**状态**：完成

**逻辑**：
线是点线面的核心——没有线就没有入线数，没有入线数就没有价值信号、没有碰撞检测、没有面水流扩散。
reasoning_lines 表必须先于一切存在。

**改动**：
- 文件：`v4/manager.py`
- `_ensure_schema()` 新增 reasoning_lines 建表 + 2 个索引（idx_rl_basis, idx_rl_new）
- 新增 5 个方法：
  - `create_reasoning_line(new_point_id, basis_point_id, reasoning, source)` — 写线
  - `get_incoming_line_count(node_id)` — 单点入线数
  - `get_incoming_line_counts_batch(node_ids)` — 批量入线数（避免 N+1，供搜索/面使用）
  - `get_basis_set_for_node(new_point_id)` — 获取某新点的 basis 集合（碰撞检测用）
  - `find_collision_candidates(basis_ids, min_overlap)` — 碰撞检测：查重叠已有节点（Step 5 用）
- `delete_node()` 增加 reasoning_lines 清理

**总结**：
reasoning_lines 表结构：line_id(PK), new_point_id(线的起点/新点), basis_point_id(线的终点/旧点), reasoning(因果说明), source(GP/C), created_at。
索引在 basis_point_id 上（入线数查询高频）和 new_point_id 上（碰撞检测用）。
额外实现了 find_collision_candidates，提前为 Step 5 碰撞检测铺路——一次 SQL GROUP BY 即可找到重叠节点，不需要额外相似度算法。

---

## Step 2：RecordLessonNodeTool 加 reasoning_basis 参数 ✅

**状态**：完成

**逻辑**：
GP 写点时必须连线——没有线的创新 = 无法判断价值 = 无法去重 = 噪音。
reasoning_basis 是 GP 主动声明"我基于哪些旧节点产生此经验"的入口。
validateInput 模式（参考 Claude Code 源码）：execute() 开头校验，为空返回 Error 让模型重试。

**改动**：
- 文件：`tools/node_tools.py`（class RecordLessonNodeTool）
- parameters 新增 `reasoning_basis`（array of string，必填）
- required 列表加入 `"reasoning_basis"`
- execute() 签名加 `reasoning_basis: List[str] = None`
- execute() 开头加 validateInput：为空返回 Error 提示
- 写入节点后，遍历 reasoning_basis 调用 `self.vault.create_reasoning_line(node_id, bid, reasoning=because_reason, source="GP")`
- 返回消息追加 `🔗 推理线→{valid_basis}`

**总结**：
reasoning_basis 的 reasoning 字段复用 because_reason（因果说明），避免 GP 填两遍相同内容。
线创建在节点写入之后、返回之前，保证节点存在再连线。
valid_basis 过滤了空字符串和自引用（bid != node_id）。

---

## Step 3：修复 auto_mode 工具名引用 ✅

**状态**：完成

**逻辑**：
auto_mode.py 引用了不存在的 `record_point`/`record_line`/`record_context_point` 工具名。
Yogg 运行时 GP 调用这些工具会被 GP_BLOCKED_TOOLS 拦截（因为不在 unblock 列表中匹配不到实际工具），
或直接报"工具不存在"。修复为现有工具名，让线创建内嵌在 record_lesson_node 中。

**改动**：
- 文件：`auto_mode.py`
- 3 处 `gp_unblock_tools` 从 `["record_point", "record_line", "record_context_point"]` → `["record_lesson_node", "record_context_node"]`
- `record_round` 过滤列表从 `("search_knowledge_nodes", "record_lesson_node", "record_point", "record_line")` → `("search_knowledge_nodes", "record_lesson_node")`
- SPIRAL_PROMPT 中 `record_context_point` → `record_context_node`
- CROSS_MODULE_PROMPT 中 `record_point` + `record_line` → `record_lesson_node`（通过 reasoning_basis 参数连线）

**总结**：
不需要单独的 record_line 工具——线的创建已内嵌在 record_lesson_node.execute() 中（Step 2 实现）。
GP 调用 record_lesson_node 时传 reasoning_basis，execute() 自动创建 reasoning_lines。
record_context_node 是已有工具（RecordContextNodeTool），无需改动。

---

## Step 4：入线数计算 + 搜索输出改造 ✅

**状态**：完成

**逻辑**：
入线数是点线面的价值信号，必须让 GP 在搜索结果和认知目录中感受到拓扑。
改造分两处：get_digest()（认知目录）和 search_tool.py（搜索输出）。
GP 不看到入线数本身（防马太效应），但通过角色标签（基础/探索）感受到。

**改动**：
- `v4/knowledge_query.py` get_digest()：
  - PROVEN/UNTESTED → 基础（高入线数）/ 探索（入线=0）
  - Top 节点按入线数排序而非 usage_success_count
  - 前沿节点 = 入线=0 的最近创建节点
- `tools/search_tool.py`：
  - 搜索结果每个节点内联入线数（`入线:N`），批量查询避免 N+1
  - 圆锥凝实度摘要 → 拓扑密度摘要：`N节点(M基础,K探索) | M条边`
  - 凝实度判定 → 密度判定（基于入线数而非 confidence）
  - VOID 记录 extra 从 cone_density → topo_density

**总结**：
get_incoming_line_counts_batch() 一次 SQL 拿到所有结果节点的入线数，搜索输出零额外查询。
密度判定逻辑：basis_count≥3 + edges≥5 → 高密度，其余递减。
旧 confidence/PROVEN/UNTESTED 语义已被入线数/基础/探索替代，但 confidence_score 字段保留（向后兼容）。

---

## Step 5：碰撞检测（validateInput 扩展） 

**状态**：完成

**逻辑**：
碰撞检测 = 写前去重。GP 准备写新点并连线到 A,B,C，发现 A,B,C 都已有线指向 X → 可能重复。
核心原则：只提醒不阻止。引用相同素材可以写出完全不同的结论，纯集合重叠会误杀合法创新。
find_collision_candidates 已在 Step 1 实现（一次 SQL GROUP BY），此处接入 execute() 流程。

**改动**：
- 文件：`tools/node_tools.py`（RecordLessonNodeTool.execute）
- reasoning_basis 校验通过后、节点写入前，调用 `self.vault.find_collision_candidates(valid_basis, min_overlap=2)`
- 有碰撞候选时：logger.info 记录 + 构造 collision_hint 字符串
- 节点写入成功后，collision_hint 注入返回消息末尾，GP 可看到提醒
- GP 选择：忽略提醒继续写（合法创新）或停止写（标记虚点，Step 7 实现）

**总结**：
碰撞检测的 min_overlap=2 是保守阈值——至少 2 个 basis 重叠才提醒，避免单 basis 共享就误报。
collision_hint 格式：`⚠️ 碰撞检测：你引用的节点已被以下节点引用：[X] 'title' (重叠N个basis)。确认是否重复？`
提醒在写入成功消息末尾，不阻断写入流程。虚点机制（Step 7）将提供"选择不写"的路径。

---

## Step 6：面两阶段组装（expand_surface） ✅

**状态**：完成（含重构）

**逻辑**：
面 = 搜索后处理层，一次性上下文窗口填充。两阶段：先填充基础（水流扩散），再推向前沿（替换策略）。
水流扩散 = BFS 沿高入线数方向走，入线数多的点阻力小 = 已被反复验证的推理通道。
替换策略 = 真正踢掉 fill 中高入线数节点（非追加），加入边缘新点，GP 被推向知识前沿。
先填充基础再推进，不是同时生效。

**改动**：
- 新建 `v4/surface.py`（SurfaceExpander 类）
  - `expand_surface(seed_ids, context_budget, replace_ratio)` → 两阶段组装
  - `_fill_phase(seed_ids, neighbor_map, incoming_counts, budget, excluded_ids)`：BFS 沿高入线数方向扩散，跳过消融/虚点
  - `_push_phase(fill_nodes, frontier_ids, incoming_counts, budget)`：真正踢掉 fill 中高入线数节点，返回 (retained_fill, push_nodes)
  - `_prefetch_neighbors(node_ids)`：委托 `vault.get_neighbor_map()`
  - `_collect_frontier(fill_nodes, incoming_counts, excluded_ids)`：委托 `vault.get_frontier_node_ids()`，过滤消融/虚点
  - `render_surface(surface_result)`：批量获取标题，输出 `title[node_id]` 格式
  - `_check_virtual_saturation(node_ids)`：委托 `vault.get_virtual_saturation()`
  - `_get_ablation_ids(candidate_ids)`：委托 `vault.get_excluded_ids()`
- `v4/manager.py`：新增 4 个公共 API 供 SurfaceExpander 使用
  - `get_neighbor_map(node_ids)`：1-hop 邻居映射（node_edges + reasoning_lines）
  - `get_frontier_node_ids(limit)`：最近创建的非虚拟非消融节点
  - `get_excluded_ids(candidate_ids)`：消融节点集合
  - `batch_get_titles(node_ids)`：批量获取标题
- `tools/search_tool.py`：搜索输出末尾调用 expand_surface + render_surface

**重构要点**：
- surface.py 零 `vault._conn` 直接访问，所有 SQL 查询收归 vault 公共 API
- _push_phase 从假替换（追加）改为真替换（踢掉高入线数节点）
- render_surface 显示 `title[node_id]` 而非纯 ID
- ablation_ids 作为 excluded_ids 传播到 fill_phase 和 collect_frontier
- _collect_frontier SQL 加 `is_virtual=0 AND ablation_active=0` 条件

**总结**：
面组装在搜索结果末尾输出，格式：`[基础] N 个已验证节点：title1[id1], title2[id2]...` + `[探索] M 个前沿节点：...`。
BASIS_INCOMING_THRESHOLD=2：入线数≥2 标记为基础，<2 标记为探索。
虚点饱和信号已接入：`[饱和] XXX 已有 N 个虚点 = 知识饱和`。
面的输出是搜索结果的补充，不替代搜索本身。

---

## Step 7：虚点机制 ✅

**状态**：完成

**逻辑**：
虚点 = 碰撞检测发现重叠时 GP 选择不写新点的占位符。
虚点不注入面（不占上下文），但饱和信号必须注入面——否则 GP 看到沙漠→反复探索已饱和区域→空转。
虚点搜索可见性：只在 1-hop 邻居中出现，不直接被搜索命中。

**改动**：
- `v4/manager.py`：
  - `_ensure_schema()` 新增 `is_virtual INTEGER DEFAULT 0` 列
  - 新增 `get_virtual_saturation(node_ids)` 方法：查 1-hop 邻居中的虚点，按 title 前缀聚合区域
- `v4/surface.py`：
  - `_check_virtual_saturation()` 从 stub 改为调用 `vault.get_virtual_saturation()`
- `tools/search_tool.py`：
  - 搜索结果过滤：`row_dicts = [r for r in row_dicts if not r.get('is_virtual')]`
  - 虚点不直接出现在搜索命中中，仅通过 1-hop 邻居边可见

**总结**：
虚点创建路径尚未完整——GP 碰撞检测后选择不写时，需要一个工具调用 `vault.create_node(is_virtual=1)`。
当前碰撞检测只提醒不阻止，GP 看到提醒后可以选择不继续调用（不写新点），但还没有显式的"标记虚点"操作。
虚点饱和信号已接入面渲染：`[饱和] XXX 已有 N 个虚点 = 知识饱和`。
虚点搜索过滤已实现，is_virtual=1 的节点被搜索结果排除。

---

## Step 8：清理旧架构 ✅

**状态**：完成

**逻辑**：
旧架构残留（圆锥凝实度、PROVEN/UNTESTED、epistemic_status 显示）与点线面体系矛盾。
confidence_score 字段保留（向后兼容，Arena/Evidence Assessor 仍在用），但显示层替换为入线数/角色标签。

**改动**：
- `v4/prompt_factory.py`：`高凝实→直接组装；低凝实→先探索` → `高密度→直接组装；低密度→先探索`
- `v4/knowledge_query.py generate_map()`：PROVEN/UNTESTED → 基础（高入线数）/ 探索（入线=0）
- Step 4 已完成：`get_digest()` + `search_tool.py` 圆锥凝实度 → 拓扑密度

**未清理（保留兼容）**：
- `confidence_score` 字段：Arena/Evidence Assessor 仍在用，不删除
- `epistemic_status` 字段：schema 保留，显示层已替换
- `arena_mixin.py proven_pct/untested_pct`：Arena 统计口径，与点线面不矛盾
- `manager.py create_node epistemic_status 参数`：API 兼容保留，注释标注 phased out

---

## Step 9：真理区分（RAG消融） ✅

**状态**：完成（基础框架，线积累后自然激活）

**逻辑**：
真理区分 = RAG消融。点 A 积累足够入线后，从面和搜索中移除 A，观察 N 轮：
- 向前（缺了 A 仍正确）→ A 是 LLM 内部已有知识 → 降级（ablation_active=2）
- 向后（缺了 A 推理链断裂）→ A 是必要的逻辑跳板 → 确认价值（ablation_active=0）

消融必须同时隐藏搜索结果（否则 GP 通过搜索绕过消融）。

**改动**：
- `v4/manager.py`：
  - `_ensure_schema()` 新增 `ablation_active INTEGER DEFAULT 0` 列
  - `check_ablation_candidates(min_incoming, min_idle_rounds)` → 查找满足消融条件的节点
  - `activate_ablation(node_id)` → ablation_active=1，从面/搜索隐藏
  - `deactivate_ablation(node_id, confirmed)` → confirmed=True 恢复(ablation_active=0)，confirmed=False 降级(ablation_active=2)
- `tools/search_tool.py`：
  - 搜索结果过滤：`row_dicts = [r for r in row_dicts if not r.get('ablation_active')]`
- `v4/surface.py`：
  - `_get_ablation_ids()` → 查询候选中的消融节点
  - `expand_surface()` 中过滤 ablation_ids

**总结**：
ablation_active 状态：0=正常，1=消融观察中，2=已降级（LLM内部知识）。
消融触发条件：入线数≥5 + idle rounds≥3（idle rounds 的精确判断需要 trace 数据，MVP 先跳过）。
消融是后台操作，不由 GP 触发，由 C-Phase 或定时任务触发。
当前线数据为空（刚创建表），消融机制需要线积累后自然激活。
