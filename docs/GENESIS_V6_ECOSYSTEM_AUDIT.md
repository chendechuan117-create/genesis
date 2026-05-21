# Genesis V6 生态可学习性审计

> 基调：V6 不从 `brain.py` 开始。先证明 PLS 痕迹是否具备可学习性，再决定是否把它升华为参数化经验先验。
>
> 本文是 `GENESIS_V6_ROADMAP.md` 的前置门槛。未通过本审计前，不应修改 `V4Loop`、`SurfaceExpander`、`NodeVault` 或 C-Phase 运行时逻辑。

---

## 一、审计目标

V6 的核心假设是：PLS 留下的点、线、面不是终点，而是可被编译为经验先验的训练基石。

但这个假设必须先被验证：

1. **是否有信号**：NodeVault 与 `runtime/traces.db` 中是否存在稳定的 `state -> signature/tool/error/outcome` 映射。
2. **是否可泛化**：这些映射是否能在未见过的 trace/task 上预测后续需要的知识维度或工具风险。
3. **是否优于现有系统**：候选模型是否能超过当前 `SignatureEngine.infer()`、`VectorEngine.search()`、Surface BFS 的组合。
4. **是否不会误杀长尾**：任何门控不得压低 HUMAN、validated、hard evidence、低频高价值约束节点。

若以上任一项不成立，V6 小模型暂停，不进入运行时。

---

## 二、非目标

本阶段明确不做以下事情：

- **不实现小脑**：不创建 `genesis/v6/brain.py`，不训练 MLP。
- **不改主循环**：不改 `genesis/v4/loop.py`。
- **不改 Surface 行为**：不做 hard gate，不影响线上召回。
- **不改数据库 Schema**：只读审计，不新增表、不迁移、不清理节点。
- **不替代 PLS**：PLS 仍是冷存储与证据底座，V6 只评估是否能从中提炼经验先验。

---

## 三、现有生态接口对齐

### 3.1 State 输入

可用来源：

- **用户输入**：`traces.user_input`。
- **知识文本**：`knowledge_nodes.title`、`tags`、`resolves`、`metadata_signature`。
- **执行局部状态**：`spans.tool_name`、`spans.error`、`spans.tool_args_preview`、`spans.tool_result_preview`。

编码约束：

- 当前 `VectorEngine` 使用 `BAAI/bge-small-zh-v1.5`。
- 该模型物理向量维度应按 **512** 处理。
- 审计脚本必须动态检查向量长度，禁止写死后静默失败。

### 3.2 Label 输出

候选 label 分三类：

1. **Signature label**
   - 来自 `metadata_signature`。
   - 初始只使用 `signature_constants.METADATA_SIGNATURE_FIELDS` 中稳定字段。
   - 动态 value 需要从真实数据库频率统计生成词表。

2. **Tool label**
   - 来自 `spans.tool_name`。
   - 必须与 `ToolRegistry` 当前注册工具名对齐。
   - 不能用自然语言动作名代替真实工具名。

3. **Error / friction label**
   - 来自 `spans.error` 与 `tool_result_preview`。
   - 先映射到粗粒度 `error_kind`：permission、missing_dependency、timeout、network、syntax、oom、unknown。
   - 不直接把每条 error 文本当分类标签。

### 3.3 Outcome 信号

可用 outcome：

- `traces.status`。
- `spans.status`。
- `spans.error` 是否为空。
- `duration_ms` 是否异常长。
- `tool_call_count` 与 `llm_call_count` 是否显著高于同类任务。
- NodeVault 中的 `usage_success_count`、`usage_fail_count`。

约束：

- 单次工具失败不一定是坏信号，可能是合理探索。
- 成功 trace 中的中间失败不能直接作为负样本。
- 负样本必须结合最终 outcome、重试模式、是否绕路成功来判定。

---

## 四、可学习性审计问题

### 4.1 数据覆盖

需要统计：

- NodeVault 中各类型节点数量。
- 有 embedding 的节点比例。
- 有 `metadata_signature` 的节点比例。
- 有 usage 反馈的节点比例。
- `traces.db` 中 completed/error trace 数量。
- `tool_call` span 数量与工具分布。
- error span 数量与 error_kind 分布。

最低门槛：

- 至少有 100 条可用训练样本。
- 至少有 3 类以上稳定 tool 或 signature label。
- 单一 label 占比不能超过 80%，否则说明类别坍塌。

### 4.2 标签质量

需要回答：

- signature 是否真的反映任务语义，还是大量为空/泛化词。
- tool_name 是否稳定，还是大量 unknown/空值。
- error 文本是否可被稳定归类。
- usage_success/fail 是否足够稠密。

最低门槛：

- signature 可解析率 >= 60%。
- tool label 非空率 >= 70%。
- error_kind unknown 比例 <= 50%。

### 4.3 预测价值

先做 baseline，不做 MLP：

1. **规则 baseline**
   - `SignatureEngine.infer(user_input)`。

2. **向量 baseline**
   - `VectorEngine.search(user_input)` 后统计 top-k 节点 signature 命中。

3. **频率 baseline**
   - 按全局最高频 label 预测。

4. **线性 baseline**
   - NumPy 线性分类器或 centroid classifier。
   - 仅用于验证信号，不追求高性能。

最低门槛：

- 线性 baseline 必须显著超过频率 baseline。
- 线性 baseline 必须至少在一个核心任务上接近或超过规则 baseline。
- 如果线性模型无优势，MLP 不进入计划。

---

## 五、Shadow Mode 设计

若可学习性审计通过，下一步仍不接管运行时，只进入 shadow mode。

Shadow mode 只记录预测，不影响决策：

- 对每次任务预测 top-k signature/tool/error_kind。
- 任务结束后，用真实 trace 计算命中率。
- 估算如果用于 Surface rerank，会节省多少 token。
- 估算是否会压低最终实际使用或验证过的节点。

必须记录的指标：

- **top-k 命中率**：预测 label 是否出现在后续 trace 或 C-Phase 产物中。
- **token saving estimate**：模拟 rerank 后可减少的 Surface token。
- **critical miss rate**：HUMAN/validated/hard evidence 节点是否被排到过低。
- **false confidence**：模型高置信预测但实际不命中的比例。

Shadow 通过门槛：

- top-3 命中率稳定高于规则 baseline。
- token saving estimate >= 20%。
- critical miss rate = 0。
- false confidence 不高于人工设定阈值。

---

## 六、接入策略

只有 Shadow Mode 通过后，才允许进入软接入。

接入顺序：

1. **Soft Rerank**
   - 只对 Surface 候选排序加权。
   - 不删除、不屏蔽、不 hard gate。

2. **Prompt Hint**
   - 只注入一行高浓度经验先验。
   - 例如：`经验先验：当前任务更接近 runtime=python/task_kind=debug，优先检查 import 和测试反馈。`

3. **Failure-aware Rerank**
   - 仅当 trace 出现具体错误后，才对相关 error_kind 节点加权。

禁止项：

- 禁止首次接入就 hard filter。
- 禁止对 HUMAN 节点降权。
- 禁止对 validated hard evidence 节点降权。
- 禁止让模型输出直接修改 NodeVault。

---

## 七、主要风险与对应护栏

### 7.1 噪声压缩风险

如果 PLS 痕迹本身噪声很高，小模型会把噪声压缩成更难解释的黑盒。

护栏：

- 先 baseline，后 MLP。
- 保留每次预测的可解释 feature 与命中结果。
- 不通过 shadow 不接管。

### 7.2 长尾误杀风险

低频但关键的生产约束可能被模型视为低概率。

护栏：

- HUMAN、validated、hard evidence 永不 hard gate。
- 初期只 rerank，不 filter。
- critical miss rate 必须为 0。

### 7.3 生态漂移风险

工具名、signature value、trace schema 会随 Genesis 演进变化。

护栏：

- 输出词表从运行时真实数据生成。
- 每次训练前检查 ToolRegistry 与词表一致性。
- 向量维度运行时断言，不依赖文档常数。

### 7.4 伪直觉风险

当前 ReAct Round 1 已受系统提示词与 Surface 影响，不是纯净直觉。

护栏：

- 不把 Round 1 直接神化为 ground truth。
- Loss 先基于 trace outcome 与工具摩擦，而非“直觉/实证”的抽象叙事。

---

## 八、停止条件

出现以下任一结果，V6 参数化小模型暂停：

- 数据样本不足，无法构造稳定训练/验证集。
- label 坍塌，频率 baseline 已经很强。
- 线性 baseline 不超过规则 baseline。
- shadow mode 出现 critical miss。
- token saving 不明显，或节省 token 以牺牲成功率为代价。
- 模型无法给出可解释预测，只制造额外复杂度。

---

## 九、推荐最小行动

第一步只做一个只读审计脚本：

`genesis/v6/audit_pls_learnability.py`

它应该输出：

- NodeVault 数据覆盖报告。
- Trace 数据覆盖报告。
- Signature/Tool/Error label 词表。
- Baseline 可预测性报告。
- 是否允许进入 Shadow Mode 的明确结论。

该脚本必须满足：

- 只读 SQLite。
- 不创建新表。
- 不写模型权重。
- 不影响运行时。
- 可重复运行。

---

## 十、结论

V6 当前的正确问题不是“如何实现小模型”，而是：

> **PLS 痕迹是否真的包含可学习、可泛化、能降低 Context 噪声且不误杀长尾约束的经验梯度？**

只有这个问题被审计脚本客观回答为“是”，`GENESIS_V6_ROADMAP.md` 中的小模型路线才进入实现阶段。
