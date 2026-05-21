# PLS 异步状态探索执行计划

## 结论

PLS 可以异步探索，但不能让多个探索者直接并发修改主拓扑。安全形态是：

```text
异步读 → 异步想 → 异步产 proposal → 单 writer 串行归并主 PLS
```

换句话说，让“现在的探索”并发，让“过去的塑形”串行。

## 当前边界

### 已可并发

- `pls_query` 是只读工具，使用只读 SQLite 连接，可并发执行。
- `V4Loop` 已支持把 `is_concurrency_safe()` 为真的工具用 `asyncio.gather` 并行运行。
- 多方向 LLM scout 可以并发，只要不直接调用写库工具。

### 必须串行

- `record_point`
- `record_line`
- `create_reasoning_line`
- `create_node_edge`
- `ensure_virtual_point`
- `record_potential_samples`
- `resolve_potential_sample`
- `resolve_void`
- `activate_ablation`
- `deactivate_ablation`
- `activate_proactive_pruning`
- `evaluate_proactive_pruning`

这些都会改变 PLS 地形，必须由主流程或单 writer 归并。

## 不变量

### 同轮隔离

同一轮、同一 parent snapshot fan-out 出来的异步 branch，不能互相当作独立验证。它们最多是同代候选，不应直接贡献异轮入线。

### GP 可见性边界

GP 只能看到定性标签：基础、探索、游离、饱和、矛盾、可验证势、出口势。不能把入线数、fusion score、win rate、branch vote 等数字暴露给 GP。

### 势不是事实

`potential_samples` 是弱注意力信号，不是结论、任务或评分。异步 scout 不应无节制写入主 `potential_samples`。

## 当前运行态警报

一次远端 Yogg 只读统计显示：

```text
knowledge_nodes: 4329
node_edges: 7761
reasoning_lines: 5163
potential_samples: 18635
void_tasks: 754
virtual nodes: 452
active ablation/prune: 503
open potentials: 18430
duplicate line pairs: 2
duplicate line rows extra: 16
```

这说明异步化前必须避免三类放大：

- 重复线放大入线数
- 弱势样本膨胀
- 消融/修剪可见性快照漂移

## 顺序执行计划

### Phase 0：只读 PLS terrain scout

目标：每轮开始前并发读取 PLS 地形，生成定性摘要，注入 auto prompt。

约束：

- 只调用 `pls_query`
- 不调用 `search_knowledge_nodes`
- 不写 `potential_samples`
- 不写 `void_tasks`
- 不写主拓扑
- 不暴露数字给 GP

输出示例：

```text
[PLS 地形摘要]
- 基础锚点：...
- 探索前沿：...
- 饱和提醒：...
- 证伪/衰减：...
- 可验证势：...
- 消融可见性：...
```

### Phase 1：多方向 branch proposal

目标：并发运行多个只读探索分支，分别观察基础、出口、反例、missing basis。

约束：

- branch 只产 proposal
- proposal 不直接入主 PLS
- branch 之间不互相验证

### Phase 2：proposal staging

新增 append-only staging，例如：

```text
pls_proposals(proposal_id, parent_trace_id, round_seq, branch_id, proposal_type, payload_json, basis_ids_json, status, merge_result, created_at)
```

### Phase 3：单 writer merge

由单 writer 执行：

```text
pending proposal → rebase → dedupe → visibility check → same-generation check → accept/reject → write main PLS
```

### Phase 4：维护动作队列化

把 C-phase deterministic 写入、ablation、pruning、trace entity merge 逐步迁移到维护队列，由单 writer 处理。

## 第一阶段落地范围

本轮只执行 Phase 0：

- 新增只读 terrain scout 模块
- 在 auto round prompt 前生成 terrain brief
- 将 brief 追加到 `signals`
- 保持所有主写工具串行
- 保持 `search_knowledge_nodes` 非并发

## 验收条件

- Python 语法通过
- terrain scout 在 DB 缺失或查询失败时静默降级
- round prompt 中出现 `[PLS 地形摘要]`
- 不新增任何主 PLS 写入路径
- 不把 raw incoming/fusion/win_rate/count 暴露给 GP

## Phase 0 执行记录

已新增 `genesis/tools/pls_async_scout.py`，并在 `genesis/auto_mode.py` 的每轮 `signals` 构造后注入 `[PLS 地形摘要]`。该 scout 只调用 `PLSQueryTool` 的只读 mode，通过线程池并发读取，不调用 `search_knowledge_nodes`，不写主 PLS。

开关：

- `GENESIS_PLS_TERRAIN_SCOUT`
- `GENESIS_PLS_TERRAIN_SCOUT_TIMEOUT_SECS`

## Phase 1 执行记录

已在 `genesis/tools/pls_async_scout.py` 中新增 `build_pls_branch_proposals()`。第一版不启动额外 LLM 分支，而是基于同一批只读 PLS 查询确定性生成五类候选方向：

- `basis_branch`
- `frontier_branch`
- `falsify_branch`
- `exit_branch`
- `avoid_saturation_branch`

这些 proposal 只进入 auto prompt 的 `signals`，不写 `potential_samples`，不创建 staging 表，不写 `record_point` / `record_line`，也不允许 branch 之间互相验证。

开关：

- `GENESIS_PLS_BRANCH_PROPOSALS`
- `GENESIS_PLS_BRANCH_PROPOSALS_TIMEOUT_SECS`

## Phase 2 执行记录

已在 `genesis/v4/manager.py` 的 `NodeVault._ensure_schema()` 中新增 staging 表 `pls_proposals`：

```text
pls_proposals(
  proposal_id,
  parent_trace_id,
  parent_round_seq,
  branch_id,
  proposal_type,
  source,
  payload_json,
  basis_ids_json,
  status,
  merge_result,
  created_at
)
```

已新增最小 staging API：

- `record_pls_proposal(...)`
- `get_pls_proposals(...)`
- `update_pls_proposal_status(...)`

payload 会在写入时统一为 schema v1：

```text
schema_version
node_id
title
content
point_type
tags
resolves
reasoning
basis_ids
origin
extra
```

`record_pls_proposal(...)` 允许方向性 proposal 暂存为空字段，但会拒绝非法 `point_type` 和内部拓扑数字字段，例如 `incoming_count`、`usage_count`、`fusion_score`、`win_rate`。

边界：

- 只写 `pls_proposals`
- 不写 `knowledge_nodes`
- 不写 `reasoning_lines`
- 不写 `node_edges`
- 不写 `potential_samples`
- 不执行 proposal merge
- 不把 pending proposal 自动当作事实

## Phase 3 执行记录（校验骨架）

已新增 `validate_pls_proposal(proposal_id, update_status=False)`。当前 Phase 3 只做 rebase/安全校验，不做主拓扑归并。

校验内容：

- proposal 是否存在
- candidate node 是否已存在
- basis 是否存在
- basis 是否虚点
- basis 是否处于消融/修剪隐藏状态
- basis 是否来自同一 `parent_trace_id + parent_round_seq`

返回或写回的状态只进入 `pls_proposals.status / merge_result`：

- `validated`
- `needs_rebase`
- `duplicate`
- `unsafe_same_generation`
- `rejected`

边界：

- 不调用 `create_node`
- 不调用 `create_reasoning_line`
- 不调用 `add_edge`
- 不调用 `record_potential_samples`
- 不自动把 `validated` proposal 当作事实

## Phase 4 执行记录（归并预演）

已新增 `preview_pls_proposal_merge(proposal_id)`。当前 Phase 4 只生成 dry-run 归并计划，不执行归并。

预演前置条件：

- proposal 必须通过 `validate_pls_proposal(...)`
- payload 必须提供 `node_id`
- payload 必须提供 `title`
- payload 必须提供 `content`
- `point_type` 必须是 `LESSON` 或 `CONTEXT`
- 必须有有效 `basis_ids`
- payload 必须提供 `reasoning` / `line_reasoning` / `basis_reasoning`

输出只包含计划操作：

- `planned_point_write`
- `planned_line_write`

边界：

- 不调用 `create_node`
- 不调用 `create_reasoning_line`
- 不调用 `add_edge`
- 不调用 `record_potential_samples`
- 不更新 `pls_proposals.status`
- 不写任何主 PLS 拓扑表

## Phase 6 执行记录（观察入口与 staging worker）

已新增 `pls_query mode=proposals`，用于只读观察 `pls_proposals` staging 状态。该模式只展示候选 ID、branch、status、schema、preview blockers 和简短 review，不展示内部拓扑数字，不执行 validation 或 merge。

已新增 `stage_pls_branch_proposals(...)`。该 worker 复用只读 branch scout，把确定性分支候选写入 `pls_proposals`，source 为 `async_branch_worker`。写入内容仍是方向性 proposal：

- 不生成 `node_id`
- 不提供 `basis_ids`
- 不写主拓扑
- validation 会保持 `needs_rebase`

auto 接入开关：

- `GENESIS_PLS_BRANCH_PROPOSAL_STAGING`
- `GENESIS_PLS_BRANCH_PROPOSAL_STAGING_TIMEOUT_SECS`

边界：

- worker 只调用 `record_pls_proposal`
- staging summary 可进入 auto signals，但只说明暂存数量
- proposal 不参与入线数
- proposal 不触发消融
- proposal 不被当作事实
- 主 PLS 仍只允许显式 single-writer commit 改变

## Phase 6 审计修复

自审时发现并修复两个部署完整性问题：

- `stage_pls_branch_proposals(db_path=...)` 不能直接实例化 `NodeVault(db_path=...)`，因为 `NodeVault` 是单例；若进程中已有实例，显式 `db_path` 会被忽略。现在显式 `db_path` 路径使用短连接 sqlite3 只创建/写入 `pls_proposals`，默认 auto 路径仍走 `NodeVault()`。
- 旧版/诊断版 `pls_proposals` 表可能缺 `status`、`branch_id` 等列。现在索引创建发生在补列之后，避免旧表迁移时因缺列失败。

补充回归：

- 显式 `db_path` 不污染既有 `NodeVault` 单例库
- 重复 proposal 不虚报 staged 数量
- 只有 `pls_proposals`、没有 `knowledge_nodes` 的 staging-only 诊断库也可通过 `pls_query mode=proposals` 只读查看
- 旧版 `pls_proposals` 表会先补列再建索引
