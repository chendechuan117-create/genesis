# Yogg 自诊断问题行动纲领

> 日期: 2026-05-21  
> 输入依据: `docs/yogg_self_diagnosis_verified.md`、`docs/yogg_optimization_coupling_review.md`、`docs/pls_self_evolution_loop.md`、`docs/GENESIS_V6_ROADMAP.md`  
> 范围: 行动纲领与实施顺序。本文不代表已修改运行时代码。

---

## 0. 总判断

Yogg 的自诊断不是零散 bug 报告，而是暴露出一个更大的结构问题:

```text
Yogg 已经有较强的自我观测能力，
但缺少把观测转化为稳定行动闭环的分层执行体系。
```

三轮验证后的关键事实:

- **问题规模**: 50 项诊断，34 项确认，12 项部分确认。
- **主要病灶**: 死路径、时序真空、确认偏误、知识拓扑债、工具经济学真空、治理边界不清。
- **主要风险**: 如果直接“修所有点”，会把本来已经复杂的 `auto_mode -> PLS -> NodeVault -> C-Phase -> trace` 耦合进一步打成一团。
- **正确策略**: 不重建大脑，不先上 V6 硬门控，不先清库；先建立观测闭环、当前状态锚、干跑维护面，再逐步收敛数据债和认知债。

一句话纲领:

```text
先让 Yogg 看见真实运行状态，
再让它知道自己处在哪一章，
再让知识库可维护，
最后才让自进化和 V6 接管更高阶判断。
```

---

## 1. 总体原则

### 1.1 保留的有意耦合

这些耦合是设计资产，不应被粗暴拆掉:

| 耦合 | 保留理由 | 边界 |
|------|----------|------|
| `yogg_auto.py -> auto_mode.run_auto()` | 负责生命周期、崩溃保护、日志与 systemd 行为 | runner 不理解语义，不决定认知 |
| `auto_mode -> PLS terrain/signals` | PLS 给注意力候选 | PLS 只能给 affordance，不能变成指令 |
| `NodeVault.create_node() -> evidence gate` | 信任策略必须集中在写入口 | 强化证据质量，不另造写入门 |
| `C-Phase -> 知识沉淀` | LESSON 应由反思侧生产 | C-Phase 需要更多外部证据，避免只复述 GP |
| `TopicTracker/fallback/dry warning -> prompt` | 防止重复验证和模式坍缩 | 只能当 guardrail，不能成为主导航 |
| `V6 shadow -> V4Loop` | 校准新模型，不干扰生产 | 只记录，不路由、不过滤、不注入 |
| `ChapterState -> prompt packet` | 帮助当前状态锚定 | 只渲染，不调度、不写库、不替代 PLS |

### 1.2 必须拆开的事故耦合

这些耦合会放大误判，应优先隔离:

| 事故耦合 | 现象 | 处理方式 |
|----------|------|----------|
| 死代码看起来像能力 | `Evidence Assessor`、社区检测、`network_health.py` 有实现但不进入主路径 | 先标记/干跑/接入观测，不直接承诺能力 |
| 运行遥测变成语义地形 | 行数、计数、缺失字段被 GP 当成任务事实 | 渲染时降权，只作为 diagnostics，不作为行动命令 |
| stale action 劫持当前任务 | 旧 round 的方向被继续执行 | ChapterState 明确 `stale_actions` / `deprecated_directions` |
| PLS 候选变成强制任务 | terrain/scout/proposal 被提示词放大 | 文案上固定为“可能/候选/待验证” |
| 直接 SQL 绕过 NodeVault | 拓扑写入绕过 hidden/virtual/evidence guard | 做 bypass 审计，统一写入口 |
| 自进化自审自批 | Yogg 提 patch、测 patch、应用 patch | 引入 review/canary，不允许冷却即晋升 |

### 1.3 禁止动作

在完成前置阶段前，不做以下事:

- **不直接清理 live NodeVault 拓扑债**: 先 dry-run 报告，再分批迁移。
- **不把 V6 作为硬过滤器接入 Surface**: 先 shadow/calibration，再 soft prior。
- **不扩大 GP 知识写权限**: `record_lesson_node` 继续留给 C-Phase。
- **不删除 TopicTracker/fallback/dry guard**: 除非有等价替代。
- **不把 ChapterState 做成 scheduler**: 它只渲染当前状态。
- **不把 PLS terrain 写成任务指令**: 只能是注意力候选。
- **不把 network health 直接注入 GP 语义上下文**: 网络健康是运维信号，不是问题本体。
- **不使用 nohup 启动生产服务**: 服务生命周期必须走 systemd。

---

## 2. 耦合依赖总图

```text
                ┌────────────────────────┐
                │ systemd / yogg_auto.py │
                └───────────┬────────────┘
                            │ lifecycle only
                            ▼
┌──────────────────────────────────────────────────────┐
│ auto_mode.py                                          │
│ - round loop                                          │
│ - progress classifier                                │
│ - self-evolution                                     │
│ - signal assembly                                    │
└───────┬──────────────┬───────────────┬────────────────┘
        │              │               │
        ▼              ▼               ▼
┌────────────┐  ┌──────────────┐  ┌──────────────────┐
│ PLS terrain│  │ ChapterState │  │ diagnostics       │
│ weak hints │  │ prompt packet│  │ runtime truth     │
└─────┬──────┘  └──────┬───────┘  └────────┬─────────┘
      │                │                   │
      ▼                ▼                   ▼
┌──────────────────────────────────────────────────────┐
│ V4Loop / prompt / tool dispatch                       │
└───────┬───────────────────────────────┬──────────────┘
        │                               │
        ▼                               ▼
┌──────────────┐                 ┌───────────────┐
│ C-Phase      │                 │ trace pipeline │
│ reflection   │                 │ entities/edges │
└──────┬───────┘                 └───────┬───────┘
       │                                 │
       ▼                                 ▼
┌──────────────────────────────────────────────────────┐
│ NodeVault                                             │
│ - create_node evidence gate                           │
│ - reasoning_lines / node_edges                        │
│ - VOID / ablation / heartbeat                         │
└──────────────────────────────────────────────────────┘

V6 shadow 只能旁路观察 auto_mode/V4Loop/trace 的输入输出，
在校准完成前不能参与 hard gating。
```

### 2.1 关键依赖顺序

```text
诊断信号可见
  -> daemon/trace 死路径可验证
  -> Evidence Assessor 才有真实输入
  -> 证据质量规则才有落点
  -> NodeVault 维护/拓扑清理才安全

ChapterState 当前状态锚定
  -> stale action 不再劫持
  -> PLS 候选不会被误读成命令
  -> auto_mode progress classifier 的输出更可解释
  -> V6 shadow 才有干净训练标签

self-evolution 安全门
  -> 变更可以通过沙箱/审查/金丝雀晋升
  -> 才允许 Yogg 自己修更高风险的控制回路
```

---

## 3. 阶段 0: 冻结边界与建立基线

### 目标

在任何生产修复前，先确定“当前系统到底如何运行”。

### 必做事项

- **进程边界盘点**: 列出 `discord_bot.py`、`yogg_auto.py`、`background_daemon.py`、`start.sh`、`start_api.sh` 的实际 systemd 管理关系。
- **数据库快照**: 对 NodeVault、trace DB、trace entity DB 做只读结构盘点和备份策略说明。
- **现有诊断指标基线**: 记录最近 24h 的 auto reports、progress class、tool success、provider failure、KB delta、trace pending 数。
- **文档边界冻结**: 将“哪些是能力、哪些是死路径、哪些是设计草案”写入当前行动记录。

### 验收标准

- **能回答**: 当前哪个服务在跑、由谁重启、哪个 DB 是权威源。
- **能回滚**: 任何后续维护都有备份/干跑输出。
- **能区分**: runtime 能力、实验能力、文档构想、死代码不再混淆。

### 不做事项

- 不改 live DB。
- 不接入新控制器。
- 不删除死代码。

---

## 4. 阶段 1: P0 死路径与观测闭环修复

这是第一批应该动的生产代码，因为它们不改变认知策略，只让系统诚实地暴露状态。

### 4.1 PipelineDiagnostics 补齐 record 调用

#### 问题

`c_phase_zero_output` 和 `search_zero_hit` 已定义但没有记录点，导致诊断信号永远为 0。

#### 行动

- 在 C-Phase 完成处记录“本轮是否创建知识节点”。
- 在搜索工具返回处记录“本轮是否 0 hit”。
- 为两个信号加最小单元测试或合成触发测试。

#### 耦合注意

- `search_zero_hit` 不能只统计 LIKE，应覆盖最终用户可见结果。
- `c_phase_zero_output` 要区分 C-Phase 被跳过、失败、正常完成但零产出。
- 记录诊断不能反过来污染 GP prompt，除非经过明确摘要层。

#### 验收

- 合成 5 次 0 hit 能触发 breaker 或至少产生非零 rate。
- C-Phase 零产出在 auto report 或 diagnostics 中可追踪。

### 4.2 daemon 与 trace pipeline 死路径拆分

#### 问题

`background_daemon` 调 `process_pending_traces(rebuild_relationships=False)`，而 Evidence Assessor 和社区检测依赖关系重建，导致功能性休眠。

#### 行动

- 将 trace pipeline 拆成三个显式阶段:
  - `extract_entities`
  - `rebuild_relationships_and_communities`
  - `assess_evidence`
- daemon 中不要用一个布尔值隐式控制全部后续能力。
- 先增加 dry-run/summary 模式，输出 pending、processed、relationships、communities、assessed。

#### 耦合注意

- Evidence Assessor 不应在没有关系图更新时假装评估。
- 社区检测可能较重，应有频率/limit/cooldown。
- 输出先进入 daemon 日志和 diagnostics，不直接进 GP 语义上下文。

#### 验收

- daemon 周期日志能明确显示三阶段各自运行/跳过原因。
- 有新 trace 时，relationship/community/evidence 至少在 dry-run 报告中可见。

### 4.3 heartbeat 活墓园降级

#### 问题

`process_heartbeat` 是单行快照，旧 PID 可能被误判为存活，且无清理。

#### 行动

- 给 heartbeat 增加或渲染进程身份维度: `pid`、启动时间、host、service name、last_heartbeat age。
- `knowledge_query` 展示时优先显示 `fresh/running`、`stale_snapshot`、`dead_or_unknown`，不要把 `os.kill(pid, 0)` 当唯一依据。
- daemon 增加 heartbeat TTL 清理或 stale 标记报告。

#### 耦合注意

- 不要把 heartbeat 清理和知识 GC 混在一个不可分事务里。
- systemd 是生命周期权威，heartbeat 是系统自述，不是 supervisor。
- PID 检测只能作为弱证据。

#### 验收

- 过期 heartbeat 不再显示成健康运行。
- stale 条目可统计、可清理、可解释。

### 4.4 死代码隔离标签

#### 问题

`network_health.py`、Challenger 残留、社区检测等容易被误读成已接入能力。

#### 行动

- 生成“能力接入矩阵”: 文件、是否导入、是否入口、是否被 systemd 调用、是否进入 prompt、是否写库。
- 对零导入模块先标记为 `quarantined_design` 或 `unwired_module`。
- 后续再决定删除、接入或保留为实验。

#### 耦合注意

- 不要因为代码存在就纳入 GP 自我认知。
- 不要为了“减少死代码”把运维监控硬塞进认知路径。

#### 验收

- 每个孤岛模块都有状态: production / experiment / dead / deprecated。

---

## 5. 阶段 2: 当前状态锚定层 ChapterState

这是最重要的认知层修复。它解决的不是“Yogg 不够聪明”，而是“Yogg 不知道自己现在在哪一章”。

### 5.1 目标边界

ChapterState 的唯一职责:

```text
把多个只读来源整理成一个小而清晰的 prompt packet。
```

它不做:

- 不查 NodeVault。
- 不写 NodeVault。
- 不决定 tool calls。
- 不替代 PLS。
- 不替代 TopicTracker。
- 不做 scheduler。
- 不直接判断任务完成。

### 5.2 推荐数据流

```text
source collectors
  -> SourceLane[]
  -> ChapterStateBuilder
  -> ChapterState
  -> bounded renderer
  -> auto_mode signal/prompt packet
```

### 5.3 SourceLane 类型

| lane | 内容 | 风险 |
|------|------|------|
| `user_request_lane` | 当前用户目标 | 必须最高优先级 |
| `recent_round_lane` | 最近 round 的真实行为 | 防止历史劫持 |
| `stale_action_lane` | 过期计划/未完成旧方向 | 必须显式标 stale |
| `deprecated_direction_lane` | 已验证不成立/已修复方向 | 防止重复挖坑 |
| `evidence_boundary_lane` | 当前证据来自代码、DB、报告还是推断 | 防止把推断当事实 |
| `open_uncertainty_lane` | 尚未验证的问题 | 防止过度自信 |
| `next_decision_lane` | 下一步只应解决的决策边界 | 限制发散 |

### 5.4 渲染字段

```text
active_question
current_chapter
known_facts
stale_actions
deprecated_directions
evidence_boundaries
open_uncertainties
next_decision_boundary
```

### 5.5 耦合注意

- ChapterState 应接在 `auto_mode` 组装 signals 之前或同层，不进入 NodeVault 写路径。
- 它应降低 PLS terrain 的命令性，而不是替代 PLS。
- 它应让 `raw_state.issue` 退位，避免旧状态自引用冻结。
- 它应给 V6 shadow 提供更干净的 state label。

### 5.6 验收

- 同一旧 action 连续出现时，会被归类到 `stale_actions` 而不是 `active_question`。
- 已验证不成立的问题不会继续作为当前任务。
- prompt packet 有长度上限。
- 关闭 ChapterState 后，系统退回原行为。

---

## 6. 阶段 3: 知识拓扑与 VOID 生命周期维护

等观测和当前状态锚定稳定后，再处理知识库维护。否则容易清掉“看似孤儿但仍有认知价值”的节点。

### 6.1 拓扑干跑审计

#### 行动

生成只读报告:

- orphan `reasoning_lines`
- orphan `node_edges`
- hidden/virtual endpoint debt
- self-loop edges
- noncanonical relation values
- null/invalid line ids
- physical skill 文件 vs TOOL 节点覆盖率
- VIRT 节点数量、来源、被引用情况

#### 耦合注意

- `reasoning_lines` 已经是持久化表，不应再按“会话快照丢失”处理。
- 拓扑债很多属于历史数据债，不等同于当前写入逻辑错误。
- 所有清理都应先 dry-run，再小批量、可回滚。

#### 验收

- 每类债务都有 count、样例、建议动作、风险等级。
- 报告不修改 live DB。

### 6.2 VOID 生命周期补全

#### 问题

VOID 已有 `open/resolved/stale` 基础，但缺少 dedupe key、occurrence count、last_seen、observed/ignored 等维护维度。

#### 行动

- 先做 VOID dry-run maintenance report:
  - duplicate open VOID groups
  - repeated occurrence candidates
  - likely resolved by existing nodes
  - stale VOID candidates
  - empty/meaningless query text
- 再设计轻量字段或 metadata 扩展:
  - `dedupe_key`
  - `occurrence_count`
  - `first_seen`
  - `last_seen`
  - `status_reason`

#### 耦合注意

- VOID 是知识空洞，不是任务命令。
- fallback focus 可以引用 VOID，但不能被单个 VOID 长期劫持。
- VOID resolve 不应靠弱 substring 自动过度关闭。

#### 验收

- 重复 VOID 不再制造重复任务压力。
- stale VOID 能被降权。
- 被现有知识覆盖的 VOID 能进入候选 resolved。

### 6.3 CONTRADICTS 消费升级

#### 问题

CONTRADICTS 现在主要是拓扑标记，没有运行时回调。

#### 行动

- 不做强回调。
- 在知识渲染中显示更明确的 contradiction cue。
- 在 C-Phase 审查与 self-evolution review 中把 CONTRADICTS 作为审查信号。

#### 耦合注意

- CONTRADICTS 不应自动否定节点，只应要求复核。
- 过强的 contradiction callback 会制造新控制器。

#### 验收

- GP/C-Phase 能看见关键矛盾边。
- 矛盾边触发“复核/降权”，不触发自动删除。

---

## 7. 阶段 4: 证据质量与工具经济学

### 7.1 证据质量升级

#### 当前判断

基础 evidence gate 已存在，不应重复发明。下一步是防止“空证据/弱证据”保住 `validated`。

#### 行动

- 规范 `evidence_refs` 的最小质量:
  - file evidence: path + relevant excerpt
  - command evidence: command + output excerpt
  - trace evidence: trace id + span/result excerpt
  - report evidence: report path/id + quote
- 对只有类型、没有内容的 evidence 降级为 partial。
- C-Phase 写 LESSON 时要求 evidence boundary。

#### 耦合注意

- 证据规则必须继续集中在 `NodeVault.create_node()`。
- 不要在 tool 层各自实现一套互相矛盾的 trust policy。

#### 验收

- `validated` 节点都有可读证据摘录。
- 空 evidence 无法维持 validated。

### 7.2 工具经济学模型

#### 问题

GP 对 WebSearch、read_file、grep、DB 查询等工具缺少成本差异感。

#### 行动

- 给工具注册增加只读元数据:
  - `cost_class`: free/cheap/medium/expensive
  - `side_effect`: none/read/write/network
  - `latency`: low/medium/high
  - `preferred_before`: 可选低成本替代
- prompt 中以建议形式呈现，不做硬阻断。
- 对高成本工具调用产生 diagnostics 计数。

#### 耦合注意

- 成本模型不能覆盖用户明确要求。
- 不能把 cost 当作真理，只能作为操作策略。
- 写工具仍由权限系统控制，不由 cost 控制。

#### 验收

- 常见本地信息任务优先使用 read/grep/DB，而不是 WebSearch。
- auto report 中可解释工具选择成本。

### 7.3 搜索管道改进

#### 行动

- 为中文查询增加同义词/别名扩展，不只依赖空格拆词。
- `search_zero_hit` 与 vector threshold 绑定诊断。
- 对低置信但可能重要的结果保留“弱候选”区域。

#### 耦合注意

- 搜索结果不是事实，只是候选。
- 弱候选必须在渲染上与已验证知识分开。

#### 验收

- 中文同义表达不会轻易 0 hit。
- 0 hit 有诊断而不是静默失败。

### 7.4 显式完成握手

#### 问题

任务完成靠 GP 最后一条自然语言，没有结构化完成信号。

#### 行动

- 先在 auto report/progress classifier 中增加完成候选结构:
  - `completion_claimed`
  - `evidence_of_completion`
  - `remaining_uncertainty`
- 暂不急着增加新工具。

#### 耦合注意

- 完成信号不能让 GP 提前逃跑。
- 对代码任务，completion 必须绑定 tests/diff/evidence。

#### 验收

- soft completion 和 evidence-backed completion 可区分。

---

## 8. 阶段 5: 自进化安全晋升线

自进化不能在观测闭环和证据质量之前全面放权。

### 8.1 当前模型

```text
sandbox diff
  -> test-diff
  -> review
  -> canary
  -> production
```

### 8.2 行动顺序

1. **修正/验证 scope gate**: 确保 `doctor.sh --only` 对多文件路径语义正确。
2. **保留 test-diff 证据分类**: `NO_TESTS_FOUND` 只能是 unverified，不是 pass。
3. **Twin-Review 非阻塞**: C-Phase 审查 diff，但先只记录意见。
4. **Twin-Review 阻塞**: 只有 `APPROVE` 才允许晋升。
5. **Canary rounds**: 应用后观察 N 轮，无崩溃、无异常诊断再标记成功。
6. **关键文件红线**: `auto_mode.py`、`loop.py`、`manager.py`、`provider`、systemd 脚本等只能人工确认。

### 8.3 耦合注意

- SelfEvolution 属于执行治理，不属于认知生产。
- C-Phase review 是审查者，不是 patch 作者。
- Canary 依赖 heartbeat/diagnostics 已可信。
- 不允许“冷却完成 = 自动生产”。

### 8.4 验收

- 无测试覆盖不会被报告为 pass。
- critical 文件不会自动晋升。
- review 记录可追溯。
- canary 失败可回滚。

---

## 9. 阶段 6: V6 只读校准与软先验

V6 是长期方向，不是当前 P0 修复。

### 9.1 当前姿态

```text
shadow_only
no routing
no filtering
no prompt injection
```

### 9.2 行动

- 编译训练/评估数据集:
  - task embedding
  - ChapterState fields
  - PLS activation
  - tool/action sequence
  - outcome class
- 建立 baseline:
  - frequency baseline
  - recent-success baseline
  - PLS-only baseline
- 评估 V6 是否能预测:
  - 成功工具路径
  - 自指隧道风险
  - stale action 风险
  - 需要搜索/需要代码/需要 DB 的任务类型

### 9.3 接入门槛

只有满足以下条件，才能从 shadow 进入 soft prior:

- 离线评估显著优于 baseline。
- 不降低任务多样性。
- 不增加自指重复率。
- 可以解释其建议来源。
- 有 kill switch。

### 9.4 禁止

- 不把 V6 logits 直接硬过滤 Surface。
- 不用未校准模型替代 PLS。
- 不把小模型误当“真理压缩器”。

---

## 10. 阶段 7: 收敛与删除债务

最后才做删除和迁移。

### 行动

- **Schema 退役计划**: 给 `epistemic_status` 等幽灵字段明确 deprecated status、迁移策略、渲染策略。
- **NetworkHealthMonitor 决策**: 三选一: 接入运维 diagnostics、移到 experiments、删除。
- **Challenger 残留清理**: 删除或更新文档/pyc 残留引用。
- **工具契约审计**: JSON schema 参数与 `execute()` 签名一致性。
- **物理技能可见性**: 决定是否生成 TOOL 索引节点或只保留 runtime registry。

### 耦合注意

- 删除必须发生在确认没有 runtime/import/doc 依赖后。
- Schema 迁移必须兼容旧 DB。
- TOOL 节点索引不要伪装成技能已验证。

### 验收

- 代码存在性、运行时接入性、知识图谱可见性三者不再混淆。
- 文档不再宣称未接入能力。

---

## 11. 优先级总表

| 优先级 | 工作项 | 类型 | 依赖 | 风险 | 第一验收 |
|--------|--------|------|------|------|----------|
| P0 | diagnostics record 补齐 | 观测 | 无 | 低 | 合成触发可见 |
| P0 | daemon trace 三阶段显式化 | 观测/维护 | diagnostics | 中 | 日志显示跳过/运行原因 |
| P0 | heartbeat stale 语义 | 运维 | systemd 边界 | 中 | stale 不显示为 live |
| P0 | 能力接入矩阵 | 文档/审计 | 无 | 低 | dead/experiment/prod 可区分 |
| P1 | ChapterState prompt packet | 认知锚 | SourceLane contract | 中 | stale action 不劫持 |
| P1 | evidence quality gate | 信任 | NodeVault gate | 中 | 空证据降级 |
| P1 | VOID dry-run maintenance | 知识维护 | ChapterState | 中 | 重复/stale VOID 可见 |
| P1 | topology dry-run audit | 数据维护 | diagnostics | 中 | 债务报告可回滚 |
| P2 | tool cost metadata | 执行经济 | tool registry | 中 | 成本可解释 |
| P2 | search 中文/zero-hit 改进 | 召回 | diagnostics | 中 | 中文 0 hit 降低 |
| P2 | self-evolution review/canary | 治理 | diagnostics + evidence | 高 | 冷却不等于晋升 |
| P3 | V6 shadow calibration | 长期学习 | ChapterState + traces | 高 | 优于 baseline 后才 soft prior |
| P3 | schema/dead code 收敛 | 债务删除 | dry-run reports | 中 | 无误删/无旧库破坏 |

---

## 12. 推荐执行节奏

### 第 1 批: 1-3 天

目标: 让系统不再假装“看得见”。

- 补 `c_phase_zero_output` / `search_zero_hit` record。
- 拆 daemon trace pipeline 的阶段状态。
- heartbeat stale 语义降级。
- 产出能力接入矩阵。

成功标志:

```text
Yogg/daemon 报告中的“沉默能力”变成显式 running/skipped/dead/dry-run。
```

### 第 2 批: 3-7 天

目标: 让 Yogg 不再被旧章节劫持。

- ChapterState isolated experiment 对齐现有 contract。
- 接入只读 prompt packet，带 kill switch。
- auto_mode knowledge_state 避免 raw_state 自引用冻结。
- 时间/新鲜度以 freshness class 进入渲染。

成功标志:

```text
Yogg 能明确区分 current task、stale action、deprecated direction、open uncertainty。
```

### 第 3 批: 1-2 周

目标: 让知识库从“可增长”变成“可维护”。

- VOID dry-run maintenance。
- topology dry-run audit。
- evidence quality 升级。
- CONTRADICTS 进入审查和渲染提示。

成功标志:

```text
清理建议都有证据、样例、风险等级和回滚路径，而不是直接清库。
```

### 第 4 批: 2-4 周

目标: 让执行和自进化安全。

- 工具成本元数据。
- search zero-hit 与中文召回改进。
- Twin-Review 非阻塞 -> 阻塞。
- Canary 晋升。

成功标志:

```text
Yogg 可以安全提出和验证小补丁，但不能无审查修改核心控制回路。
```

### 第 5 批: 4 周后

目标: 让 V6 从构想进入可评估阴影系统。

- 编译 shadow dataset。
- 做 baseline 对照。
- 只在指标稳定后提供 soft prior。

成功标志:

```text
V6 的建议能被离线数据证明有用，而不是凭概念美感接管 V4。
```

---

## 13. 每次实施前的检查清单

### 13.1 改生产代码前

- **是否有 GitNexus impact**: 修改函数/类/方法前必须做 upstream impact。
- **是否读过 NodeVault observation**: 修改目标文件前读取对应 file observations。
- **是否有 kill switch**: 新行为是否可关闭。
- **是否有 dry-run**: 数据维护类变更是否先只读。
- **是否会扩大 GP 权限**: 如果会，默认拒绝。
- **是否会把候选当事实**: 如果会，改渲染措辞。

### 13.2 改提示词/渲染前

- **是否区分事实、候选、推断、过期**。
- **是否有长度上限**。
- **是否会重复强调同一旧方向**。
- **是否会把 operational count 变成 semantic mandate**。

### 13.3 改 DB/迁移前

- **是否有备份**。
- **是否兼容旧 schema**。
- **是否有 dry-run 样例**。
- **是否能回滚**。
- **是否绕过 NodeVault 写入口**。

### 13.4 改 self-evolution 前

- **是否涉及 critical 文件**。
- **是否有测试证据分类**。
- **是否需要人工 approve**。
- **是否有 canary 观察窗口**。
- **是否会让 Yogg 自己批准自己**。

---

## 14. 最终目标状态

完成上述阶段后，Yogg 应达到以下状态:

```text
1. 运行状态诚实
   死路径、跳过、失败、0 hit、零沉淀都可见。

2. 当前章节清晰
   它知道当前问题、旧行动、废弃方向和证据边界。

3. 知识库可维护
   VOID、拓扑债、虚拟节点、矛盾边都有 dry-run 报告和生命周期。

4. 证据质量可审计
   validated 不再靠空 evidence 存活。

5. 工具选择有经济感
   便宜、本地、只读优先；昂贵工具有理由。

6. 自进化有治理
   沙箱、证据、审查、金丝雀、回滚构成晋升链。

7. V6 有数据资格
   先 shadow 证明有效，再进入 soft prior，最后才考虑 gating。
```

---

## 15. 最短可执行路线

如果只允许做最小闭环，推荐顺序是:

```text
A. diagnostics record 补齐
B. daemon trace 三阶段状态显式化
C. ChapterState 只读 prompt packet
D. VOID/topology dry-run reports
E. evidence quality 升级
F. self-evolution review/canary
G. V6 shadow calibration
```

这个顺序的核心理由:

```text
先修“看见真实状态”，
再修“理解当前章节”，
再修“维护知识债”，
再修“安全自修改”，
最后才让新模型影响行为。
```
