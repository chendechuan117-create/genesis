# Genesis Bottleneck Map

> 2026-05-16
>
> 本文是 Genesis / Yogg 当前系统瓶颈的结构图。它不是补丁计划，也不是新架构提案；它的目的，是把主要反馈闭环、耦合点、停止修复区域、可安全观察区域和下一步非侵入运行模式写清楚。

---

## 0. 一句话判断

Genesis / Yogg 当前的主要瓶颈不是“不会产出”，而是：

```text
自观察闭环已经形成，但 prompt / state / DB / report / tool_result / runtime log 等表面没有足够强的语义分层。
```

结果是局部修复经常变成：

```text
修 A 表面
  -> 改变 B 闭环输入
  -> 被 C prompt 回灌
  -> 在 D report / memory / VOID 中重新变成新信号
  -> 下一轮又被当作系统事实或任务方向
```

因此“修不如不修”的感觉不是错觉，而是闭环系统进入生态治理期后的正常风险信号。

---

## 1. 适用范围

本文覆盖以下反馈面：

- **Auto mode**：`genesis/auto_mode.py` 中的 session loop、signals、planner、round state、SelfEvolution。
- **Prompt assembly**：`genesis/v4/prompt_factory.py` 和 auto prompt 中的 knowledge state / rolling state 渲染。
- **NodeVault / PLS**：`genesis/v4/manager.py`、knowledge nodes、node contents、edges、reasoning lines、void tasks。
- **Knowledge query**：搜索、digest、surface expansion、VOID 暴露。
- **Self-evolution**：Doctor sandbox、test-diff、cooldown、apply、rollback、canary / review 路线。
- **Runtime**：Yogg auto session、provider failures、OOM、Discord reconnect、systemd restart、auto reports。

本文不覆盖：

- 新功能设计。
- 代码补丁方案。
- DB schema migration。
- provider 供应商策略。
- Yogg 远端部署操作手册。

---

## 2. 系统总体闭环

```text
                 ┌──────────────────────────────┐
                 │        Runtime / Logs         │
                 │ provider / OOM / reconnect    │
                 └──────────────┬───────────────┘
                                │
                                ▼
┌─────────────┐       ┌──────────────────┐       ┌────────────────────┐
│  NodeVault  │──────▶│  Auto Signals    │──────▶│  Prompt Assembly   │
│ nodes/edges │       │ DB/VOID/errors   │       │ auto + factory     │
└──────┬──────┘       └──────────────────┘       └─────────┬──────────┘
       ▲                                                     │
       │                                                     ▼
┌──────┴──────┐       ┌──────────────────┐       ┌────────────────────┐
│ C-Phase /   │◀──────│  Agent Process   │──────▶│ Tool Calls / Shell │
│ knowledge   │       │ GP + Op + C      │       │ doctor / record_*  │
│ production  │       └──────────────────┘       └─────────┬──────────┘
└─────────────┘                                             │
                                                            ▼
                                                   ┌────────────────────┐
                                                   │ Sandbox / Reports  │
                                                   │ diff / JSON / MD   │
                                                   └─────────┬──────────┘
                                                             │
                                                             ▼
                                                   ┌────────────────────┐
                                                   │ SelfEvolution      │
                                                   │ test/apply/restart │
                                                   └────────────────────┘
```

关键点：

```text
这些模块不是线性流水线，而是互相回灌的生态系统。
```

同一个字符串、节点、VOID、report 片段、error line，可能同时是：

- 观测材料。
- prompt 输入。
- 任务方向。
- 知识候选。
- 报告指标。
- 下次修复的依据。

这就是耦合放大的来源。

---

## 3. 六个主反馈闭环

### 3.1 Prompt / signal 注入环

```text
DB / VOID / current errors / PLS terrain
-> _get_auto_signals()
-> AUTO_PROMPT_FIRST / AUTO_PROMPT_CONTINUE
-> agent.process()
-> tool calls / record_* / response
-> DB / reports / next signals
```

主要表面：

- `current errors`
- `recent VOID`
- `knowledge_state`
- `frontier_state`
- `round_log`
- `planner_result`
- `fallback focus`

瓶颈：

```text
_auto_signals 同时承担观测、解释、优先级和控制作用。
```

风险：

- 一个 wording 修复可能改变探索方向。
- 一个 false VOID 可能变成下一轮任务。
- 一个 runtime error 可能被当作认知缺口。
- 一个 report artifact 可能被 prompt 重新消费。

健康边界：

```text
Signal 应该只说“观察到什么”，不直接暗示“应该做什么”。
```

---

### 3.2 Rolling state 回灌环

```text
round result knowledge_state
-> last_knowledge_state / last_good_knowledge_state
-> runtime/.auto_session_memory.json
-> session recovery
-> _format_knowledge_state()
-> prompt
-> next round behavior
```

主要表面：

- `last_knowledge_state`
- `last_good_knowledge_state`
- `.auto_session_memory.json`
- `FactoryManager.render_knowledge_state()`
- `_format_knowledge_state()`

近期症状：

- 旧的强语义标签能从 rolling state 中复活。
- 修 prompt factory 后，仍可能被 auto state 回灌。
- sanitizer 本身又可能被 report-wide grep 误报。

根耦合：

```text
persisted state 缺少语义 epoch / provenance / schema_version。
```

当前修复只能降低渲染污染，但没有完全解决：

```text
这个 state 是谁产生的？
它是观察、建议、判断，还是历史残留？
它该不该进入下一轮 prompt？
```

健康边界：

```text
Rolling state 只能作为 rolling_state_proxy，不应冒充 verified fact 或 stable knowledge。
```

---

### 3.3 Knowledge write / MEM_CONV 环

```text
prompt + response + tool evidence
-> C-Phase / record_point / record_line / store_conversation
-> knowledge_nodes / node_contents / node_edges
-> search / digest / surface
-> prompt
```

主要表面：

- `LESSON`
- `CONTEXT`
- `EPISODE`
- `MEM_CONV_*`
- `reasoning_lines`
- `RELATED_TO / REQUIRES / RESOLVES / TRIGGERS`

历史观察：

- C-Phase 写入能力强。
- 写入端不是唯一瓶颈。
- 消费端、反馈端和拓扑可见性更容易成为瓶颈。
- Yogg 曾出现 LESSON 比例极高、CONTEXT/trace 层不足、Arena 没有充分生效的症状。

根耦合：

```text
运行痕迹、认知结论、工具证据、prompt artifact 被写入同一知识生态。
```

风险：

- Auto session fossil 被当作概念知识。
- 工具 trace 被当作稳定经验。
- Prompt 中的 disclaimer 被后续当作知识材料。
- 写入量上升掩盖消费质量下降。

健康边界：

```text
知识节点应区分 concept / runtime_fossil / tool_evidence / prompt_artifact / self_observation。
```

---

### 3.4 VOID 创建 / 解决环

```text
search miss / weak retrieval
-> void_tasks
-> recent VOID signals
-> prompt sees “knowledge gap”
-> GP explores / writes node
-> resolve_matching_voids_for_node()
-> future search / prompt
```

主要表面：

- `void_tasks`
- `open / resolved / stale`
- `recent voids`
- `loose hit`
- `false VOID`

瓶颈：

```text
VOID 是 retrieval artifact，不一定是真实知识空洞。
```

false VOID 的常见来源：

- query phrase 不稳定。
- exact id miss。
- LIKE / tokenization 失败。
- 可见性过滤。
- 搜索路径没有覆盖真实写入路径。
- 旧 VOID 已被旁路知识满足，但没有 resolve。

风险：

```text
检索失败一旦进入 prompt，就会从 retrieval artifact 变成 exploration directive。
```

健康边界：

```text
VOID 进入 prompt 前应标明 source=retrieval_miss，semantic_gap=unknown。
```

---

### 3.5 PLS surface / topology 环

```text
seed nodes
-> surface expansion
-> qualitative topology labels
-> GP limited context
-> new lines / nodes
-> topology changes
-> next surface
```

PLS 当前权威原则：

- 价值信号来自拓扑，不来自单一数字评分。
- Growth = 入线依赖。
- Decay = CONTRADICTS / supersession。
- Density = 饱和 / repeated path overlap。
- GP 应看到定性标签，不应被 numeric incoming_count / fusion_score / win_rate 直接驱动。

瓶颈：

```text
PLS 是选择有限上下文的价值投影系统，不是所有运行事实的垃圾桶。
```

风险：

- 把密度假设当成“无需探索”。
- 把入线数重新包装成分数排序。
- 把 runtime artifact 混入 surface。
- 把 reasoning line 全量注入 normal prompt。

健康边界：

```text
Surface 负责“什么值得被看见”，不是“什么已经被证明”。
```

---

### 3.6 Self-evolution / Doctor 环

```text
GP uses doctor sandbox
-> sandbox diff changes
-> snapshot / outcome_detected
-> test-diff / scope gate / review / apply
-> restart / canary / rollback
-> new runtime behavior
-> next GP observes changed system
```

主要表面：

- `doctor.sh diff-status`
- `outcome_detected`
- `test-diff`
- `apply_history`
- `cooldown`
- `rollback tag`
- `smoke test`
- `scope review`

已降低的风险：

- 无测试覆盖不再直接等同测试通过。
- test collection failure 可区分。
- 沙箱 probe 测试不应污染生产 test-diff。
- 多路径 `--only` 语义已修。
- `git apply --check` 和 rollback tag 降低 PromotionGate 风险。

仍存在的系统风险：

```text
Yogg 仍可能同时是提议者、执行者、观察者和解释者。
```

根耦合：

```text
补丁本身会成为下一轮系统材料。
```

健康边界：

```text
自进化的安全不应来自单一 cooldown 或单一测试结果，而应来自多条独立证据线。
```

---

### 3.7 Runtime / provider / report 环

```text
provider 429 / 403 / timeout / OOM / reconnect
-> logs / auto reports
-> current error signals
-> prompt
-> changed tool use / retries / self-diagnosis
-> more load / more reports
```

主要表面：

- Discord logs。
- `runtime/auto_reports/*`。
- journalctl / systemd state。
- provider response errors。
- memory pressure watcher。

瓶颈：

```text
运行饥饿和认知质量会互相污染。
```

风险：

- Provider failure 被解释成认知失败。
- OOM / reconnect 残留被解释成任务中断原因。
- report-wide grep 把源码 sanitizer 或历史 ledger 当成 live prompt 污染。
- retry / timeout 增加上下文噪声。

健康边界：

```text
Runtime artifact 可以触发诊断，但不应直接升级为知识结论。
```

---

## 4. 表面分类

| 表面 | 例子 | 应当代表 | 不应冒充 |
|---|---|---|---|
| Runtime artifact | 429、OOM、reconnect | 运行条件 | 认知结论 |
| Retrieval artifact | search miss、VOID | 检索失败或覆盖不足 | 真实知识空洞 |
| Rolling proxy | last_knowledge_state | 临时工作记忆 | 已验证事实 |
| Knowledge node | LESSON、CONTEXT | 可复用观察或概念 | runtime log 原文 |
| Evidence line | reasoning_lines、test output | 支撑关系 | 分数排名 |
| Control directive | round_focus、planner next | 行动约束 | 事实观察 |
| Report metric | node count、dry streak | 外部观测指标 | 质量本身 |
| Patch artifact | diff、sanitizer、ledger entry | 修改痕迹 | 系统真理 |

当前瓶颈集中在：

```text
表面之间可以互相流动，但缺少足够硬的语义降级和 provenance 标记。
```

---

## 5. 根耦合矩阵

| 根耦合 | 症状 | 影响 | 修复风险 |
|---|---|---|---|
| Observation 和 directive 混用 | signal wording 改变行为 | 小改动变策略变更 | 高 |
| Retrieval miss 和 real gap 混用 | false VOID 增多 | 错误牵引探索 | 高 |
| Rolling state 缺 epoch | 旧语义复活 | prompt 污染回灌 | 中高 |
| Runtime artifact 进入知识面 | provider/OOM 变认知材料 | 误判质量下降 | 中 |
| Report-wide scan 不分 provenance | sanitizer 源码触发坏词 | 误报 after 质量 | 中 |
| SelfEvolution 证据不独立 | 自己写自己验自己解释 | 修复变自证 | 高 |
| Node write 强于 consumption | 产出量上升但使用率低 | 知识堆积 | 中高 |
| RELATED_TO / hub 引力 | 搜索图方向弱 | 旧 hub 吸走注意力 | 中高 |

---

## 6. 瓶颈症状清单

如果出现以下现象，优先按瓶颈处理，不要立即打补丁：

- **修复漂移**：修一个 wording 后，另一个 state/report surface 重新出现同类污染。
- **false VOID 上升**：VOID 与 loose search hit 能对上，说明是检索/可见性问题，不是真空洞。
- **dry loop**：连续多轮 `outcome_detected=False`，但 response 很长、工具调用很多。
- **节点量增长但边质量不变**：nodes/hour 上升，edges/node、reasoning_lines/node 不跟随。
- **报告误报**：bad-term scan 命中源码、ledger、历史 prompt，而不是 live prompt field。
- **运行失败混入认知**：429 / OOM / reconnect 后，Yogg 开始围绕运行失败做大量知识生产。
- **补丁后新增观测面**：新字段、新 disclaimer、新 report phrase 被下一轮消费。
- **自修改自证**：SelfEvolution 只靠 cooldown / test-diff / smoke 单线通过就晋升。

---

## 7. Stop-fixing zones

这些区域不是不能改，而是默认冻结；没有 before/after 指标和闭环图，不应继续补丁。

| 区域 | 文件/模块 | 原因 | 允许条件 |
|---|---|---|---|
| Black | live DB schema、生产 DB 数据迁移 | 一旦错会污染所有闭环 | 明确 migration、备份、回滚、只读审计先行 |
| Red | `auto_mode.py` run loop / signals / planner | 直接塑造每轮行为 | 有字段级 before/after、live observation window |
| Red | `prompt_factory.py` prompt render | 影响所有请求上下文 | 有 prompt fixture 和污染字段扫描 |
| Red | `manager.py` NodeVault 写路径 | 影响知识生态 | 有 DB diff、节点/边/内容一致性检查 |
| Red | `knowledge_query.py` / search tools | 影响 retrieval、VOID、surface | 有 query corpus 和 false VOID 检验 |
| Red | `doctor.sh` / SelfEvolution apply | 影响自修改安全 | 有 sandbox test、rollback、scope gate 验证 |
| Yellow | tests、audit scripts、reports | 可能影响观察口径 | 字段级 provenance 明确 |
| Green | docs、只读 dashboard、手工分析 | 不进入运行闭环 | 可直接做，但避免被 prompt 自动消费 |

---

## 8. Safe observation work

当前最适合继续做的是只读治理，而不是继续修核心环。

### 8.1 字段级质量仪表盘

每日或每 session 固定采集：

```text
prompt_bad_hits_by_field
knowledge_state_bad_hits_by_field
response_bad_hits_by_field
tool_result_bad_hits_by_field
report_artifact_bad_hits_by_field
nodes_per_hour
LESSON_CONTEXT_EPISODE_ratio
edges_per_node
reasoning_lines_per_node
voids_per_node
false_void_loose_hit_rate
completed_timeout_error_ratio
consecutive_dry_avg_max
outcome_detected_ratio
provider_429_403_count
OOM_restart_count
```

关键规则：

```text
不要 report-wide grep。
必须按 provenance 字段扫描。
```

---

### 8.2 VOID 审计

对每个新 VOID 标记：

```text
void_source: retrieval_miss | exact_id_miss | phrase_miss | visibility_filtered | unknown
semantic_gap: unknown | likely | confirmed_by_human
loose_hit_count: n
resolved_by_node_id: optional
```

原则：

```text
VOID 默认是检索事件，不是知识事实。
```

---

### 8.3 Rolling state 审计

对 `.auto_session_memory.json` 和 `last_knowledge_state` 只读检查：

```text
schema keys
legacy labels
source/provenance phrase
age / session id
whether injected into prompt
```

目标不是继续替换词，而是判断：

```text
哪些 state 应该进入 prompt？
哪些只应进入 report？
哪些应该过期？
```

---

### 8.4 Self-evolution 晋升观察

只观察，不改逻辑：

```text
changed files
scope gate result
test-diff classification
apply attempted/succeeded
review/smoke/canary status
restart marker cleared or not
next 3 rounds error count
```

核心指标：

```text
apply 后是否真的降低问题，而不是产生新 surface。
```

---

## 9. Patch admission rule

后续任何补丁进入 Red / Black 区前，应满足：

```text
1. 明确要降低哪个耦合，而不是只消除哪个症状。
2. 明确 before 指标。
3. 明确 after 指标。
4. 明确这个补丁会进入哪些 surface。
5. 明确如果补丁文字被 Yogg 看到，会不会被误当作知识。
6. 有回滚路径。
7. 有 live observation window。
```

如果不能回答第 1 条，默认不修。

如果只能回答“这个词看起来不对”，默认不修。

如果只能靠 report-wide grep 证明修好了，默认不修。

---

## 10. Non-invasive operating mode

建议下一阶段采用 `Observation Freeze`：

```text
持续运行 Yogg，但冻结核心环补丁。
只做字段级观测、闭环图更新、VOID 审计、质量仪表盘。
```

### 10.1 周期

```text
每 12h：采集质量仪表盘
每 24h：审计新增 VOID / report artifact
每 3 天：判断是否真的需要进入 Red-zone patch
```

### 10.2 判断标准

可以考虑补丁的情况：

- 同一个 root coupling 连续多天稳定复现。
- false VOID 或 prompt pollution 能定位到单一字段。
- 修复能减少 surface 流动，而不是新增 surface。
- 有局部 fixture 或只读 replay 可复现。

继续观察、不补丁的情况：

- 只是产出风格变差。
- 只是某一轮 provider / OOM 造成异常。
- 只是 report-wide bad hit。
- 只是指标短期波动。
- 需要同时改 auto_mode、manager、prompt_factory 才能解释的问题。

---

## 11. 当前阶段命名

Genesis / Yogg 已经从：

```text
功能生长期
```

进入：

```text
生态治理期
```

功能生长期关注：

- 加工具。
- 加记忆。
- 加自进化。
- 加 prompt 能力。
- 加 PLS surface。

生态治理期关注：

- 分层。
- 降级。
- provenance。
- 冻结。
- 审计。
- 限流。
- 回滚。
- 独立证据线。

如果继续用功能生长期的方法处理生态治理期的问题，就会越修越乱。

---

## 12. 最短行动清单

下一步建议只做三件事：

1. **建立字段级 dashboard**
   - 不再使用 report-wide grep 作为主要质量判断。
   - 所有坏词、VOID、dry loop、provider error 都按字段和 provenance 归因。

2. **执行 Observation Freeze**
   - 冻结 Red / Black 区补丁。
   - 允许 docs、只读审计、dashboard、手工分析。

3. **记录 patch admission log**
   - 每个想改的点先写：降低哪个耦合？如何证明？会进入哪些 surface？

---

## 13. 结论

Genesis 当前不是缺补丁，而是缺边界。

```text
凡是不能降低耦合的修复，默认不做。
凡是只改变 wording 但不改变 provenance 的修复，默认不做。
凡是没有 before/after 字段级指标的修复，默认不做。
凡是会进入 prompt/state/DB/report 的修复，先画闭环。
```

Yogg 的下一阶段目标不是“更多产出”，而是：

```text
让每一种产出知道自己是什么表面、来自哪里、能否进入下一轮 prompt、以及不能冒充什么。
```
