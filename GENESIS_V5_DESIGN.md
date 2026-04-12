# Genesis V5 设计方案

> 基调：Genesis 最大的杠杆是信息利用。任务是手段，知识是目的。
>
> 版本：2026-04-05-R3 · **GP 统一 + V4 深度修补 + 新能力增量添加，非重写**
>
> V4 观测 + LLM 定律 + CC 源码验证 + Knowledge Map 重构 + GP 统一 + 知识驱动任务

---

## 一、理论基础：LLM 定律与行为模式

> 所有定律/模式已与 Claude Code v2.1.92 (Apr 2026) 生产代码交叉验证。

### 1.1 Scaling Laws

| 定律 | 核心结论 | 来源 |
|---|---|---|
| Kaplan (2020) | Loss 与模型大小/数据/计算量呈幂律关系 | [arxiv:2001.08361](https://arxiv.org/abs/2001.08361) |
| Chinchilla (2022) | 最优训练需平衡参数与数据（~20 tok/param） | [arxiv:2203.15556](https://arxiv.org/abs/2203.15556) |
| Inference Scaling (2024+) | 推理时投入更多算力，效果单调改善 | OpenAI o1/o3, DeepSeek R1 |

<!-- V5-REL: 关键决策值得花更多 token，常规操作应快速通过 -->

### 1.2 Behavioral Failure Modes（V4 实际观测映射）

| 失效模式 | V4 实际表现 | 来源 |
|---|---|---|
| **Context Rot** | 83.7万tok消耗、G重复派发25次 | [Chroma 2025](https://research.trychroma.com/context-rot) |
| **Instruction Attenuation** (39%衰减) | Op第1轮选shell策略后锁死55次 | [Springer 2025](https://ceaksan.com/en/llm-behavioral-failure-modes) |
| **Task Drift** | 从"分析LLM物理"漂移到"用shell查sqlite" | 同上 |
| **Mode Collapse** | 重复 shell→sqlite→写节点 循环 | [Holtzman 2019](https://arxiv.org/abs/1904.09751) |
| **Incorrect Tool Invocation** | search_knowledge_nodes参数错→被LLM"拉黑" | KAMI 2025 |
| **Reward Hacking (Goodhart)** | progress=strong但效率为零 | Goodhart's Law |
| **Sycophancy** | V4无Challenger，无对抗验证 | [Anthropic 2024](https://arxiv.org/abs/2401.05566) |
| **Degeneration Loop** | G反复派发"读取llm_physics节点" | Holtzman 2019 |

<!-- CC-VERIFY: prompts.ts:233 反退化指令 "Don't retry the identical action blindly" -->

### 1.3 Agentic Failure Patterns (KAMI)

> 来源：[KAMI v0.1](https://arxiv.org/html/2512.07497v1)，900个agent执行轨迹分析

**四个行为原型**：
1. **Premature Commitment** — 跳过grounding步骤（V4: Op猜列名不先查schema）
2. **Over-Helpfulness** — 数据缺失时自主替换而非报告（V4: shell兜底）
3. **Context Pollution / "契诃夫之枪"** — 把所有上下文当信号（最强模型30次中10次失败）
4. **Fragile Tool-Use Under Stress** — 错误恢复循环中连贯性崩溃

**KAMI核心结论**：**Recovery capability — not initial correctness — best predicts success.**

| Emergent Principle | CC生产验证 |
|---|---|
| 规模≠可靠性 | CC对所有模型用相同safeguard |
| 错误反馈引导恢复 | verificationAgent.ts: 错误消息应建议修正路径 |
| 上下文质量>数量 | autoCompact.ts: 主动清除旧工具结果 |
| 源数据对齐 | prompts.ts: "Read code before suggesting modifications" |

### 1.4 Context Engineering 原则

| 策略 | CC实现 | 来源 |
|---|---|---|
| Select & Retrieve | POST_COMPACT_TOKEN_BUDGET=50K, 每文件限5K | [Adaline 2025](https://labs.adaline.ai/p/context-rot-why-llms-are-getting) |
| Summarize & Compress | compact/prompt.ts 9段式结构化压缩 | CC源码 |
| Isolate Workspaces | getScratchpadInstructions() 独立临时目录 | CC源码 |
| Instrument & Prune | Function Result Clearing + stripImagesFromMessages() | CC源码 |

<!-- Karpathy 2025: "Context is compute." -->

---

## 二、V4 的教训（观测驱动）

> 来自V4 auto运行透明化日志(RichAutoCallback)直接观测。

### 根本问题
V4知识系统"只写不验"。写了大量节点但：不知道哪些有效，不知道注入什么能提升成功率，无淘汰机制。

### 架构缺陷（附观测证据）

| 缺陷 | 观测证据 | 根因映射 |
|---|---|---|
| G→Op→C割裂 | Op因OP_BLOCKED_TOOLS用shell绕道55次 | Incorrect Tool Invocation |
| 单LLM盲跑 | G派发25次相同方向，无人刹车 | Mode Collapse + Degeneration Loop |
| 上下文原始 | 83.7万token，大量重复 | Context Rot |
| 工具接口脆弱 | search_knowledge_nodes参数错后被"拉黑" | Premature Commitment |
| 评估虚高 | progress=strong，实际效率≈0 | Reward Hacking |

### 核心教训
1. 执行和学习不应分开——学习发生在执行过程中
2. 没有评估的知识积累 = 垃圾堆积（Goodhart's Law）
3. 没有对抗的推理 = 套壳复述（Sycophancy）
4. 上下文越少越精准越好，不是越多越好（Context Rot）
5. **恢复能力 > 首次正确率**——为恢复而设计（KAMI核心结论）

### 元信息的本质定位：当地指南

元信息 = **当地指南**。LLM 本身有"基本功"（写代码、推理、使用工具），元信息告诉它"**这个环境的路怎么走**"——代理怎么配的、数据库表叫什么名、上次踩过什么坑。不是教它走路，是帮它适应当地文化。

由此推导：
- **Over-Helpfulness（编造）不是架构缺口**——是元信息覆盖度问题。覆盖好就不需要猜。
- **Premature Commitment（不查就做）不是缺口**——是学习循环的入口。先做了再说，经验回馈，下次不犯。
- **Goodhart（自评虚高）删除自评环节**——取消置信度/杠杆分等数字分数，Shadow 对照是唯一外部度量。
- **置信度/杠杆分可以取消**——元信息本质只是一段格式特殊的信息，不需要复杂评分体系。

---

## 三、V5 核心原则

> **方向修正**：经分析，V4 三阶段（G→Op→C）的核心痛点不在于架构本身，而在于自我施加的信息截断
> 和工具限制。修补这些问题 + 增量添加新能力，比推倒重写风险更小、收益更确定。

### P1：知识是产品，任务是手段
每一次任务执行，核心目标不仅是完成任务，更是：
- 发现哪些知识有效
- 发现哪些知识无效或有害
- 产生新的、经过验证的知识

### P2：GP 统一（思考+执行合一）→ C 反思

> **方向修正 R3**：原 P2 主张“保留 G→Op→C 三位一体”。经实际运行观测，三阶段的核心痛点在于：
> 1. **dispatch 协议脆弱**：G 的 dispatch 质量直接决定 Op 质量，但 dispatch 丢失上下文
> 2. **工具封锁造成绕道**：Op 缺搜索工具→shell绕違55次
> 3. **信息截断严重**：G→Op→C 每个节点都在压缩/截断信息
>
> **解法：合并 G+Op 为 GP，保留 C 独立反思。**

- **GP = 思考者+执行者**：拥有完整上下文和所有工具，搜索→思考→执行→回复。无 dispatch，无信息丢失
- **C = 反思者**：专注知识提炼，仅允许节点管理工具，注意力 100% 给知识沉淀
- **去除信息截断**：C-Phase 接收完整执行信息（10 处截断全部移除）✅
- **迭代上限软提醒**：到达 80% 上限时注入提醒，不硬截断

GP 统一的优势：
- 零信息丢失（无 dispatch 压缩、无上下文切换）
- 工具全量可用（无 OP_BLOCKED_TOOLS 限制，仅 C-Phase 专属工具限制）
- 執行中可随时搜索知识库、随时调整策略
- C 的注意力仍然 100% 给知识提炼（独立阶段保留）

### P3：知识驱动任务
每个用户任务都是**知识区域的天然实验场**。GP 接到任务后做两件事：
1. **任务路径**：怎么完成用户的请求（正常规划）
2. **知识路径**：这个任务触及的知识区域有哪些 VOID？能否顺便设计最小实验来验证？

代价极低（每次任务多 1-2 个诊断命令），但知识增长从 daemon 后台线性产出变为与任务量成正比增长。
用得越多，知道得越多——正反馈。

**替代 Scavenger/Fermentor/Verifier**——这三个 daemon 是脱离真实任务的人造实验，产出低质量。
在真实任务中观测到的东西更可靠。只保留 Doctor（沙箱自诊断）。

### P4：上下文是稀缺资源，越精准越好
- 动态知识通过 **Knowledge Map**（结构化目录）让 G 自选，按需加载全文
- 不用算法替 G 选择——LLM 天生擅长从标题列表识别相关性，前提是让它看到选项
- **Knowledge Arena 废除**——Arena 的排名服务于 V4 简陋的检索，Knowledge Map 让 G 自选后排名无意义
- 知识淘汰靠**语义去重 + 环境过期**，不靠使用频率（频率淘汰会杀死知识驱动任务的探索性产出）

### P5：为恢复而设计
- 工具错误消息应**引导恢复**，不只报告失败
- 连续失败时系统自动注入辅助上下文（如 schema 信息）
- Behavior Monitor 检测"连续失败无策略变化"，强制重置
<!-- THEORY: KAMI "Recovery > Initial Correctness"
     CC-VERIFY: prompts.ts:233 "diagnose why before switching tactics" -->

### P6：远期探索方向（不在当前实施范围）
以下方向记录备查，待当前修补稳定后再评估：
- **System 1/System 2 快慢双系统**：圆锥凝实度分流——高凝实区域用便宜/快模型，低凝实用强模型
- **DAG 并行执行图**：替代顺序循环，并行执行无依赖的子任务
- **Shadow LLM 对照**：同任务无知识注入，测量元信息的因果影响（消融实验）
- **元信息注入格式压缩**：Level 0（自然语言）→ Level 1（结构化缩写，~20 tok/node）
- **Shadow diff 度量信息增量**：按信息量分配 token 预算，增量为 0 的节点从 Map 中去掉

---

## 四、V5 架构

> GP 统一 + C 反思。基于 V4 深度修补 + 增量添加。

```
用户 (Discord / CLI)
  │
  ▼
┌──────────────────────────────────────────────┐
│         Genesis V5 (GP 统一 + 修补)           │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │     [Multi-G 视角] (MBTI 人格模型)    │  │
│  │  ✅ 多人格模型激活                      │  │
│  │  ✅ Blackboard 信息交换/排序/注入 GP    │  │
│  └──────────────┬─────────────────────────┘  │
│          │                             │
│  ┌──────────────▼─────────────────────────┐  │
│  │     GP-Process（思考者+执行者，已重写） │  │
│  │  ✅ DoingTasks 准则（改编自 CC）         │  │
│  │  ✅ Tool Preference Map（显式工具映射）  │  │
│  │  ✅ Knowledge Map 注入（~960 tokens）     │  │
│  │  ○ 知识驱动：任务路径 + 知识路径双规划   │  │
│  │  ○ Behavior Monitor（退化/漂移检测）     │  │
│  └──────────────┬─────────────────────────┘  │
│                 │                             │
│  ┌──────────────▼─────────────────────────┐  │
│  │     C-Process（反思者，已增强）          │  │
│  │  + 接收完整执行信息（无截断）            │  │
│  │  + VOID 升格路径保留                     │  │
│  │  + 知识驱动任务的探索性产出记录          │  │
│  └──────────────┬─────────────────────────┘  │
│                 │                             │
│  ┌──────────────▼─────────────────────────┐  │
│  │        Knowledge Vault（已增强）         │  │
│  │  ✅ 信息截断全部移除                     │  │
│  │  ✅ Knowledge Map 生成                   │  │
│  │  ○ 淘汰机制：语义去重 + 环境过期（待）  │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  ✅ 后台守护: GC + 签名审计（零LLM）    │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ✅ 已砍掉: Scavenger / Fermentor / Verifier │
│  ✅ 已砍掉: Dispatch / Op-Process / Op-Prompt │
│  远期探索: System 1/2, DAG, Shadow 对照      │
└──────────────────────────────────────────────┘
```

---

## 五、核心模块设计

### 5.1 已完成：信息截断移除（裹脚布清理）

V4 中大量自我施加的字符截断，导致下游阶段（尤其 C-Phase）在残缺信息上做决策。**全部移除：**

| 位置 | 截断 | 改动 |
|---|---|---|
| `loop.py` C 执行摘要 | 工具结果 200 字符 | → 完整 |
| `loop.py` C 执行摘要 | AI 推理 100 字符 | → 完整 |
| `loop.py` Op 超时路径 | 工具结果 150 字符 | → 完整 |
| `loop.py` Op 超时路径 | assistant 800 字符 | → 完整 |
| `loop.py` 搜索 | conversation_context 300 字符 | → 完整 |
| `loop.py` 签名合并 | raw_output 1200 字符 | → 完整 |
| `prompt_factory.py` | knowledge_state issue 240 字符 | → 完整 |
| `prompt_factory.py` | knowledge_state 各字段 220 字符 × 5 条上限 | → 完整，不限条数 |
| `prompt_factory.py` | G 的 raw_output 2000 字符 | → 完整 |
| `prompt_factory.py` | 短期记忆用户 500 / 回复 800 | → 完整 |

### 5.2 已完成：GP 统一（G+Op 合并）✅

> **方向修正 R3**：原 5.2 主张"Op 搜索封锁（G/Op 职责分离）"，原 5.3 主张"Dispatch 协议简化"。
> 经实际观测，dispatch 协议本身是不必要的复杂性来源。解法：直接合并 G+Op 为 GP。

**已删除的 Op 架构组件**：
- `dispatch_to_op` 工具 + `DispatchTool` 注册 → 已从 factory.py 移除
- `DispatchPayload` / `OpResult` 数据模型 → 已从 models.py 删除
- `build_op_prompt` / `render_op_result_for_g` / `render_dispatch_for_human` → 已从 prompt_factory.py 删除
- `OP_MAX_ITERATIONS` / `op_max_iterations` / `op_max_consecutive_errors` → 已从 config 和 loop.py 删除
- `genesis/tools/dispatch_tool.py` / `tests/test_dispatch_tool.py` → 文件已删除

**GP 统一后的架构**：
- GP 拥有完整上下文（用户对话 + 知识搜索结果 + 工具执行结果）
- GP 拥有所有工具（仅排除 C-Phase 专属的节点管理工具）
- 防御性拦截：LLM 万一尝试调用已废弃的 `dispatch_to_op`，返回错误提示
- `from_op_result()` 保留为向后兼容别名，委托给新的 `from_result()`

### 5.4 已完成：Knowledge Map ✅

**问题**：G 只能通过 `search_knowledge_nodes` 搜索已知关键词。不知道搜什么 → 看不到 → 用不上。
当前 `get_digest()` 仅显示类别计数和少量亮点（~8行），97.8% 的节点对 G 不可见。

**方案**：在 G prompt 中注入**分层标签地图**，让 G 看到知识的全貌（哪些领域有覆盖、哪些有空洞）。

```
[Knowledge Map · 674 nodes · 12 VOID]

LESSON (257): 经验教训
├─ 网络/代理 (12): proxy层级冲突 | socks5直连优化 | curl代理参数 | +9
├─ Docker (8): 卷权限模式 | 网络模式选择 | compose依赖链 | +5
├─ Genesis (45): dispatch协议 | Op工具选择 | C原子性 | +42
├─ Python (15): pip路径 | venv迁移 | 包版本冲突 | +12
├─ 系统管理 (18): systemd单元 | 日志轮转 | 磁盘清理 | +15
└─ ... (159 nodes in 10 other clusters)

ASSET (25): 可复用资产
├─ 脚本 (10): 网络诊断 | 进程检查 | +8
└─ 配置模板 (15): nginx | compose | systemd | +12

CONTEXT (15): 环境快照
├─ 网络 (5): v2rayA配置 | DNS设置 | +3
└─ 项目 (10): 目录结构 | API密钥布局 | +8

[知识空洞] 12 VOID: geoip与tproxy优先级 | sing-box迁移路径 | +10

→ search_knowledge_nodes("关键词") 获取某区域详情
```

**设计要点**：

1. **分层聚类**：按 `type` → `primary_tag`（节点 tags 字段的首标签）自动分组
2. **每簇展示 Top 3 标题**：足够让 G 识别相关性，看到领域有什么
3. **每类型最多 8 簇**：防止 prompt 爆炸，长尾归入"其他 N 簇"
4. **Token 预算 ~1-2K**：约 30-50 行。DeepSeek 前缀缓存下，跨请求零额外成本
5. **VOID 区域内联**：交叉查询 `void_tasks` 表，展示知识空洞（圆锥模型的洞）
6. **与 digest 共存**：digest 保留（PROVEN/UNTESTED 亮点），Map 补充全貌

**实现（已完成）**：
- `vault.generate_map()` ✅ 新方法，查询所有非 MEM_CONV 节点，按 type + 有意义标签 聚类生成文本
  - 噪声标签跳过（`auto_managed` 等），无有意义标签时从标题提取主题词
  - 实测：2151 节点 → 71 行、~960 tokens
- `build_gp_prompt()` 注入 Map 块 ✅（放在 digest 后面，变量内容区）
- **不新增工具**：G 用现有 `search_knowledge_nodes` 钻入感兴趣的区域即可
- 后续可选：`fetch_knowledge(node_id)` 按需加载单节点全文（视实际需求决定）

**与 V4 搜索管线的关系**：
- Map **不替代**搜索（向量→Cross-Encoder→signature_gate 仍然保留）
- Map 解决**发现**问题（G 知道什么存在），搜索解决**检索**问题（G 拿到详情）
- 两者互补：Map 帮 G 选对搜索关键词，搜索返回精排结果+Graph Walk

### 5.5 待实施：知识驱动任务

在 GP prompt 中注入双规划框架：

```
你接到了一个任务。在规划执行路径时，做两件事：

1. [任务路径] 怎么完成用户的请求（正常规划）

2. [知识路径] 这个任务触及的知识区域有哪些未验证假设（VOID）？
   你的执行过程能否顺便设计一个最小实验来验证它？
   - "顺便" = 不超过 2 步额外操作
   - 不能为了填 VOID 牺牲任务质量
   - 但如果代价极低（一条额外的诊断命令），就去做
```

Knowledge Map 的输出也需配合：

```
[知识区域: v2ray/routing]
  ✅ LESSON_014: tag 不匹配时 v2ray 走默认路由
  ✅ LESSON_022: v2ray tag 修改后需重启服务生效
  🕳️ VOID_037: geoip 数据库与 tproxy 规则的优先级关系
  凝实度: 中 (2 实/1 空)
  本次任务可探测: VOID_037
```

**替代 Scavenger/Fermentor/Verifier**：这三个 daemon 的知识生产功能由知识驱动任务接管。
Daemon 的人造实验产出低质量，真实任务中的观测更可靠。

### 5.6 待实施：知识淘汰机制

Knowledge Arena 废除后，需要新的淘汰机制防止知识库膨胀，且不能误杀探索性产出。

**淘汰策略**：
- **语义去重**：如果两个节点语义重复（向量相似度 > 阈值），合并或删弱的那个
- **环境过期**：节点带环境签名 + 时间戳。环境已变（如从 v2ray 迁到 sing-box）时，旧节点标记 historical，不参与 Map 展示但不物理删除
- **不用使用频率淘汰**：频率淘汰会杀死知识驱动任务的探索性产出（新节点必然使用次数少）

### 5.7 已完成：Daemon 清理 ✅

| Daemon | 处置 | 原因 |
|---|---|---|
| **Scavenger（拾荒者）** | ✅ 砍掉 | 产出零使用率，Autopilot 替代 |
| **Fermentor（发酵者）** | ✅ 砍掉 | 69 假设节点零使用率 |
| **Verifier（验证者）** | ✅ 砍掉 | LLM 审计成本高、信号弱 |

`background_daemon.py`：611 → 95 行。仅保留 **GC**（`purge_forgotten_knowledge`）+ **签名审计**（`audit_signatures`），零 LLM 成本。
原文件归档于 `archive/daemon_deprecated/`。

> 注：原设计中的"Doctor（沙箱诊断）"实际从未作为独立 daemon 实现，其概念等同于主循环的诊断能力。

### 5.8 待实施：Behavior Monitor

> V4 没有此模块。基于 auto 观测和 LLM 定律研究新增。

```python
class BehaviorMonitor:
    """系统级干预，不依赖 prompt（Instruction Attenuation 会让 prompt 级检查失效）"""

    def detect_degeneration(self, messages) -> bool:
        """任一触发：
        1. 连续 N 次相同工具调用（Mode Collapse / Degeneration Loop）
        2. 连续 M 次失败但无策略变化（Premature Commitment）
        3. 当前任务描述与原始任务偏离超阈值（Task Drift）"""
        ...

    def suggest_recovery(self, failed_tool_call, error_result) -> str:
        """恢复导向：不只报告"Error: 列ntype不存在"，
        而是注入 schema 信息引导修正。
        THEORY-REF: KAMI "error messages should suggest corrective paths" """
        schema = self.get_relevant_schema(failed_tool_call)
        return f"[Recovery Hint] {error_result}\n可用字段: {schema}"
```

<!-- CC-VERIFY: autoCompact.ts:67-70 有类似 circuit breaker：
     MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3 -->

### 5.9 已完成：Tool Preference Map ✅

> CC 用**显式枚举**解决 shell 绕道。已注入 GP prompt。

实际注入内容（`prompt_factory.py` `build_gp_prompt`）：
```
# 工具使用规则
- 搜索知识用 search_knowledge_nodes，不要用 shell + sqlite3 CLI
- 读写文件用 read_file/write_file，不要用 shell cat/echo
- shell 仅用于系统命令和终端操作。有专用工具时，必须优先用专用工具。
```

### 5.10 已完成：GP Prompt 重写 ✅

> 参考 CC v2.1.92 `prompts.ts` 的 `getSimpleDoingTasksSection`、`getUsingYourToolsSection`、`DEFAULT_AGENT_PROMPT`。
> **方向修正 R3**：原为 G/Op 双 prompt 重写。GP 统一后合并为单一 `build_gp_prompt`，Op prompt 已删除。

**GP prompt**（`build_gp_prompt`）：
- **任务执行准则**（改编自 CC DoingTasks）：先读再改、失败先诊断不盲重试、不超范围、不投机防御
- **工具使用规则**（Tool Preference Map，见 5.9）
- **Knowledge Map 注入**（见 5.4）
- **Multi-G Blackboard 注入**（透镜阶段产出）

**已删除**：`build_op_prompt` / `render_op_result_for_g` / `render_dispatch_for_human`（见 5.2）

---

## 六、与 V4 原版的关键差异总结

| 维度 | V4 原版 | V5 (GP 统一 + 修补) | 状态 |
|---|---|---|---|
| 执行模型 | G→Op→C 三阶段 | **GP→C 两阶段**（G+Op 合并） | ✅ |
| Dispatch | G→dispatch→Op 协议 | **已删除**（GP 直接执行，零信息丢失） | ✅ |
| C 信息质量 | 200 字符截断摘要 | 完整信息传递（10 处截断移除） | ✅ |
| GP prompt | G/Op 分离双 prompt | 统一 `build_gp_prompt`（DoingTasks + Tool Map + Knowledge Map） | ✅ |
| 工具使用 | 无约束，shell 兜底 | Tool Preference Map 显式映射 | ✅ |
| Daemon | 4 个（Scavenger/Fermentor/Verifier/GC） | 仅 GC + 签名审计（零 LLM 成本） | ✅ |
| 知识发现 | G 猜关键词搜索，97.8%不可见 | Knowledge Map 分层标签地图（~960 tokens） | ✅ |
| Multi-G | 无 | MBTI 人格矩阵 + Blackboard 汇聚注入 GP | ✅ |
| 知识生产 | C-Phase 被动记录 | 知识驱动任务：任务路径+知识路径双规划 | ✅ |
| 评分体系 | Knowledge Arena (confidence/leverage) | **保留**（信号弱，待 Behavior Monitor 激活） | ✅ 决定 |
| 错误处理 | 报告错误 | Behavior Monitor 恢复导向 | ○ 待做 |
| 退化检测 | 无 | Behavior Monitor 系统级干预 | ○ 待做 |

**已砍掉的模块**：Dispatch 协议、Op-Process、Op-Prompt、Scavenger、Fermentor、Verifier、Dual LLM、Shadow LLM、Compactor。

---

## 七、实施路径

> 每个 Phase 独立可验证，不依赖后续 Phase。

### Phase 1：裹脚布清理 ✅
- [x] 移除 `loop.py` 中 6 处信息截断
- [x] 移除 `prompt_factory.py` 中 4 处信息截断
- **验证点**：C-Phase 产出的 LESSON 质量是否提升

### Phase 2：Prompt 重写 + Daemon 清理 ✅
- [x] GP prompt 重写：DoingTasks 准则 + Tool Preference Map
- [x] 砍掉 Scavenger / Fermentor / Verifier（`background_daemon.py` 611→95行）
- **验证点**：daemon 零 LLM 成本运行

### Phase 3：Knowledge Map ✅
- [x] 实现 `vault.generate_map()`（按 type+有意义标签 分层聚类，噪声标签跳过，标题提取回退，~960 tokens）
- [x] `build_gp_prompt()` 注入 Knowledge Map 块（digest 后、signature 前）
- [ ] 实测运行，观察 GP 使用 Map 选节点的效果
- **验证点**：GP 搜索命中率提升（Map 帮 GP 选对关键词）

### Phase 3.5：GP 统一（G+Op 合并）✅
- [x] 合并 G-Process 和 Op-Process 为统一的 GP-Process
- [x] 删除 dispatch 协议（`dispatch_to_op` 工具、`DispatchPayload`/`OpResult` 模型）
- [x] 删除 Op prompt（`build_op_prompt`/`render_op_result_for_g`/`render_dispatch_for_human`）
- [x] 清理残留配置（`OP_MAX_ITERATIONS`、`op_max_iterations`、diagnostics breaker）
- [x] 清理死文件（dispatch_tool.py、backup 文件、临时文件）
- [x] GitNexus 全量扫描验证：零断链、零残留
- **验证点**：所有文件 py_compile 通过；GitNexus 图谱零 Op 调用残留

### Phase 4：知识驱动任务 + 知识淘汰 ← **当前**
- [x] GP prompt 注入双规划框架（任务路径 + 知识路径）✅
- [x] Knowledge Map VOID 展示增强（6条样本 + 签名标签 + source 分布）✅
- [x] Knowledge Arena 评估：**保留**（机制正确但信号弱：98.9%胜率/14L，待 Phase 5 Behavior Monitor 提供更精细的成功/失败判定后激活）
- [x] 语义去重淘汰：**已在 RecordLessonNodeTool 中实现**（≥0.85 合并，0.65-0.85 建边）✅
- [ ] 环境过期标记（签名漂移检测 + historical 标记）→ 延至 Phase 4.5
- **验证点**：知识驱动产出的 LESSON 数量 > 0；知识库大小可控

### Phase 5：Behavior Monitor
- [ ] 实现退化检测（重复工具调用 / 连续失败无策略变化 / 任务漂移）
- [ ] 实现恢复导向错误处理（失败时注入 schema 等辅助信息）
- **验证点**：Behavior Monitor 触发时成功恢复的比例

### 依赖链
Phase 1 ✅ → Phase 2 ✅ → Phase 3 ✅ → Phase 3.5 ✅ → Phase 4（依赖 Phase 3 的 Map）→ Phase 5（独立，可与 4 并行）

---

## 八、验证标准

V5 成功的标志不是"完成了更多任务"，而是：

1. **C 产出质量**：信息截断移除后，C 的 LESSON 原子性和准确性提升
2. **工具纪律**：shell 绕道次数显著下降（V4 约 55 次/session → 目标 < 5）
3. **知识可见性**：G 通过 Knowledge Map 能看到全量知识目录，不再 97.8% 不可见
4. **知识增长率**：知识驱动任务使每次执行都有知识产出（VOID 探测 + LESSON 记录）
5. **退化控制**：Behavior Monitor 检测并恢复退化循环
6. **知识库健康**：语义去重 + 环境过期使知识库大小可控，无冗余膨胀

---

## 附录 A：来源索引

| 标记 | 含义 | 示例 |
|---|---|---|
| `CC-VERIFY` | 已在 CC v2.1.92 源码中验证的结论 | autoCompact.ts 互斥路径 |
| `CC-REF` | CC 源码具体位置引用 | verificationAgent.ts:82-91 |
| `THEORY` | LLM 理论/定律依据 | Goodhart's Law, Context Rot |
| `THEORY-REF` | 具体论文/研究引用 | KAMI v0.1, Chroma 2025 |
| `设计修正` | 相对原方案的修正，附修正原因 | Dream → 数学衰减 |

### 关键 CC 源文件索引

| 文件 | 内容 | V5 对应模块 |
|---|---|---|
| `prompts.ts` | 系统 prompt 组装，15个可组合 section | Field Compiler |
| `systemPromptSections.ts` | 缓存/非缓存 section 机制 | Cache Boundary |
| `systemPrompt.ts` | prompt 层级覆盖逻辑 | Field Compiler 静态层 |
| `verificationAgent.ts` | 验证 agent 完整 prompt (153行) | Dual LLM Challenger |
| `autoCompact.ts` | 主动压缩触发逻辑 + circuit breaker | Compactor |
| `compact/prompt.ts` | 9段式压缩摘要格式 | Compactor 摘要格式 |
| `compact/compact.ts` | 压缩执行 + post-compact 状态重建 | Post-Compact 重建 |
| `memdir/memdir.ts` | 记忆系统：类型分类+WHAT_NOT_TO_SAVE | 类型过滤器 |

### 关键论文/研究索引

| 简称 | 全称 | URL |
|---|---|---|
| Chroma 2025 | Context Rot: Entropy-Based Analysis | [link](https://research.trychroma.com/context-rot) |
| Adaline 2025 | Why LLMs Are Getting Worse at Context | [link](https://labs.adaline.ai/p/context-rot-why-llms-are-getting) |
| Springer 2025 | LLM Behavioral Failure Modes | [link](https://ceaksan.com/en/llm-behavioral-failure-modes) |
| KAMI v0.1 | Agent Task Benchmark (900 trajectories) | [arxiv](https://arxiv.org/html/2512.07497v1) |
| Holtzman 2019 | Neural Text Degeneration | [arxiv](https://arxiv.org/abs/1904.09751) |
| Kaplan 2020 | Neural Scaling Laws | [arxiv](https://arxiv.org/abs/2001.08361) |
| Chinchilla 2022 | Training Compute-Optimal LLMs | [arxiv](https://arxiv.org/abs/2203.15556) |
| Anthropic 2024 | Sycophancy in RLHF | [arxiv](https://arxiv.org/abs/2401.05566) |
