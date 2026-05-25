# Yogg 5/21-23 深度分析报告（附代码行标注）

## 防语义漂移协议：杠杆不是分类词

本文暴露的问题，应服务于当前主线：

> 通过 Genesis 撬动 Genesis 自己，先搭建 Genesis 对自身的概念模型；优化现有 PLS / Trace / NodeVault / Arena 的杠杆效率，为第二阶段“每用户小模型 / V6 概率路线预测”准备高质量轨迹地基。

本文不是“看到一个 bug 修一个 bug”的待办表，也不是给问题贴“观察/写入/连接/选择/清洁”标签的分类表。**杠杆是因果判据，不是命名体系。**

一个改动只有满足以下至少一条，才算提高杠杆效率：

1. **提高未来轮次的先验质量**：让下一轮 Genesis 更容易选择正确路线，而不是只让当前报告更好看。
2. **提高 state-action-outcome 轨迹可蒸馏性**：未来 V6 能从轨迹中看清当时状态、选择路线、选择依据、参与的点/线/面和结果。
3. **提高 Genesis 自我概念模型的可连接性**：新观察能接回旧点/旧线/旧面，进入概念网络，而不是孤立散文。
4. **减少未来训练标签污染**：防止假成功、假失败、假环境、假当前状态、假归因进入长期经验。
5. **减少重复探索**：让系统更容易判断“这里已探索过、这里仍是空洞、这里需要验证”，而不是下一轮重新发现同一问题。

不满足上述条件的工作，即使看起来很系统，也不算杠杆优化：

- 给所有问题贴上“观察/连接/清洁”标签，但不改变未来轮次可用信息。
- 做大型 governance 系统，但不提升轨迹可蒸馏性。
- 自动修复 ENV_FACT，却没有记录验证证据。
- 自动消解 CONTRADICTS，却没有保留冲突为何出现。
- 把 Arena 归因变复杂，但仍无法形成可训练的 state-action-outcome 标签。
- 把文档越写越宏大，但下一轮 Genesis 仍不知道如何少走弯路。
- 把多维信号压成一个总分，导致不可调试。

后续每次想修一个 Yogg 问题，必须先回答五问：

1. 这个改动会改善哪条未来路线预测？
2. 它会让哪种 state-action-outcome 样本更干净？
3. 它会让哪个点/线/面更容易复用？
4. 它会减少哪种重复探索？
5. 它会避免哪种训练标签污染？

答不上来，暂停，不做。

Genesis 自我模型不是终点，Knowledge Governance 也不是终点。它们只服务于 V6 的每用户小模型：把长期交互轨迹蒸馏成个性化概率路线 prior。不要为了治理 Genesis 而治理 Genesis，不要为了分析 Yogg 报告而继续生产 Yogg 报告。

## 时间线概览

| 时段 | 特征 | 节点数 |
|------|------|--------|
| 5/21 凌晨 | 崩溃循环 — knowledge_state 冻结导致同一 issue 跨 session 重复 | 0 实质产出 |
| 5/21 深夜 (22:00-23:50) | 模式提取爆发 — 系统性扫描代码库架构断裂 | ~50+ LESSON |
| 5/22 全天 | 深化分析 — 隐式数据总线、技能发现层、操作配方 | ~20 LESSON |
| 5/23 凌晨-上午 | 最深架构分析 — 经济成本替代、信号精度反转、桥接点坍缩 | ~25 LESSON |

## 当前杠杆保护状态（截至 5/23 19:20）

| 杠杆 | 问题 | 当前结论 |
|------|------|----------|
| 清洁杠杆 | Evidence Assessor 污染 Arena 计数 | 已改为 dry-run/passive，只报告候选，不写 `usage_success_count` / `usage_fail_count`；保护未来训练标签 |
| 观察杠杆 | ShellTool cwd 信号不透明 | 已输出 requested/resolved/executor/fallback 元数据，便于判断实际执行位置；避免假环境进入自我模型 |
| 清洁杠杆 | daemon 自动节点硬删除 | 已改为 dry-run-first，区分 `would_delete` 与 `hard_deleted`；防止破坏未被理解的概念材料 |
| 观察杠杆 | daemon Phase3 字段读取 | 已兼容 `evidence_stats` / `evidence_assessment`，避免日志误报 |
| 选择杠杆 | Arena 集体归因 | 仍是全局 env_ratio 给所有活跃节点统一加减分；这是 V6 路线预测标签质量风险，不只是 Arena bug |
| 连接/清洁杠杆 | CONTRADICTS 只标记不消解 | 已新增 dry-run 矛盾报告；作用是暴露 unresolved 概念冲突，不是自动修知识 |
| 观察/清洁杠杆 | ENV_FACT 新鲜度与当前状态锚定 | 已新增 dry-run freshness 报告；作用是防止旧环境事实污染 Genesis 自我建模 |
| 观察杠杆 | background daemon 维护链 | Yoga 当前 active 是 `yogg-auto.service`，`genesis-daemon.service` inactive；daemon 逻辑是代码路径风险，不等于当前 live 循环 |
| 写入/连接杠杆 | witness chain / lineage / 经济成本 / EPISODE 消费 | 暂不追求全修；只选择能提高 Genesis 自我概念模型质量的最小改动 |
| 观察/连接杠杆 | 技能发现层 | 已新增只读 `skill_inventory`，暴露物理技能资产地图；不自动 import、不执行、不安装依赖，先让 Yogg 能看见孤儿技能材料 |

---

## 一、5/21 凌晨：崩溃循环（knowledge_state 冻结）

**现象**：5/21 00:00-04:00 期间，连续 10+ 个 session 的所有 round 共享完全相同的 issue 文本：

> "两个概念点已经沉淀到位——覆盖了一个全新的概念域：**系统的自调节协议本身**。之前50多轮都在问'缺什么'，这一轮切到了'实际在工作的是什么，以及它的故障模式是什么'"

所有 round 的 `kb_changed=False`，`progress_class=error`。

**根因**：`auto_mode.py` 的 `_build_auto_knowledge_state()` 中，非 reanchor 路径给 `raw_state.issue` 优先权。V4Loop 是纯透传 → 自我指涉循环 → issue 冻结。这是 4/8 已修复的 Bug #2 的复发形态。

**相关代码**：
- `genesis/auto_mode.py:_build_auto_knowledge_state()` — knowledge_state 优先级逻辑
- `genesis/v4/loop.py:_run_main_loop()` — V4Loop 透传 knowledge_state

---

## 二、5/21 深夜 (22:00-23:50)：模式提取爆发

这是本周产出密度最高的时段。Yogg 在 ~2 小时内创建了 50+ 个 LESSON 节点，系统性地扫描了 Genesis 代码库的架构断裂。

### 2.1 奖惩不对称

**P_REWARD_PUNISH_ASYMMETRY** (22:19)：知识治理的奖惩不对称——惩罚管道全自动 vs 奖励路径形式化。

**P_REWARD_PUNISH_LAYER_COMPARISON** (23:23, 23:37)：代码级验证——惩罚 4 层闭环（ablation 自动触发 → confidence 衰减 → GC 清理 → 硬删除）vs 奖励完全真空（trust_tier 只读不写、无自动提升管道）。

**5/23 处置**：自动硬删除末端已切断为 dry-run-first；奖惩不对称的架构判断仍成立，但 daemon 自动删节点的不可逆风险已先止血。

**推理链**：
- `genesis/v4/c_phase.py:152-156` — Arena 全局 env_ratio 判定，≥0.7 时所有活跃节点统一 success=True
- `genesis/v4/manager.py:ablation` — 自动触发衰减
- `genesis/v4/background_daemon.py:GC` — 定期清理低置信节点
- `genesis/v4/trace_pipeline/node_cleanup.py` — 清理候选管道（5/23 后 daemon 自动路径为 dry-run）

### 2.2 信任层级出生证系统

**P_TRUST_TIER_BIRTH_CERTIFICATE** (22:45)：trust_tier 是 INSERT-only 的出生证——创建时固定（HUMAN/REFLECTION/CONVERSATION/FERMENTED/SCAVENGED），运行时零晋升管道。

**推理链**：
- `genesis/v4/manager.py:create_node()` — trust_tier 在创建时赋值，之后无修改路径
- `genesis/v4/manager.py:build_reliability_profile()` — tier_bonus 基于出生证计算，非运行时表现
- `genesis/v4/c_phase.py` — C-Gardener 无 trust_tier 提升逻辑

### 2.3 节点类型永恒性

**P_NODE_TYPE_ETERNITY** (22:26)：知识节点类型创建时固定，运行时零转换。LESSON 永远是 LESSON，CONTEXT 永远是 CONTEXT。

**推理链**：
- `genesis/v4/manager.py:create_node()` — type 字段创建后无修改 API
- `genesis/v4/manager.py:update_node()` — 不包含 type 变更

### 2.4 多数据库硬编码孤岛

**P_MULTI_DB_HARDCODED_SILOS** (22:27)：三个 SQLite 数据库物理隔离，路径硬编码，零跨库 JOIN。

**推理链**：
- `~/.genesis/workshop_v4.sqlite` — NodeVault 知识库
- `runtime/traces.db` — 执行追踪
- `runtime/trace_entities.db` — Trace 实体存储
- `genesis/v4/manager.py:__init__()` — 硬编码 DB 路径
- `genesis/v4/trace_pipeline/entity_store.py:__init__()` — 独立 DB 连接

### 2.5 功能社区与知识图谱的拓扑隔离

**P_COMMUNITY_KNOWLEDGE_TOPOLOGY_ISOLATION** (22:28)：trace_pipeline 的 Louvain 社区检测与 knowledge_nodes 的图边是完全独立的拓扑空间，零交叉引用。

**推理链**：
- `genesis/v4/trace_pipeline/community_detector.py` — Louvain 算法在 trace_entities.db 上运行
- `genesis/v4/manager.py:node_edges` — 知识图谱边表，两者之间无桥接查询

### 2.6 签名学习零调用

**P_SIGNATURE_LEARNING_ZERO_CALL** (22:29)：`learn_signature_marker()` 方法存在但运行时零调用——仪式性完备。

**推理链**：
- `genesis/v4/manager.py:learn_signature_marker()` — 方法定义
- `genesis/v4/c_phase.py` — C-Phase 偏差检测理论上应调用，但实际路径断裂

### 2.7 版本系统只写不读

**P_VERSION_WRITE_ONLY** (22:29)：node_versions 表完整保存每次修改的快照（保留最近 5 版），但零消费管道——无 diff 查看、无回滚、无版本对比。

**推理链**：
- `genesis/v4/manager.py:update_node()` — 写入 node_versions 快照
- `genesis/v4/manager.py:get_node_versions()` — 方法存在但调用次数为零

### 2.8 effective_confidence 过滤-排序断裂

**P_EFFECTIVE_CONFIDENCE_FILTER_SORT_BREAK** (22:30)：`effective_confidence()` 计算了精密的质量分数（融合 confidence_score、freshness、tier_bonus、validation_bonus），但仅用于门槛过滤（<0.15 排除），排序仍用原始 confidence_score。

**推理链**：
- `genesis/v4/manager.py:effective_confidence()` — 精密质量计算
- `genesis/tools/node_tools.py:search_knowledge_nodes()` — 排序用原始 confidence_score

### 2.9 知识路由 24 节点硬预算

**P_KNOWLEDGE_ROUTING_24_NODE_BUDGET** (22:31)：知识路由层 `_apply_knowledge_routing()` 有 24 节点的硬编码上限，超出部分静默截断，无充足性判定。

**推理链**：
- `genesis/v4/loop.py:_apply_knowledge_routing()` — 24 节点硬限制

### 2.10 Arena 集体归因

**P_ARENA_COLLECTIVE_ATTRIBUTION** (22:58)：Arena 反馈使用全局 env_ratio（单轮所有工具成功率的算术平均），对所有活跃节点统一应用相同的 success/fail 判定，无 per-node 归因。

**推理链**：
- `genesis/v4/c_phase.py:152-156` — 全局 env_ratio 判定
- `genesis/v4/c_phase.py:record_usage_outcome()` — 所有活跃节点统一 success=True/False

### 2.11 ERROR_PATTERN 命名空间误归因

**P_ERROR_PATTERN_NAMESPACE_MISATTRIBUTION** (22:39)：`shell.cwd.mismatch` ERROR_PATTERN 揭示了诊断信号层的命名空间误归因仪式——错误被归因到 shell 工具，但实际根因在 cwd 解析层。

**推理链**：
- `genesis/tools/shell_tool.py:_resolve_work_dir()` — cwd fallback 链
- `genesis/v4/trace_pipeline/entity_extractor.py` — ERROR 实体提取，按工具名分类

### 2.12 V4 核心循环终止后状态真空

**P_V4_LOOP_TERMINATION_STATE_VACUUM** (22:55)：迭代硬上限触发时，知识游标被清零，跨轮记忆断裂。

**推理链**：
- `genesis/v4/loop.py:_run_main_loop()` — 迭代上限处理
- `genesis/v4/loop.py:_knowledge_cursor` — 清零逻辑

### 2.13 其他 5/21 节点（按时间排列）

- **P_KNOWLEDGE_LINEAGE_EXPLICIT_ABANDONMENT** (22:30)：parent_node_id 仪式性保留与零使用
- **P_VIRT_DUAL_IDENTITY_PARADOX** (22:32)：VIRT 节点的双重身份悖论——元认知标记的自我指涉断裂
- **P_EPISODE_TRIPLE_CONSUMER_EXCLUSION** (22:32)：EPISODE 节点的三重消费侧排除——自动产出但系统性地不可见
- **P_ORPHAN_AUDIT_EXCLUSION_BIAS** (22:33)：孤儿节点审计的排除法偏见——类型学的阶层排斥
- **P_TOOL_COST_STATS_DECISION_BREAK** (22:34)：工具成本的统计-决策断裂——精密采集但决策零消费
- **P_PLS_TYPE_ORIGIN_BIAS** (22:36)：PLS 类型出身偏见——硬编码白名单决定消费优先级而非质量信号
- **P_TOOL_COST_THREE_LAYER_ZERO_CONSUMPTION** (22:40)：工具成本的三层存在与零决策消费架构
- **P_KNOWLEDGE_LINEAGE_DUAL_TRACK_GHOST** (22:43)：知识世系的双轨断裂——声明式字段与关系式边的并行幽灵
- **P_EPISODE_DUAL_IDENTITY_PARADOX** (22:45)：EPISODE 的双重身份悖论——结构性纪念品
- **P_CONTRADICTS_RITUAL_MARKING** (22:51)：CONTRADICTS 边的仪式性标记——检测完备但消解真空
- **P_KNOWLEDGE_INFRA_CONCEPT_IMPL_BREAK** (22:53)：知识基础设施的概念-实现断裂——witness_chain 与 snapshot_equivalence 的知识空洞
- **P_REASONING_CHAIN_CAPTURE_CONSUMPTION_BREAK** (22:56)：推理链的采集-消费断裂——reasoning_content 被捕获但 C-Gardener 上下文构建零遍历
- **P_CROSS_SESSION_MEMORY_LAYER_ASYMMETRY** (22:57, 23:03)：跨会话记忆的层间不对称——auto_mode 磁盘持久化 vs V4 核心循环内存游标
- **P_TOOL_CONTRACT_TRIPLE_BREAK** (22:59)：ShellTool use_sandbox 的构造器配置-schema 缺失-执行访问漂移
- **P_VERSION_LINEAGE_SCHEMA_ABSENCE** (23:01)：版本世系的 schema 缺席——扁平快照替代演化链
- **P_CONTRADICTS_RESOLUTION_VACUUM** (23:03, 23:20)：CONTRADICTS 消解真空——检测完备但零自动消解管道
- **P_ENV_FACT_HYPOTHESIS_EXECUTION_DUAL_TRACK** (23:06)：ENV_FACT 假设-执行双轨断裂——记录的是 GP 假设而非执行真相
- **P_APPROACH_REDUNDANT_RECOVERY_RITUAL** (23:09)：APPROACH 作为冗余恢复的仪式性见证——工具内部恢复成功被编码为错误格式
- **P_ERROR_PATTERN_QUATERNARY_CONSUMER_VACUUM** (23:12)：ERROR_PATTERN 四元分类的消费侧真空——精密定义与零类别消费
- **P_VERIFICATION_TIME_CLASS_POLITICS** (23:16, 23:43)：验证时间的阶级政治——生产仪式的时间戳记而非质量续命机制
- **P_DAEMON_DEATH_CLEANUP_VACUUM** (23:18)：守护进程死亡导致的知识清理执行真空
- **P_FALLBACK_CHAIN_BOUNDARY_COLLAPSE** (23:28)：fallback 链边界崩溃的显式失败终端——shell.cwd.absent 作为镜像信号
- **P_FALLBACK_CANDIDATE_IMPLICIT_PRIORITY** (23:29)：Fallback 候选链的隐性优先级秩序——空间拓扑假设的硬编码与零反馈学习
- **P_SHELL_CWD_MIRROR_SIGNAL_PAIR** (23:38)：shell.cwd.mismatch 与 shell.cwd.absent 构成镜像信号对
- **P_TYPE_NAMING_QUALITY_DISGUISE_RITUAL** (23:40)：类型命名的质量伪装仪式
- **P_SYMBOL_SELF_DECEPTION_PATTERN** (23:42)：Genesis 知识系统的符号自我欺骗模式——类型标签作为质量代理的系统性误用
- **P_ETERNITY_ARCHITECTURE_PREFERENCE** (23:44)：永恒性架构偏好——出生证系统作为设计哲学
- **P_NEGATIVE_CERTAINTY_COGNITIVE_ECONOMICS** (23:45)：负面确定性的认知经济学——损失厌恶的工程化实现
- **P_COGNITIVE_DIVERSITY_ASYMMETRIC_THRESHOLD** (23:46)：认知多样性判定的非对称阈值——不足可测而充足不可判

---

## 三、5/22：隐式数据总线与技能系统

### 3.1 隐式数据总线系列（核心发现）

Yogg 在 5/22 识别出了 Genesis 的一个系统性架构模式——**隐式数据总线**：

**P_52AED97284** (23:49)：`tool_results` 隐式数据总线的类型抹平契约。`Tool.execute` 强制返回 `str`（`genesis/tools/_base.py:128`），`_classify_tool_result` 只能从中提取布尔成功/失败。

**P_92787045ED** (23:52)：操作配方的文本协议替代架构。`_summarize_consumed_tool_result`（`genesis/v4/loop.py:490-509`）是跨工具数据流的唯一通道——截断、优先级行提取、格式化包装。

**P_C2B973A54A** (23:53)：工具契约的类型强制架构。`Tool.execute` 抽象方法强制返回 `str`（`genesis/tools/_base.py:128`），输入-输出类型不对称是显式架构选择。

**P_AED75CF350** (23:54)：Blackboard 作为隐式数据总线的文本化渲染。`render_for_g`（`genesis/v4/blackboard.py:531-567`）将结构化 EvidenceEntry 强制渲染为文本摘要。

**P_3EECFED273** (23:55)：隐式数据总线的字符串强制模式。`loop.py:491` 的 `str(result or "")`、`c_phase.py:354` 的 `str(msg.content)`、`manager.py:1645` 的 `str(payload.get("content"))` 形成跨模块重复模式。

**结论**：Genesis 的跨组件通信完全依赖文本协议——结构化数据在子系统内部流通，但在跨系统边界处必须通过字符串序列化。这不是 bug，是显式的架构契约。

### 3.2 技能发现层真空

**P_SKILL_PRODUCTION_DISCOVERY_ASYMMETRY** (23:32)：技能生产-发现不对称——精密手动生产层（`genesis/tools/skill_creator_tool.py`）与历史上的发现/消费侧真空。

**P_SKILL_DISCOVERY_LAYER_VACUUM_VERIFIED** (23:36)：代码级验证——`registry.load_from_file()`（`genesis/core/registry.py:234-297`）仅接受显式路径参数。后续 `factory.py:autoload_physical_skills()` 已补启动时物理扫描，但运行时资产可见性仍缺口。

**P_SKILL_ORPHAN_RUNTIME_BLINDNESS** (23:39)：技能孤儿化的运行时监控盲区——系统完全不感知"生产→持久化→[发现缺失]→加载"的生命周期断裂。

**P_35A4B40BD6** (23:57)：43 个技能文件存在于 `genesis/skills/` 目录，启动时零自动发现。技能成为"写入即遗忘"的孤儿工件。

**5/23 处置校准**：后续代码已经存在 `factory.py:autoload_physical_skills()`，因此"零自动发现"不再完全成立；但它是启动时尝试加载，不给 Yogg 一个可审计的运行时资产地图。已新增 `skill_inventory` 只读工具：

- 只扫描 `genesis/skills/*.py` 的 AST。
- 不 import skill 文件。
- 不执行 skill 文件。
- 不安装依赖。
- 不注册技能。
- 输出 `registered` / `orphan_candidate` / `safety_rejected` / `schema_incomplete` / `parse_error` 等状态。

本地只读扫描结果：`files=41`，工具相关 `reported=37`，其中 `orphan_candidate=35`、`parse_error=1`、`schema_incomplete=1`。这不是为了立即扩大工具面，而是给 Yogg 下一轮提供新的可探索材料：哪些技能资产已存在、哪些被安全策略挡住、哪些需要修 schema、哪些可能应该转为 NodeVault TOOL 节点或文档化为废弃资产。

### 3.3 守护进程自豁免

**P_DAEMON_SELF_EXEMPTION_FALSE_LIFE** (23:33)：`cleanup_stale_heartbeats`（`genesis/v4/manager.py:1067-1076`）显式保留 daemon 自身心跳，导致守护进程死亡后心跳幽灵永存。

### 3.4 黑板收敛度误报

**P_BLACKBOARD_CONVERGENCE_FALSE_POSITIVE** (23:29)：收敛度公式 `convergence = 1.0 - unique_nodes / total_refs`（`genesis/v4/blackboard.py:418`）将高入线数误判为多样性不足——同一节点被多次引用时 convergence 趋近 1.0。

**5/23 处置**：已将黑板收敛判断拆成两类：

- `shared_anchor_detection`：多个 persona 共同指向同一基础锚点，表示共享基础，而不是知识空洞。
- `convergence_detection`：同一 persona 或单一证据源重复引用同一节点，仍表示独立证据不足。

这样 Yogg 不会把“多透镜达成共同锚点”误判为“需要继续制造新空洞”，减少自我诊断循环中的假探索压力。

### 3.5 SEQUENTIAL 关系幽灵

**P_F9704F2475** (23:50)：`SEQUENTIAL` 关系类型在 `relationship_builder.py:31` 定义完整，但整个类中只有 `build_co_occurrence` 和 `build_error_patterns` 两个实际构建方法，不存在 `build_sequential`。

---

## 四、5/23：最深架构分析

### 4.1 验证委托黑箱

**P_FA91A449C1** (03:40)：ShellTool 的 cwd 处理存在三层独立验证且互不反馈：

| 层 | 位置 | 机制 |
|----|------|------|
| 宿主执行路径 | `genesis/tools/shell_tool.py:398-402` | `_resolve_work_dir()` 精密 fallback 链 |
| 沙箱执行路径 | `genesis/tools/shell_tool.py:393-396` | 跳过 `_resolve_work_dir()`，直接 `cd {cwd}` |
| doctor.sh 路径 | `scripts/doctor.sh:42-64` | `_doctor_workspace_dir()` 容器内独立验证 |

关键 bug：沙箱路径曾引用未绑定的 `cwd_fallback_note` 变量（line 396）。

**5/23 处置**：该变量已初始化，ShellTool 结果也会输出 `[cwd-meta] requested/resolved/executor` 与 fallback 信息；但 host / sandbox / doctor 三条 cwd 验证路径仍未统一语义。

### 4.2 经济成本替代的三轨假肢（本周最深发现之一）

**P_2A71E971B9** (03:57)：Genesis 用三轨精密技术测量系统性地替代了缺失的经济成本维度：

| 轨 | 测量内容 | 消费状态 |
|----|---------|---------|
| Token 精度计量轨 | `total_tokens/input_tokens/output_tokens` 精密累计 | 仅用于 PipelineDiagnostics 告警，零经济优化消费 |
| Duration_ms 精密测量轨 | 每工具调用精确到 0.1ms（`genesis/v4/loop.py:823`） | 零决策消费，从不出现在 GP 上下文 |
| Cost_estimate 三元标签轨 | Tools 声明 cheap/moderate/expensive | GP 可偶然消费但无结构化反馈 |

**共同特征**：精密采集 + 渲染可见 + 决策层零消费。系统看起来在追踪成本，实则只提供"成本感知"的认知假肢。

### 4.3 环境自证伪真空

**P_55BA6EC790** (04:04)：ENV_FACT 节点记录的环境事实可被当前运行时直接证伪，但知识库缺乏交叉检查机制。

具体证据：
- `DISC_79FC470D` 记录 `cwd=/home/chendechusn/Genesis/Genesis`，但当前运行用户为 yoga、路径为 `/home/yoga/Genesis`——矛盾持续 30+ 天
- 4 条 ENV_FACT cwd 节点全部 `last_verified_at=NULL`
- `SurfaceExpander._calculate_priority()` 只用入线数×饱和降权，零时间/新鲜度维度
- `auto_mode.py` 的 `_EDGE_NOISE_RE` 将 `[ENV_FACT]` 主动过滤出边构建

### 4.4 质量信号的三层路径依赖不对称消费

**P_QUALITY_SIGNAL_ROUTING_PATH_DEPENDENCY** (04:12)：同一节点的"可信度"取决于它通过哪条路径被看见：

| 路径 | 质量模型 | 位置 |
|------|---------|------|
| SearchTool | `_fusion_score` 加权（trust 权重 15-25%） | `genesis/tools/node_tools.py` |
| SurfaceExpander | `_calculate_priority` 只用入线数×边权重×饱和惩罚 | `genesis/v4/surface_expander.py` |
| Blackboard | `_score_evidence` 显式注明"用入线数替代 effective_confidence" | `genesis/v4/blackboard.py` |

### 4.5 验证状态的生产-消费断裂

**P_6576866416** (04:22)：DISCOVERY→PATTERN 自动提升时，`_try_promote_to_pattern()` 硬编码 `validation_status="validated"`，但 `create_node()` 的自洽堵漏 `_has_hard_evidence()` 即时将其降级为 `"partial"`。降级信号被困在 `metadata_signature` JSON blob 中——消费侧（SurfaceExpander、SearchTool）不解析该字段。

**推理链**：
- `genesis/v4/manager.py:_try_promote_to_pattern()` — 硬编码 validated
- `genesis/v4/manager.py:create_node()` — 自洽堵漏降级
- `genesis/v4/surface_expander.py:_calculate_priority()` — 不看 metadata_signature

### 4.6 ERROR_PATTERN 因果断言误分类

**P_CWD_MISMATCH_CAUSAL_ASSERTION_FALSE** (04:28)：ERROR_PATTERN 断言 "/workspace 缺失 → shell 命令失败"，但 Doctor 沙箱中 `/workspace` EXISTS 且 shell 命令成功执行——因果断言被直接证伪。

### 4.7 词汇替代基础设施

**P_VOCABULARY_SUBSTITUTION_INFRASTRUCTURE** (03:23)：多个领域中的精密词汇（time_decay、recency_bias、witness_chain、knowledge_state、budget、cost、shell.cd、cwd.mismatch）被用作基础设施存在的代理，而非描述实际存在的功能。

### 4.8 knowledge_state 词汇跨层身份漂移

**P_KNOWLEDGE_STATE_IDENTITY_DRIFT** (03:19)：词汇 `knowledge_state` 指向两个完全不相关的数据模型：
- **模型 A**：NodeVault 元数据签名（`genesis/v4/signature_engine.py`）
- **模型 B**：auto_mode 知识状态（`genesis/auto_mode.py:_build_auto_knowledge_state()`）

两者共享词汇标记但不共享 schema、代码路径或语义。

### 4.9 文本中介的信念修订

**P_TEXT_MEDIATED_BELIEF_REVISION** (03:16)：Evidence Assessor 的信念修订管道不是基于结构化证据关系，而是基于文本关键词匹配协议——`_match_errors()` 要求至少 2 个词命中。

**推理链**：
- `genesis/v4/trace_pipeline/evidence_assessor.py:_match_errors()` — 关键词模糊匹配

### 4.10 Evidence Assessor 静默信念污染

**P_EVIDENCE_ASSESSOR_SILENT_CONTAMINATION** (03:09)：两套完全独立的系统修改同一字段（`usage_success_count`）：
- Arena（主动反馈）：C-Phase 每轮基于 env_ratio 判定
- Evidence Assessor（被动观察）：基于 resolves 文本匹配

两者互不知晓，语义不可解析。

**5/23 处置**：Evidence Assessor 已改为 dry-run/passive，只返回 `applied=False` 的 reinforced/weakened 候选，不再写入 Arena 共享计数字段。剩余问题是文本模糊匹配仍粗糙，且 Trace Entity 身份仍被压平成 value 文本。

### 4.11 DISCOVERY 类型认知黑洞

**P_DISCOVERY_COGNITIVE_BLACK_HOLE** (03:01)：DISCOVERY 四个子分类（TOOL_BEHAVIOR/ENV_FACT/APPROACH/ERROR_PATTERN）在生产侧有精密定义和四级冗余存储，但所有消费管道将它们视为无差别的 DISCOVERY。

### 4.12 伪经济词汇语义假肢

**P_PSEUDO_ECONOMIC_SEMANTIC_PROSTHESIS** (02:53)：系统使用经济学术语（cost/budget/expensive/cheap）描述纯技术维度，形成经济意识的假象但无实际经济内容。

三根假肢：
1. 工具契约层：`cost_estimate` 返回 "cheap"|"moderate"|"expensive"
2. 上下文管理层：`context_budget` 作为节点数量上限
3. 提示工程层：`TOKEN_BUDGET_THRESHOLD` 作为硬截断

### 4.13 自我模型的反射替代

**P_SELF_MODEL_REFLECTION_SUBSTITUTION** (02:06)：Genesis 有 reflection 词汇（12 处）但零 `self_model`/`self_awareness`/`metacognition`/`self_identity`/`introspection` 匹配——系统用"反思"完全替代了"自我模型"。

### 4.14 工具结果六层类型抹平级联

**P_TOOL_RESULT_SIX_LAYER_ERASURE** (01:45)：工具结果从执行到消费经历 6 层独立机制的类型抹平：

| 层 | 位置 | 抹平内容 |
|----|------|---------|
| L1 抽象契约强制 | `genesis/tools/_base.py:128` | execute() -> str |
| L2 防御性二次转型 | `genesis/v4/loop.py:491` | str(result or "") |
| L3 回调文本化 | `genesis/auto_mode.py` | step_callback 只传字符串 |
| L4 C-Phase 文本解析 | `genesis/v4/c_phase.py:354` | str(msg.content) |
| L5 Trace 实体提取 | `genesis/v4/trace_pipeline/entity_extractor.py` | 正则匹配文本 |
| L6 Evidence Assessor | `genesis/v4/trace_pipeline/evidence_assessor.py` | 关键词模糊匹配 |

### 4.15 Persona 学习系统

**P_PERSONA_SURFACE_COMPLETENESS** (01:38)：四层表面完备（采集→持久化→加载→决策影响）但两层结构性断裂：
1. 采纳数据的幽灵基础设施——两个采集管道并存但都不完整
2. 信用归因真空——用全局 env_ratio 而非 per-persona 采纳率

**P_PERSONA_SIGNAL_PRECISION_PARADOX** (01:40)：信号精度-可归因性选择悖论——系统倾向于使用粗糙但可全局获得的信号（env_ratio 胜率）而非精确但需要个体归因的信号（采纳率）。

### 4.16 维护管道无声消亡

**P_MAINTENANCE_PIPELINE_SILENT_DEATH** (01:20)：背景守护进程的多层维护管道（签名审计、GC、节点清理、拓扑审计、证据评估）存在递归隐藏——拓扑审计报告的发现仅以 `logger.info` 输出，无告警或自动修复。

**P_TOPOLOGY_AUDIT_CLEANUP_DUAL_TRACK** (01:02)：拓扑审计-清理的发现-行动双轨断裂：
- 精密诊断层：`genesis/v4/manager.py:972-1055` `topology_audit_report()`
- 清理层：`genesis/v4/trace_pipeline/node_cleanup.py` 使用完全独立的逻辑

**运行态注记**：Yoga 当前运行主服务是 `yogg-auto.service`；`genesis-daemon.service` inactive。所以上述维护链目前主要是代码路径风险，只有 daemon 被启动后才会自然执行。5/23 已将 daemon 中的 GC/cleanup 自动删除改为 dry-run 报告。

### 4.17 Trace-Knowledge 桥接点实体身份坍缩

**P_ENTITY_IDENTITY_BRIDGE_COLLAPSE** (07:17)：Trace Entity Store 管理着 19,636 个规范实体、96,212 次跨 session 出现记录，但唯一桥接点 `Evidence Assessor.assess_evidence()` 主动丢弃全部实体身份结构——只提取 value 文本字段做关键词模糊匹配。

### 4.18 三重计数本体架构

**P_TRIPLE_COUNT_ONTOLOGY_SILOS** (07:22)：三个完整但隔离的频次/信誉计数基础设施：

| 系统 | 测量对象 | 消费 |
|------|---------|------|
| Trace Entity Store occurrence_count | 执行痕迹出现频率 | 仅展示 + EvidenceAssessor 文本匹配 |
| knowledge_nodes.usage_count | 知识节点激活频率 | PLS 排序和节点选择 |
| usage_success/fail_count | 节点使用结果质量 | 原为双源（Arena+EvidenceAssessor）写入；5/23 后 EvidenceAssessor 已隔离为 dry-run，Arena 集体归因仍存在 |

### 4.19 信号精度反转

**P_BDFA6A1DE1** (07:26)：越贴近决策的计数精度越粗——Trace Entity Store（per-entity，最高精度）零决策消费，Knowledge Arena（全局 blob，最低精度）唯一直接影响知识置信度。

### 4.20 Evidence Assessor 污染 Arena 信号

**P_EVIDENCE_ASSESSOR_ARENA_SIGNAL_CONTAMINATION** (07:30)：原始风险/历史状态中，被动评估器通过关键词模糊匹配判断 LESSON 是否"生效"，并将结果写入与 Arena 共享的 `usage_success_count` 列。保护阈值（wins>=5 不被削弱）形成单向信用膨胀通道。

**5/23 处置**：该写入路径已隔离为 dry-run 候选报告；Arena 共享计数字段不再被 Evidence Assessor 修改。但 `_match_errors()` 文本匹配、Trace 实体身份坍缩、wins>=5 的候选保护逻辑仍保留。

**推理链**：
- `genesis/v4/trace_pipeline/evidence_assessor.py:109-130` — 被动强化/削弱候选记录，`applied=False`
- `genesis/v4/trace_pipeline/evidence_assessor.py:122-124` — wins>=5 候选保护
- `genesis/v4/trace_pipeline/evidence_assessor.py:158-177` — _match_errors 模糊匹配
- `genesis/v4/trace_pipeline/runner.py:138` — 仅在 rebuild_relationships=True 时触发

### 4.21 Knowledge Arena 确认偏误

**P_ARENA_CONFIRMATORY_BIAS** (06:12)：Arena 的全局信用归因架构导致结构性确认偏误——所有活跃节点共享同一 success/fail 标签，无法区分"真正有效的节点"和"碰巧在成功轮次中被激活的节点"。

### 4.22 见证链幽灵

**P_WITNESS_GHOST_TYPE_AB_DISTINCTION** (05:31)：Genesis 没有 witness chain 或 chain of trust 的概念词汇或基础设施。它拥有五个不连接的信任/溯源孤岛——trust_tier 出生证、provenance 实体溯源、node_versions 版本链、reanchor 信号、evidence_refs 证据校验——各自覆盖信任链的一个切片，但无任何机制将它们连接成可追溯的见证链。

### 4.23 5/23 后续节点

- **P_ECONOMIC_COST_VOCABULARY_ABSENCE** (04:42, 04:53)：经济成本词汇的系统性技术替代架构——代码级验证
- **P_CWD_FALLBACK_SIGNAL_COLLAPSE** (04:42, 04:52)：cwd fallback 补偿信号的三层语义坍缩
- **P_ENV_FACT_MIRROR_SPATIAL_IDENTITY_DUALITY** (04:44, 05:04)：ENV_FACT 镜像信号对的空间-身份双重断裂
- **P_EXCEPTION_SILENT_SWALLOW** (04:52)：异常静默吞噬模式的代码级验证
- **P_TOKEN_BUDGET_AS_ECONOMIC_SUBSTITUTE** (04:55)：Token 预算作为经济决策的技术替代架构
- **P_C4DCED6008** (04:45, 05:03)：概念词汇的代码级幽灵化——time_decay/recency_bias 标签存在但实现真空
- **P_FREQUENCY_SIGNAL_CROSS_LAYER_SEMANTIC_SPLIT** (05:05)：频次信号的跨层语义分裂——决策信号与展示信号的功能性不对称
- **P_ECONOMIC_COST_CODE_LEVEL_VACUUM_VERIFIED** (05:07)：经济成本词汇的代码级真空验证——技术计量对经济学概念的系统性替代
- **P_FEEDBACK_CREDIT_ASSIGNMENT_COLLAPSE** (05:08)：反馈信用归因坍缩——已达深层隐藏状态

### 4.24 5/23 后续人工处置状态

- **Evidence Assessor**：已从“被动写 Arena 成绩”改为“只读 dry-run 候选报告”；信号污染已止血，文本匹配粗糙仍存在。
- **ShellTool**：已补 cwd metadata；能看见 requested/resolved/executor/fallback，但三条 cwd 验证路径尚未统一。
- **Node cleanup**：daemon 自动 GC/cleanup 已改为 dry-run-first；`would_delete` 表示候选，`hard_deleted` 表示真实删除。
- **Yoga 运行态**：当前 active 服务是 `yogg-auto.service`；`genesis-daemon.service` inactive，因此 daemon 维护链不会自然产生日志，除非显式启动。
- **CONTRADICTS**：已新增 dry-run 矛盾报告，把 `CONTRADICTS` 边区分为 recent/stale/orphan/both_active/unresolved_active；仍不自动降权、不删除、不升格。
- **ENV_FACT**：已新增 dry-run freshness 报告，把环境事实区分为 unverified/stale/current-state-sensitive/runtime-mismatch-candidate；仍不自动改写、不自动失效。
- **方向切换**：不要继续逐条打补丁；转入 `docs/knowledge_governance_layer.md`，把这些 dry-run 报告收束为统一的信号生命周期与治理动作门。
- **主线校准**：Knowledge Governance 不是终点，只是清洁杠杆。本文后续问题优先级应按“是否提高 Genesis 自我概念模型的杠杆效率、是否为 V6 用户小模型留下更干净的 state-action-outcome 轨迹”来判断。

---

## 五、总结：5/21-23 的三层递进

```
5/21 深夜：模式提取（What is broken?）
    ↓ 系统性扫描，50+ 断裂点
5/22 全天：机制分析（How is it broken?）
    ↓ 隐式数据总线、类型抹平契约、技能发现真空
5/23 凌晨：根因诊断（Why is it broken?）
    ↓ 经济成本缺失、信号精度反转、桥接点身份坍缩
```

**核心洞察**：Yogg 的分析深度在三天内逐层递进——从"列举断裂"到"描述机制"到"诊断根因"。5/23 凌晨的分析质量是本周最高点：不仅定位了具体代码行，还识别出了跨模块的系统性模式（三轨假肢、六层抹平、三重计数、信号精度反转），并将它们追溯到设计哲学层面的选择（"文本协议作为通用中介"、"出生证系统作为设计哲学"、"负面确定性的认知经济学"）。

**但关键限制未变**：在该观察窗口内，Yogg 的输出仍主要停留在只读诊断层；后续修复需要外部执行者接手，并且应优先采用 dry-run/report-first 的方式，避免把模糊诊断直接变成自动改写知识的动作。
