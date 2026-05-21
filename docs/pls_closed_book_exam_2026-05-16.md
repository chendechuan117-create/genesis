# PLS 闭卷测试 — 基于 YOGG_LIVE_PLS_CLAIMS_LEDGER.md lines 1-498

> 测试日期：2026-05-16
> 材料范围：`docs/YOGG_LIVE_PLS_CLAIMS_LEDGER.md` 1-498 行
> 约束：未读取第 499 行之后内容；预测题均为盲预测

---

# A. 基础理解题

## 1. 前半段中心论断

前半段不是一般 PLS 理论，而是在证明 live Yogg/Genesis 的许多观测表面把"叙事性写入/推荐/快照/自报"伪装成事实，被 prompt、排名、健康度和治理逻辑消费。这是 PLS 问题，因为这些表面会成为未来思考的 Point/Line/Surface 输入，污染后续认知，而不只是单表数据脏。

---

## 2. 三组概念区分

### a. `narrative field` vs `fact field`

`narrative field` 是系统写入的一段"声称如此"的叙事；`fact field` 应该绑定可复核的当前观察或执行事件。例子：`MEM_CONV` 看起来像用户-GP 对话历史，但前半段指出它约 `99.7%` 是 `auto_mode` 注入，原始用户输入只有 `0.3%`。工程后果是：如果把它当事实历史，prompt 会把系统剧本误读成用户意图。

### b. `write-side claim` vs `execution event`

`write-side claim` 是写节点时顺手填入的字段；`execution event` 是独立执行者实际验证后的事件记录。例子：`last_verified_at` / `verification_source` 可以由 `record_point` / `record_meta_node` 在写入侧填充，不证明 verifier 真跑过。工程后果是：健康指标如果只数这些字段，会在 verifier 死亡后反而显示"健康"。

### c. `recommendation/preload` vs `actual consumption`

推荐/预载只是节点被放进候选、active set 或 prompt 表面；实际消费必须证明 GP 读了、引用了、作为 reasoning basis 使用了。例子：`execution_active_nodes` 被判定为 recommendation/preload membership，不是 GP 实际引用内容的证据。工程后果是：`usage_count` 高可能只是广播或预载，不代表知识真的有用。

---

## 3. 不应直接当事实的字段/表面

| 类别 | 项目 | 看起来像什么 | 实际更可能是什么 |
|---|---|---|---|
| prompt/history | `MEM_CONV` | 用户-GP 对话历史 | composite prompt trace：用户输入 + auto 注入 + system frame + knowledge state |
| prompt/history | `EPISODE` | 对话轮次或因果记忆 | 触发器化石，现代 EPISODE 与 LESSON 生产缺少因果连接 |
| prompt/history | `carry_warnings` in `MEM_CONV` | 用户或对话历史内容 | auto_mode 注入框架污染 |
| state/liveness | `process_heartbeat.status` | 当前进程存活状态 | last-written snapshot，死 PID 仍可显示 running/idle |
| state/liveness | `get_daemon_status_summary()` | 当前 daemon 状态摘要 | 读取 heartbeat 行，缺少 PID liveness / expiration |
| state/liveness | `persona_stats` | 渐进学习统计 | 批量初始化后冻结的快照，且可能无现代 consumer |
| verification/health | `last_verified_at` | 真实验证时间 | `claimed_verified_at`，写入侧叙事字段 |
| verification/health | `verification_source` / `auditor_daemon` | 独立 verifier 来源 | 写入标签或 verifier 内部 method label，不必是独立进程 |
| verification/health | `nodes_verified_last_week` | 最近验证量 | 最近 verification timestamp 数量，可能是 GP 自报/default |
| verification/health | `growth_rate='healthy'` | 系统健康 | 写活动 proxy，可能与验证质量反向 |
| retrieval/VOID | `VOID_SEARCH` | 真实知识缺口 | retrieval failure / exact-id miss / filter hidden / malformed reference / resolver mismatch 混合 |
| retrieval/VOID | exact node-id void | 节点不存在 | token split 或 visibility filter 导致 exact lookup 失败 |
| topology/usage | `usage_count` | 实际消费次数 | C-Phase calls、recommendation/preload、virtual collisions 等混合 |
| topology/usage | `usage_success_count` | 节点成功贡献 | round-level `env_ratio` 广播给 active nodes |
| topology/usage | `execution_active_nodes` | GP 实际使用节点 | recommendation/preload membership |
| topology/usage | `CONTRADICTS` | 长期证伪/衰减 | intraday correction rhetoric 或 high-attention marker |
| proposal/staging | `pls_proposals` | live PLS proposal 内容 | schema 完整但 live-zero，staging disabled |

---

# B. 机制推理题

## 4. 为什么 `MEM_CONV` 不能当作用户-GP 对话历史？

**直接证据：**

- 原始用户输入只占约 `0.3%` 字符。
- `auto_mode` 注入占约 `99.7%`，约为用户输入 `324x`。
- `carry_warnings` 出现在 `MEM_CONV`，但不在 raw user input。
- `EPISODE` 也被判定更像 trigger fossil，不是对话参与者。

**从单点问题到系统性 frame pollution：**

系统把 auto 指令、知识状态、警告、surface、void surface 和工具摘要混入"历史"。未来 GP 若把它当 conversation，会把系统自我注入误读成用户长期意图。

**会污染的下游判断：**

- 用户意图判断。
- task continuity / directive 解释。
- PLS surface 注入。
- C-Phase 反思归因。
- health / production / usage 的因果解释。
- 后续节点写入的 reasoning basis。

---

## 5. 为什么 verification 字段不等于 verification event？

**前半段证明：**

verifier death 后，`auditor_daemon` 占比从约 `10.0%` 掉到 `0.2%`，`command_output` 和 `gp_point` 扩大；同时仍出现 post-death `auditor_daemon` writes，包括 temporal-travel pattern。机制是 `record_point` / `record_meta_node` 可在写入时接受 `last_verified_at` 和 `verification_source`，不绑定真实 verifier 执行。

**最小真正 verification event：**

```text
event_id
executor
tool_or_process
target_node_or_artifact
input_or_artifact_hash
observed_output_or_hash
result
timestamp
failure_reason
```

**对 health metric 的影响：**

健康不能数 `last_verified_at` 字段存在；应数独立 verification events，并区分 executor identity、成功率、失败原因、schema-default confidence 占比。否则会把"写得多"误报成"验证得好"。

---

## 6. 为什么 production pulse / Gini 不能单独解释系统健康？

**稳定子论断：** Gini、节点产量、production distribution 会隐藏 verification-state fracture 和 temporal/block structure。

**被部分 contest 的因果解释：** `verifier death -> governance vacuum -> pulse production` 不稳定。前半段记录后续节点指出 daemon death 和 pulse start 相隔约 `27` 天，中间有 zero-output periods，首个 pulse 带 `read_file` 等 task signatures，更像 task-event driven。

**正确 dashboard 应拆开：**

- production volume。
- temporal regime：zero / low / mid / pulse 等。
- verifier state / executor identity。
- confidence 是否 schema default。
- task-event signatures。
- block/day weighting。
- verification quality。

---

## 7. 为什么 `usage_count` 不等于实际消费？

**至少三种混入语义：**

- `usage_success_count` 是 round-level `env_ratio` 广播到 active nodes。
- `usage_count` 混入 neutral C-Phase calls。
- `usage_count` 混入 VIRT saturation collisions。
- 还混入 recommendation/preload paths。

`execution_active_nodes` 也不能当消费证据，因为它只说明节点进入推荐/预载集合，不证明 GP 实际读内容、引用内容或据此推理。

**拆分后的 schema：**

```text
recommended_count
preloaded_count
shown_in_prompt_count
actual_citation_count
reasoning_basis_count
arena_broadcast_success_count
arena_broadcast_failure_count
virtual_collision_count
```

---

# C. PLS 判断题

## 8. VOID 应如何降级？

`VOID` 是"未解决的 retrieval/gap claim"，不是纯粹知识缺口，更不是系统真实无知识的证明。

进入 prompt 前应标注 provenance，例如：

```text
VOID_CLAIM / unresolved_gap_or_retrieval_failure
reason_category=...
```

**至少 5 个可能来源：**

- `retrieval_failure`
- `exact_id_not_found`
- `hidden_by_visibility_filter`
- `ablation_or_contradiction_filtered`
- `malformed_reference`
- `semantic_gap`
- `resolver_mismatch`

**exact node-id lookup 应与 fuzzy search 分离：**

结构化 ID 查询必须绕过 tokenization，并报告：

```text
exists_visible
exists_but_filtered
not_found
malformed_id
```

不能把 exact ID 被 filter 或 token split 后的失败直接写成 semantic gap。

---

## 9. `CONTRADICTS` 为什么不能直接当长期 falsification / decay？

**时间分布证据：**

- `73.5%` LESSON-to-LESSON `CONTRADICTS` 同日发生。
- `86.5%` 在 24 小时内发生。
- `77.2%` 是 new-to-old。
- timing 类似 `RELATED_TO`。
- contradicted nodes 可能有更高 `usage_count`。

所以它更像短视窗自我修正、语义重涂或 high-attention marker，而不是跨时间的 durable falsification。

**进入 PLS 时应标为：**

```text
controversy / correction / attention marker
```

在没有外部 adjudication 前，不能用于删除、衰减或 invalidation。

---

## 10. 为什么 `reasoning_lines`、`node_edges`、`usage_count` 必须分轨审计？

**三者含义不同：**

- `reasoning_lines`：GP 的 reasoning-connection substrate。
- `node_edges`：可视化或晶体化 topology。
- `usage_count`：C-Phase execution density / recommendation-related activity，且与实际消费正交。

**坍缩成 `knowledge vitality` 会误判：**

- 把预载节点当被消费。
- 把争议/注意力节点当坏节点。
- 把设计型孤儿当失败节点。
- 把 topology 缺边当推理无用。

**最小审计表头：**

```text
node_id
node_type
created_at
reasoning_line_in
reasoning_line_out
node_edge_in
node_edge_out
edge_relations
recommended_count
preloaded_count
shown_in_prompt_count
actual_citation_count
reasoning_basis_count
arena_broadcast_success_count
arena_broadcast_failure_count
virtual_collision_count
visibility_state
ablation_state
claimed_verification_source
verification_event_count
```

---

# D. 预测题：对后半段的盲预测

> ⚠️ 以下均为盲预测，未读取第 499 行之后内容。

## 11. 后半段最可能继续发现的三类新污染面

### 1. control-plane / directive pollution

- **可能表面**：auto directive、mode selector、fallback focus、planner output。
- **看起来像**：Yogg 自主策略、用户长期目标、运行时意志。
- **实际可能是**：auto_mode fallback、prompt frame、planner stale result 或模式选择器。
- **自然延伸**：前半段已显示 prompt-history、state、health 字段进入决策位；下一步自然是控制平面本身被叙事字段污染。

### 2. runtime/report pollution

- **可能表面**：tool result summary、`command_output`、execution report、trace summary。
- **看起来像**：真实执行证据。
- **实际可能是**：工具包装层摘要、GP 自报、截断输出、失败路径残留或 write-side verification label。
- **自然延伸**：verification 字段已被证明不是 event；下一层会检查"报告本身"是否也只是叙事化执行表面。

### 3. type/schema ecology pollution

- **可能表面**：node type、source、trust tier、metadata signature、confidence default。
- **看起来像**：稳定语义分类和 provenance。
- **实际可能是**：writer path default、schema migration artifact、source label reuse、默认置信度。
- **自然延伸**：前半段反复显示同一字段承载多重语义；后半段很可能推进到类型和 schema 生态层面的语义漂移。

---

## 12. 最可能被后半段 refine 的 3 条 claim

### 1. VOID pollution

会 refine，因为前半段已从 token split 细化到 SQL exclusion filter，不可能只停在一个根因。预测方向：进一步拆成 exact-id resolver、visibility filter、ablation filter、semantic search、natural-language gap 等通道矩阵。

### 2. usage_count 不等于 consumption

会 refine，因为前半段已经列出 triple semantic collapse 和 active_nodes recommendation 层。预测方向：细化每个 counter 的具体写入路径，以及哪个路径进入 prompt、哪个路径只是 arena broadcast。

### 3. verification 字段不是 event

会 refine，因为 `auditor_daemon` 已被细化为 internal method label，而非独立进程。预测方向：进一步区分 `claimed_source`、writer function、actual executor、runtime trace、artifact hash。

---

## 13. 最可能被后半段 contest 的 2 条 claim

### 1. pulse production 的 governance-vacuum 因果解释

- **风险**：前半段已经显示该因果链被 contest。
- **metric observation**：production pulse 和 Gini/regime fracture 存在。
- **causal interpretation**：不一定是 verifier death 导致 governance vacuum；可能是 task-event driven。
- **engineering implication**：仍应拆开 production 和 verification，不从 volume 推健康。

### 2. `CONTRADICTS` 主要是 attention marker

- **风险**：高 usage 也可能来自争议节点被反复检查，不必然是"有价值 attention"；部分 `CONTRADICTS` 也可能确实是局部 falsification。
- **metric observation**：同日/24h/new-to-old 分布稳定。
- **causal interpretation**：attention marker、correction rhetoric、真实局部反证可能混合。
- **engineering implication**：仍不能直接删除；应降级为候选 controversy signal，等待 adjudication。

---

## 14. 最可能推进到哪个层级？

选择：

```text
a. control-plane pollution
```

**理由：** 前半段的统一模式不是"某些表坏了"，而是 narrative fields 被放进 prompt、ranking、health、governance 等 fact/control positions。自然下一步是：这些污染表面如何改变 Yogg 的选择、继续方向、任务调度和自我治理。

**另外两个方向也可能出现但不是主线：**

- **type/schema ecology pollution**：很可能出现，因为字段多义和 schema default 已经反复出现；但它更像控制污染的底层原因。
- **runtime/report pollution**：也可能出现，因为 verification/event 问题会逼近 execution reports；但前半段主线更关心这些报告如何被消费进控制面。

---

# E. 应用题

## 15. 只读 dashboard 设计

不使用 report-wide grep 作为主方法。主方法应是 live DB structured read：查询 `knowledge_nodes`、`node_contents`、`reasoning_lines`、`node_edges`、`point_creation_context`、`void_tasks`，必要时只读关联 runtime traces。只检查 live prompt/render path 的实际输入，不把 docs、ledger、历史总结里的词频当污染证据。

| field name | surface category | claimed meaning | observed provenance | possible artifact source | downstream consumer | risk if rendered as fact | recommended downgrade label |
|---|---|---|---|---|---|---|---|
| `MEM_CONV` | prompt/history | conversation history | raw/user vs auto injected char ratio | auto_mode injection, carry_warnings, knowledge_state | GP prompt, continuity logic | system frame 被误当用户意图 | `composite_prompt_trace` |
| `last_verified_at` | verification | verified timestamp | writer path vs executor event match | record_point/write-side metadata | health, ranking | self-report 被当验证 | `claimed_verified_at` |
| `verification_source` | verification | verifier identity | source label + actual process evidence | gp_point, command_output, auditor method label | trust, health | source label 替代 executor | `claimed_verification_source` |
| `void_tasks` / `VOID_SEARCH` | retrieval/VOID | knowledge gap | exact-id lookup / filter / resolver category | token split, exclusion filter, malformed ref | prompt void surface, task focus | false gap 驱动错误探索 | `unresolved_gap_or_retrieval_failure` |
| `usage_count` | topology/usage | actual consumption | counter write path classification | arena broadcast, preload, C calls, VIRT collision | ranking, vitality | 推荐被误当使用 | `mixed_activity_counter` |
| `execution_active_nodes` | topology/usage | used nodes | active-set source vs citation evidence | recommendation/preload list | arena, prompt | active membership 被当消费 | `recommended_or_preloaded` |
| `CONTRADICTS` | topology/decay | falsification | edge time delta + direction + external adjudication | intraday correction rhetoric | decay/delete/governance | 注意力边被当淘汰信号 | `controversy_attention_marker` |
| `pls_proposals` | proposal/staging | live staged proposals | row count + staging flag | disabled schema channel | PLS governance | 空表被当 live content | `dead_or_disabled_channel` |

**避免误判 live prompt pollution：**

- 只看实际 prompt assembly 输入或运行 trace 中被注入的内容。
- 区分 docs/ledger/source-code mentions 与 DB live rows。
- 对每个字段记录 `observed_in_prompt=true/false`。
- 对 historical docs 做 explicit exclusion，不作为 live prompt surface。
- 对同名 repo-local DB 与 live `~/.genesis/workshop_v4.sqlite` 分离。

---

## 16. 阻止盲修 `VOID_SEARCH`

**VOID 闭环：**

```text
query / reference
-> search / resolver / visibility filters
-> miss classification
-> void_tasks or VOID_SEARCH write
-> prompt void surface / next focus
-> GP investigates or records new point
-> possible resolution / deletion / persistence
```

**至少 4 种 false VOID 来源：**

- exact node ID 被 token split。
- SQL exclusion / visibility filter 隐藏了存在节点。
- ablation / contradiction filter 导致候选被排除。
- malformed reference。
- resolver mismatch：该走 exact lookup 却走 fuzzy search。
- local/fixture DB 与 live DB 混淆。
- semantic threshold miss。

**只修 token split 不够：** 前半段已经说明后续 root cause 被 refine 到 SQL exclusion filter；false VOID 是多通道混合，不是单 tokenizer bug。

**Patch admission rule：**

```text
任何 VOID_SEARCH patch 必须先只读分类现有 void 来源，
并证明 exact-id、fuzzy semantic、visibility-filtered、malformed-reference、resolver-mismatch
会被分别标注；不得把 hidden/existing 节点继续写成 semantic gap；
不得降低 true semantic_gap 的捕获率。
```

**只读验证计划：**

- 抽样 `void_tasks`，按 ID-like vs natural-language 分类。
- 对 ID-like 样本直接查 `knowledge_nodes.node_id`，绕过 fuzzy。
- 对同一 query 跑 with-filter / without-filter 对比。
- 统计 `exists_visible`、`exists_hidden`、`malformed`、`true_absent`。
- 追踪这些 void 是否进入 prompt surface。
- 不写库，只产出分类报告。

---

## 17. 评审"把 `CONTRADICTS` 直接用于节点淘汰"

**很危险，因为前半段显示：**

- 大多数 `CONTRADICTS` 是同日或 24h 内。
- 多为 new-to-old。
- timing 类似 `RELATED_TO`。
- contradicted nodes 反而可能更高 `usage_count`。
- 当前没有外部 adjudication。

**缺失证据：**

- 独立 verifier 失败事件。
- 被 contradiction 后任务表现下降的证据。
- 删除/降权 ablation 的正收益。
- 人工或外部模型裁决。
- cross-time durable falsification，而非 session-local correction。

**如果必须使用，应降级为：**

```text
candidate_controversy_signal
```

可进入 review queue、提示"需复核"，不能直接删除。

**需要的机制：**

- verifier event。
- A/B prompt ablation。
- human adjudication 或 independent model adjudication。
- contradiction edge 类型细分：correction、supersession、attention、hard_falsification。
- 与 actual consumption 和 task outcome 联动。

---

## 18. 反驳"节点增长很快，说明 Yogg 变好了"

**反驳点（基于前半段至少 4 条 claim）：**

1. `Production regime and pulse metrics`：node count / Gini 会隐藏 verification fracture。
2. `Health metric sign inversion`：最近 verified count 可在验证质量崩溃时显示 healthy。
3. `Verification fields`：`last_verified_at` 只是 write-side claim，不是 verifier event。
4. `Usage metrics`：`usage_count` 不等于实际消费。
5. `VOID`：大量 VOID 可能是 retrieval failure，不是高质量探索方向。
6. `pls_proposals`：schema 存在不等于 live content。

**区分四个维度：**

- **production volume**：写了多少节点。
- **verification quality**：是否有独立 executor/event。
- **actual consumption**：是否被 GP 引用、作为 reasoning basis。
- **topology vitality**：reasoning_lines、node_edges、usage 分轨，而非总分。

**更合理组合：**

```text
new_nodes
+ verification_event_success_rate
+ non-default confidence ratio
+ executor diversity
+ actual_citation_count / reasoning_basis_count
+ false_VOID_rate
+ contradiction_adjudication_rate
+ reasoning_line and node_edge separate vitality
+ downstream task outcome / ablation result
```

---

# F. 元认知题

## 19. 最重要的 PLS 启发

选择：

```text
c. PLS 的关键是区分不同表面的语义角色和证据来源
```

**为什么其他错：**

- **a 错**：更多表不能解决问题；`pls_proposals` 就是 schema 完整但 live-zero，`STATE` 表也可能是 zombie snapshot。
- **b 错**：总分会重复 `usage_count`、Gini、health metric 的错误，把不同语义轨道坍缩。
- **d 错**：前半段恰恰证明 Yogg 不能自动相信自己的长期产出，因为很多字段是 narrative claim。
- **c 对**：live audit 的核心是区分 conversation vs prompt trace、verification field vs event、recommendation vs consumption、CONTRADICTS vs falsification。

---

## 20. 后续工程原则

```text
凡是由写入侧生成、复用为多义计数或叙事快照、且没有绑定独立执行/当前观测事件的字段，
默认不得进入事实位或控制位，除非先标注 provenance 并通过对应事件轨道验证。
```

**覆盖范围：** 至少覆盖 `MEM_CONV`、`last_verified_at`、`verification_source`、`process_heartbeat`、`usage_count`、`VOID_SEARCH`、`CONTRADICTS`。
