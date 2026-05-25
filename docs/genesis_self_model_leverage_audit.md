# Genesis Self-Model Leverage Audit

> 目标：审计现有 auto report / trace / PLS 痕迹是否足以支撑 Genesis 自我概念模型，并为 V6 每用户概率路线 prior 留下可蒸馏的 state-action-outcome 数据地基。
> 结论先行：当前数据足以支持 **signature intuition shadow**；还不足以支持完整 route/policy 小模型。下一步不应改运行时，而应先做 S-A-O 离线编译器/审计器。

---

## 一、防漂移边界

本文不是新路线，不替代 `GENESIS_V6_ROADMAP.md` / `GENESIS_V6_ECOSYSTEM_AUDIT.md` / `GENESIS_V6_STAGE0_RESULTS.md`。

本文只回答一个问题：

> 现有 Genesis 运行痕迹，能否让下一个模型学到“当时是什么状态、选择了什么路线、为什么这样选、结果如何”？

一个后续改动只有满足以下至少一条，才算 self-model leverage：

1. 提高未来路线先验质量。
2. 提高 state-action-outcome 样本可蒸馏性。
3. 提高点/线/面复用与连接质量。
4. 减少训练标签污染。
5. 减少重复探索。

答不上这些问题的治理、报表、自动修复或文档扩写都暂停。

---

## 二、与现有 V6 结论对齐

已有 V6 文档给出的事实：

- `GENESIS_V6_ROADMAP.md`：V6 是把 PLS/trace 痕迹升华为连续参数化 prior，而不是替代 V4/V5。
- `GENESIS_V6_ECOSYSTEM_AUDIT.md`：未通过可学习性审计前，不应修改 `V4Loop`、`SurfaceExpander`、`NodeVault` 或 C-Phase。
- `GENESIS_V6_STAGE0_RESULTS.md`：PLS 痕迹中存在可学习信号，但当前只支持 **signature intuition shadow mode**，不支持 hard gate。

Stage 0 关键结果：

| 方向 | 结论 |
|---|---|
| Signature 预测 | 有明显可学习信号，`error_kind/framework/task_kind/runtime/target_kind` 可优先做 shadow |
| Tool 预测 | 当前弱，不适合作为第一突破口 |
| Failure-aware learning | 暂停，因为 `error_tool_spans=0`，真实失败标签缺失 |
| Runtime 接管 | 暂停，不能 rerank，更不能 hard gate |

因此，本文的审计目标不是“开始训练模型”，而是确认现有轨迹是否能被编译成更好的 S-A-O 数据。

---

## 三、现有轨迹来源

### 3.1 Auto round JSON

写入路径：`runtime/auto_reports/{session_id}/round_*.json`。

代码证据：

- `genesis/auto_mode.py:3339-3350` 创建 `runtime/auto_reports`、session 目录、session JSON。
- `genesis/auto_mode.py:3433-3437` `_write_round_json()` 写每轮 JSON。
- `genesis/auto_mode.py:3847-3950` `RichAutoCallback` 捕捉 callback event。
- `genesis/auto_mode.py:3954-3980` 初始化 `round_record`。
- `genesis/auto_mode.py:4163-4181` 成功轮写入 `phase_trace`、`knowledge_state`、`frontier_state`、`state_freshness`、`pls_telemetry`。

可用字段：

| 字段 | 对 S-A-O 的意义 |
|---|---|
| `prompt_preview` | 输入 state 的截断视图 |
| `knowledge_state` | rolling issue / facts / failed_attempts / next_checks |
| `frontier_state` | 本轮 candidate issue、observations、carry_warnings、next_checks |
| `events` | LLM/tool/c_phase/lens 事件序列 |
| `activity_summary` | 粗粒度 action/outcome 摘要 |
| `progress_class` | error/soft/strong/evidence 粗标签 |
| `outcome_detected` | sandbox diff 变化检测结果，新版字段才稳定 |
| `kb_delta` | 本轮新增/更新知识节点 |
| `phase_trace` | GP/C 消息、current_state_preview |
| `pls_telemetry` | PLS 写入与连线计数 |
| `round_topology` | 点线面时序形态摘要，新版字段才稳定 |

实际样本观察：本地存在 `1686` 个 `round_*.json`。旧样本存在字段不一致问题：部分 round 有 `knowledge_state/frontier_state`，但 `pls_telemetry/round_topology/state_freshness` 为空或缺失。说明历史数据可用，但必须按 schema version/field presence 分层编译，不能假设全量一致。

### 3.2 V4 phase trace / current_state_preview

代码证据：

- `genesis/v4/agent.py:85-93` `UnifiedResponse` 返回 `phase_trace=loop.get_phase_trace()` 与 `knowledge_state`。
- `genesis/v4/loop.py:381-417` `get_phase_trace()` 保留 GP/C 消息、工具调用、inferred_signature、knowledge_state、current_state_preview。
- `genesis/v4/loop.py:422-477` `get_current_state_preview()` 输出 `input_state/routing_state/execution_state/post_round_state_ref`。

`current_state_preview` 已经接近 V6 需要的 state skeleton：

```text
input_state: issue + signature + prompt_surfaces
routing_state: cursor/vector routing + surface summary
execution_state: active_nodes + tool_outcomes
post_round_state_ref: 指向 auto report 的 knowledge_state
```

关键优点：active nodes 带 roles。

代码证据：

- `genesis/v4/loop.py:999-1007` `_mark_active_nodes()` 记录节点角色。
- `genesis/v4/loop.py:895-900` search/open 工具会标记 `tool_suggested/tool_opened`。
- `genesis/v4/loop.py:1066-1124` knowledge routing 通过 cursor/vector + SurfaceExpander 预加载并标记 `routing_seed`。
- `genesis/v4/loop.py:1284-1306` `export_knowledge_cursor()` 只把可复用角色导出给下一轮。

这对 S-A-O 很重要：它能区分“节点被预加载”“节点被搜索建议”“节点被实际打开”，避免把所有可见节点都当作贡献节点。

### 3.3 runtime/traces.db

代码证据：

- `genesis/core/tracer.py:30-75` 定义 `traces` / `spans`。
- `genesis/core/tracer.py:154-178` `end_trace()` 写 trace 级 outcome。
- `genesis/core/tracer.py:270-303` `log_llm_call()` 写 LLM span。
- `genesis/core/tracer.py:304-334` `log_tool_call()` 写工具 span。

本地只读观察：

| 表 | 数量 | 关键字段 |
|---|---:|---|
| `traces` | 6688 | `user_input/status/duration_ms/llm_call_count/tool_call_count/final_response_preview` |
| `spans` | 93969 | `span_type/phase/tool_name/tool_args_preview/tool_result_preview/error/cache_hit_tokens` |

trace DB 适合做低层时序和成本统计，但它缺少 auto round 的 PLS 语义，例如 `frontier_state`、`pls_telemetry`、`round_topology`。因此 V6 数据编译不能只读 `traces.db`，必须联合 auto reports 与 NodeVault。

---

## 四、S-A-O 可蒸馏性评估

### 4.1 State：基本可用，但需要规范化

可用 state 来源：

- 用户输入：`traces.user_input` / `prompt_preview`。
- 当前任务摘要：`knowledge_state.issue`、`frontier_state.local_goal`、`candidate_issue`。
- Signature：`phase_trace.inferred_signature`、`current_state_preview.signature`。
- PLS/routing 上下文：`current_state_preview.prompt_surfaces`、`routing_state`。
- 活跃节点：`current_state_preview.active_nodes`，带 roles。
- 历史状态风险：`state_freshness`、`reanchor_*`、`consecutive_dry`。

判断：State 足够支撑 shadow prior，但需要一个离线 canonicalizer，把不同来源统一成稳定 schema。

### 4.2 Action / Route：有原始事件，缺少路线词表

可用 action 来源：

- `events` 中的 `tool_start/tool_result/llm_call_start/llm_call_end/c_phase_done/lens_*`。
- `phase_trace.gp[].tool_calls` 与 GP/C 消息。
- `round_topology` 中的 anchor timing、points/lines/searches、timeout_risk_shape。
- `knowledge_search_count`、`pls_telemetry`。

当前缺口：

- 工具序列存在，但还没有稳定 route vocabulary。
- `tool prediction` 在 Stage 0 弱，说明不能把“下一工具”当第一目标。
- 更适合先抽象 route family，例如：
  - `inspect_only`
  - `search_then_record`
  - `code_read_then_patch`
  - `test_or_doctor_verify`
  - `pls_point_line_anchor`
  - `self_referential_report_loop`
  - `timeout_runaway`

判断：Action 原始数据足够，但还不能直接训练 route prior。下一步应先做离线 route classifier/auditor，而不是改 prompt 或工具选择。

### 4.3 Outcome：有多种 proxy，但 ground truth 混杂

可用 outcome 来源：

- `status`: completed / timeout / exception / interrupted。
- `progress_class`: error / soft / strong / evidence。
- `outcome_detected`: sandbox diff 是否变化。
- `kb_changed` / `kb_delta`: 是否产生知识变化。
- `c_phase_summary.supplements`: C 是否补充 LESSON。
- `pls_telemetry.points_created/lines_created`。
- `state_freshness.state_stale`。
- trace `duration_ms` / `tool_call_count` / `llm_call_count`。

当前污染源：

- `progress_class=strong` 是 activity proxy，不等于成功。
- `kb_changed=True` 不等于语义进步。
- `outcome_detected=True` 是 sandbox diff 变化，不等于用户价值。
- `traces.status=completed` 只表示运行完成，不等于任务成功。
- `spans.error` 本地 Stage 0 显示真实工具失败标签缺失，不能做 failure-aware learning。
- Arena usage 仍有集体归因风险，不能直接当 per-node label。

判断：Outcome 可用于分层弱标签，但不能合成单一 success 分数。V6 第一阶段应继续使用 signature shadow，不做 reward model。

### 4.4 Point / Line / Surface 连接性：已有计数，缺少样本级因果归因

已有：

- `pls_telemetry` 统计 points/contexts/lines/same_round/cross_round。
- `_summarize_confirmed_pls_results()` 能从 tool result 提取 POINT/LINE 摘要。
- `round_topology` 记录 first point、first anchor、anchor 后工具/搜索/点线形态。
- `current_state_preview.active_nodes.roles` 能区分 routing/search/opened/basis 等角色。

缺口：

- `pls_telemetry` 是计数，不是完整样本。
- `kb_delta` 有新节点/更新节点，但不总是包含“该节点由哪个 state/action 触发”。
- `record_line` result 可解析出新点/依据点，但依赖文本 preview，历史稳定性不足。

判断：足够做 PLS 连接质量审计；还不够做精确 per-node credit assignment。

---

## 五、当前可以学习什么

### 可以学：Signature intuition

已经有 Stage 0 证据支持：

- `error_kind`
- `framework`
- `task_kind`
- `runtime`
- `target_kind`

这些字段适合继续 shadow logging，不影响运行时。

### 可以审计：Route family 分布

不用训练模型，先离线统计：

- 每轮 route family。
- route family 与 `progress_class/outcome_detected/kb_changed/pls_telemetry` 的关系。
- timeout/runaway 是否集中在某些事件形态。
- 产出点线的轮次是否有可识别前置模式。

### 可以审计：S-A-O 字段覆盖率

先统计每个 round 是否具备：

- state: issue/signature/routing/active_nodes
- action: events/tool_calls/round_topology
- outcome: progress/outcome/kb/pls/status
- connection: created points/lines/basis roles

这比继续做新治理模块更贴近 V6。

---

## 六、当前不该做什么

- 不训练完整 MLP。
- 不做 tool prior 运行时接入。
- 不改 Surface 排序。
- 不做 hard gate。
- 不把 `progress_class`、`kb_changed`、`outcome_detected` 合成一个总分。
- 不把 Arena usage 当 per-node ground truth。
- 不把治理报告注入 GP prompt。
- 不自动修复 Yogg deep dive 中的每个问题。

---

## 七、下一步最小补点

### 7.1 新增只读 S-A-O 编译审计脚本

已新增：

```text
genesis/v6/audit_sao_distillability.py
```

只读输入：

- `runtime/auto_reports/*/round_*.json`
- `runtime/traces.db`
- NodeVault `knowledge_nodes/node_content/reasoning_lines`
- `runtime/v6_shadow_predictions.jsonl`

输出：

```text
runtime/v6_sao_distillability_report.json
```

统计：

- round schema coverage
- state/action/outcome/connection 字段覆盖率
- route family 分布
- weak outcome label 分布
- polluted label flags
- signature shadow prediction 可对齐率

本地 smoke test（`--max-rounds 50`）显示：

| 指标 | 结果 |
|---|---:|
| decision | `COLLECT_MORE_SCHEMA_STABLE_ROUNDS` |
| rounds_loaded | 50 |
| state coverage minimum | 0.88 |
| action coverage minimum | 0.0 |
| outcome coverage minimum | 0.0 |
| connection coverage minimum | 0.0 |

主要原因：最近样本仍含大量 legacy round，缺 `outcome_detected`、`pls_telemetry`、`round_topology`。这验证了本文结论：不能直接训练 route/policy 模型，必须先做 S-A-O schema coverage 审计与 canonicalization。

随后脚本已扩展 `schema_stability` 分层：每个 round 会被标注是否同时具备 `state/action/outcome/connection` 四组必需字段，并按 session 汇总候选。

本地 `--max-rounds 200` 结果：

| 指标 | 结果 |
|---|---:|
| decision | `COLLECT_MORE_SCHEMA_STABLE_ROUNDS` |
| rounds_loaded | 200 |
| stable_rounds | 0 |
| stable_ratio | 0.0 |
| top missing | `action:round_topology` = 200 |
| top missing | `outcome:outcome_detected_bool` = 200 |
| top missing | `connection:pls_telemetry` = 200 |
| candidate_sessions | 0 |

解释：这不是样本选择问题，而是当前本地最近 200 个 auto report 属于旧 schema，不能作为 route/policy 训练样本。它们仍可用于历史分析，但不应进入 V6 route prior 的正样本集合。

补充基座测试：`tests/test_v6_sao_distillability.py::test_current_auto_mode_helpers_can_emit_schema_stable_completed_round` 使用当前 `genesis/auto_mode.py` 的真实 helper 构造 completed round，并通过 `round_schema_profile(stable=True)`。这说明本地代码路径已经具备产出 schema-stable round 的能力；`stable_rounds=0` 更可能来自历史报告旧 schema、部署版本未同步、或实际运行尚未产生包含这些字段的新 round，而不是 schema 设计本身不可实现。

因此下一步不是“等 token 堆数据”，而是先确认 live Yogg 是否运行了包含 `outcome_detected` / `pls_telemetry` / `round_topology` 的版本，并用新产生的 round 验证 stable_ratio。

### 7.2 文档暴露问题的 S-A-O 优先级

`docs/yogg_21_23_deep_dive.md` 暴露的问题不应全部展开修复。按 V6 S-A-O 污染风险排序：

| 优先级 | 问题 | 对 S-A-O 的污染 | 当前策略 |
|---|---|---|---|
| P0 | Arena 集体归因 | 把全局 env_ratio 误当 per-node success/fail，污染训练标签 | 不把 Arena usage 当 ground truth；若要处理，先做 per-node attribution audit，不直接改奖惩 |
| P0 | outcome 语义混杂 | `completed/strong/kb_changed/outcome_detected` 容易被误合成成功 | 已在 audit 中拆成 weak labels 与 pollution flags，不合成总分 |
| P1 | ENV_FACT 新鲜度 | 旧 cwd/user/host 当当前状态，污染 State | 保持 dry-run freshness；必要时只补验证证据，不自动改写事实 |
| P1 | CONTRADICTS 消解真空 | 冲突节点同时作为候选知识进入 Surface，污染 State/Connection | 保持 dry-run contradiction report；不自动消解，但训练样本要打 conflict flag |
| P2 | witness/lineage 断裂 | 新节点难以归因到具体 state/action | 先用 `active_nodes.roles`、`kb_delta`、`round_topology` 做弱连接，不做精确 credit assignment |
| P2 | tool cost 零消费 | 影响路线成本先验，但不直接决定标签真伪 | 暂不作为 V6 第一目标 |

已实现最小解决：`audit_sao_distillability.py` 新增 `training_readiness` 层，不改 Arena、不改 Surface、不改运行时，只在训练样本进入 V6 前做过滤：

- `route_policy_candidate`: schema 稳定且 completed 的 route-level 候选。
- `per_node_credit_candidate`: 进一步排除 Arena 集体归因/冲突风险后的 per-node credit 候选。
- `review_required`: ENV_FACT、CONTRADICTS、Arena 归因等需要人工或专门审计的样本。
- `exclusion_reasons`: 直接排除训练的原因，例如 legacy schema、missing outcome、missing topology。
- `review_reasons`: 不排除 route-level 训练，但禁止进入 per-node credit 的原因。

本地 `--max-rounds 200` 训练就绪统计：

| 指标 | 结果 |
|---|---:|
| route_policy_candidates | 0 |
| per_node_credit_candidates | 0 |
| review_required | 18 |
| `schema_not_stable` | 200 |
| `missing_outcome_detected` | 200 |
| `missing_connection_or_topology` | 200 |
| `conflict_sensitive_sample_requires_contradiction_flag` | 11 |
| `environment_state_requires_freshness_check` | 7 |

这意味着：当前不是把文档问题搁置，而是先把它们转成 V6 训练闸门。等 live Yogg 产生 schema-stable 新样本后，这些 flag 会直接决定样本能否进入 route policy 或 per-node credit 数据集。

### 7.3 暂不改 auto_mode 运行逻辑

如果审计发现字段缺口，再考虑最小补字段。补字段必须满足：

- 不改变 GP prompt。
- 不改变 tool execution。
- 不改变 PLS routing。
- 不改变 Arena 更新。
- 只让 future rounds 更可蒸馏。

### 7.4 候选最小字段，不立即实现

如果审计证明需要，可考虑在 round JSON 中新增一个顶层派生字段：

```python
"sao_summary": {
  "schema": "genesis.sao_summary.v1",
  "state_refs": {...},
  "route_family": "...",
  "outcome_labels": [...],
  "connection_labels": [...],
  "pollution_flags": [...]
}
```

但这必须先由离线脚本验证价值，不能直接手写进 auto loop。

---

## 八、结论

Genesis 已经留下了足够多的自我运行痕迹，能支持 V6 的第一阶段：**signature intuition shadow**。

但完整“概率路线模型”还缺两个地基：

1. **Action/Route 规范化**：从原始工具事件抽象出稳定 route family。
2. **Outcome 弱标签分层**：区分运行完成、工具活动、沙箱变化、知识写入、语义收束、用户价值，不能合成总分。

因此下一步最符合杠杆定义的动作是：

> 做只读 S-A-O distillability audit，先证明哪些历史 round 能成为训练样本，再决定是否补最小字段。

这会直接服务 V6 每用户小模型，而不是继续扩张治理层或追逐 Yogg 的单点问题。
