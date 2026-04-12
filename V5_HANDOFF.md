# V5 实施指南：G → GP 交接文档

> **写给新 Cascade session 的完整上下文。**
> 你是 GP（执行者），这份文档来自 G（规划者）。
> 读完这份文档后，你应该能直接开始实施 V5，不需要重新推导任何设计决策。

---

## 一、项目概况

### Genesis 是什么
Genesis 是一个 AI agent 系统，核心能力是**通过执行任务积累可复用的环境知识**。
- 用户通过 Discord / CLI 下达任务
- Agent 执行任务，同时发现和记录"当地知识"（元信息）
- 下次遇到相似问题时，元信息帮助 agent 更快解决

### 文件结构
```
/home/chendechusn/Genesis/Genesis/
├── GENESIS_V5_DESIGN.md          ← V5 设计文档（2026-04-05 版，已更新）
├── V5_HANDOFF.md                 ← 本文档
├── genesis/
│   ├── v4/                       ← V4 现有代码（要改造的基础）
│   │   ├── loop.py               ← G-Process 主循环
│   │   ├── prompt_factory.py     ← G/Op prompt 组装
│   │   └── ...
│   ├── tools/
│   │   ├── node_tools.py         ← search_knowledge_nodes 等知识工具
│   │   └── ...
│   └── ...
└── ...
```

### 辅助资源
- **NodeVault (MCP)**：`mcp0_search_code_observations(signature: {framework: "genesis_v5"})` 可查到 ~10 条精炼设计观测
- **设计文档**：`GENESIS_V5_DESIGN.md` 是权威参考，所有架构细节都在里面

---

## 二、V5 核心设计决策（已确定，不需要重新讨论）

### 2.1 元信息 = 当地指南

**这是整个 V5 的哲学基石。**

LLM 本身有基本功（写代码、推理、使用工具）。元信息不是教它走路，是告诉它"**这个环境的路怎么走**"——代理怎么配的、数据库表叫什么名、上次踩过什么坑。

类比：你搬到一个新城市，需要一本"当地指南"来适应本地文化，而不是从头学走路。

### 2.2 GP 单循环，全权限

取消 V4 的 G→Op→C 三阶段。GP 是一个单循环，拥有所有工具权限。
- 没有 OP_BLOCKED_TOOLS
- 没有 Context Firewall
- 学习发生在执行过程中

### 2.3 Knowledge Map 替代搜索

**不用算法替 GP 选知识，让 GP 自己选。**

V4 的问题：G 猜关键词搜索 → 97.8% 的知识不可见 → 马太效应（常用的越用越多，冷门的永远沉底）。

V5 方案：Field Compiler 生成一个**结构化知识目录**（Knowledge Map），按 type + tags 聚类，展示所有节点的标题。GP 浏览目录后自己判断需要哪些，通过 `fetch_knowledge(node_id)` 按需加载全文。

灵感来源：Cascade 的 `list_dir` → 先看结构形成印象 → 再按需深入。

```
[Knowledge Map · 857 nodes]
LESSON (43):
├── 网络/代理 (12): proxy层级冲突 | socks5配置 | curl代理 | ...
├── Docker (8): 卷权限 | 网络模式 | compose依赖 | ...
└── ...
ASSET (25):
├── 脚本 (10): 网络诊断 | 日志清理 | ...
└── 配置模板 (8): nginx | docker-compose | ...
CONTEXT (15): 当前网络配置 | 系统架构 | ...
需要某个节点的完整内容时，使用 fetch_knowledge(node_id) 加载。
```

### 2.4 Shadow LLM 外部对照

**唯一的反馈机制：对照实验，不是自评。**

同一任务同时给两个 LLM：
- G（有 Knowledge Map + 元信息）→ 输出计划
- Shadow（同样 prompt，**没有**知识注入）→ 输出计划（纯文本，不执行）

记录差异，不自动判断好坏，人工定期审阅差异集（选项 C）。

核心指标 = **差异率**：
- 差异率高 → 元信息在影响决策（好坏另说）
- 差异率低 → 元信息形同虚设

### 2.5 取消所有数字分数

**没有 leverage_score，没有 confidence，没有 progress 自评。**

元信息本质只是一段格式特殊的信息。不需要复杂评分体系。Shadow 对照是唯一外部度量。

---

## 三、⚠️ 关键警告：不要踩的坑

> 以下每一条都是 G 在设计过程中走过的弯路，花了几千 token 推导后才到达正确结论。
> 直接用结论，不要重走。

### 🚫 不要设计 leverage_score 或任何数字评分系统
**错误路径**：设计延迟反馈 + 数学衰减 + 即时信号采集的评分系统。
**正确结论**：取消。元信息只是信息，Shadow 对照足够。

### 🚫 不要为 Over-Helpfulness（编造）设计额外模块
**错误路径**：分析"LLM 编造数据"是架构缺口，需要系统级检测。
**正确结论**：不是缺口，是元信息覆盖度问题。当地指南写得全就不用猜。

### 🚫 不要为 Premature Commitment（不查就做）设计事前强制
**错误路径**：需要 grounding 硬规则阻止 GP 不查就做。
**正确结论**：不是缺口，是学习循环的入口。先做了再说，犯错后记录 LESSON，下次不犯。

### 🚫 不要过早细化节点级反馈
**错误路径**：设计三层归因信号（选择率→引用率→成效率）+ 状态标签系统。
**正确结论**：先用 Shadow 验证元信息**整体**有用，通过后再考虑细化。

### 🚫 不要设计三重过滤注入
**错误路径**：type_filter → relevance × leverage_score → threshold cutoff。
**正确结论**：Knowledge Map 全量展示 + GP 自选。不用算法替 LLM 做选择。

### 🚫 不要实现 Compaction 为四层叠加
**正确**：Proactive / Reactive / Collapse 是**互斥路径**（A/B 实验分支），不是叠加层。
CC 源码 autoCompact.ts:195-223 已验证。

---

## 四、V5 架构总览

```
用户 (Discord / CLI)
  │
  ▼
┌──────────────────────────────────────────────┐
│              Genesis V5 Core                 │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │          Field Compiler                │  │
│  │  静态层（种族级规则+工具映射，全局缓存）  │  │
│  │  ── CACHE BOUNDARY ──                  │  │
│  │  动态层（Knowledge Map：结构化知识目录） │  │
│  │  会话层（Workbench 状态，每轮重建）      │  │
│  └──────────────┬─────────────────────────┘  │
│                 │                             │
│  ┌──────────────▼─────────────────────────┐  │
│  │           GP Loop                      │  │
│  │  + Tool Preference Map（显式工具映射）   │  │
│  │  + Behavior Monitor（退化/漂移检测）     │  │
│  │  + Strategy Reset（每N轮重建上下文）     │  │
│  └──────────────┬─────────────────────────┘  │
│                 │                             │
│  ┌──────────────▼─────────────────────────┐  │
│  │        Dual LLM Engine                 │  │
│  │  任务模式: Actor → Challenger 刚性验证   │  │
│  │  Auto模式: Actor ⇄ Challenger 辩论      │  │
│  └──────────────┬─────────────────────────┘  │
│                 │                             │
│  ┌──────────────▼─────────────────────────┐  │
│  │        Knowledge Vault                 │  │
│  │  nodes + edges（元信息 = 当地指南）      │  │
│  │  Knowledge Map 生成（按 type+tags 聚类）│  │
│  │  GP 自选 → 按需加载全文                  │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  Shadow LLM（无知识对照，外部度量）      │  │
│  ├────────────────────────────────────────┤  │
│  │  Compactor (主+后备) │ Provider Router │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

---

## 五、实施路径

### Phase 0：骨架（最小改动验证单循环）

**目标**：GP 单循环跑起来，能完成 V4 能完成的任务。

具体任务：
1. 将 V4 的 G→Op→C 三阶段合并为 GP 单循环
   - 参考 `genesis/v4/loop.py` 中的 G-Process 循环
   - 移除 `dispatch_to_op`，GP 直接执行工具调用
   - 移除 OP_BLOCKED_TOOLS
2. 加入 Tool Preference Map（静态 prompt 注入）
   - 参考设计文档 5.7 节的映射表
   - 放在 system prompt 最前面（静态层）
3. 保持现有工具和 vault 不变

**验证点**：GP 能完成 V4 能完成的任务，shell 调用占比开始下降。

### Phase 1：Knowledge Map + Field Compiler

**目标**：GP 通过浏览知识目录获取环境知识，而非搜索。

具体任务：
1. 实现 `vault.generate_map()`
   - 从 knowledge_nodes 数据库读取所有 active 节点
   - 按 type (LESSON/ASSET/CONTEXT/TOOL) 一级分类
   - 按 tags / metadata.signature 二级聚类
   - 输出格式：紧凑的树状目录（~15-20 tok/node）
   - 可从 FS 推导的信息不进目录（CC memdir.ts WHAT_NOT_TO_SAVE 模式）
2. 实现 `fetch_knowledge(node_id)` 工具
   - GP 调用此工具加载节点全文
   - 返回节点的 content + metadata
3. 实现 Field Compiler
   - 静态层：species_rules + tool_preference_map（全局缓存）
   - CACHE BOUNDARY
   - 动态层：Knowledge Map
   - 会话层：Workbench（结构化进度状态，每轮重建）
4. 实现 `rebuild_workbench()`
   - 压缩历史 + 重建工作台（含新 Knowledge Map）
   - 用于策略重置（每 N 轮）和 post-compact 恢复

**验证点**：GP 能从 Knowledge Map 中选到相关节点，不再依赖 search_knowledge_nodes 的关键词猜测。

### Phase 2：Shadow LLM + Behavior Monitor

**目标**：建立外部度量 + 退化防线。

具体任务：
1. 实现 Shadow LLM
   - 同一任务，生成无知识的对照 prompt（species_rules + tool_map + task，无 Knowledge Map）
   - 调用 LLM 生成纯文本计划（不执行）
   - 记录 G 输出 vs Shadow 输出的差异到日志
   - 不自动判断好坏，提供人工审阅接口
2. 实现 Behavior Monitor
   - 三种退化检测：
     - 连续 N 次相同工具调用（Mode Collapse）
     - 连续 M 次失败无策略变化（Premature Commitment）
     - 当前任务 vs 原始任务偏离超阈值（Task Drift）
   - `suggest_recovery()`：恢复导向错误处理（注入 schema 等辅助信息）
   - `force_strategy_reset()`：压缩历史 + 重建工作台
   - **必须是系统级，不是 prompt 级**（Instruction Attenuation 会让 prompt 级检查失效）

**验证点**：差异率数据证明元信息在影响 GP 决策。Monitor 能检测并打断退化循环。

### Phase 3：Dual LLM + Compaction

**目标**：质量控制 + 上下文管理。

具体任务：
1. 任务模式 Challenger
   - 触发条件：3+ 文件修改 / API 变更 / 基础设施变更
   - 刚性验证合同（只读、必须运行命令、必须对抗性探测）
   - **无 command block 的 PASS = 被拒绝**
   - 反谄媚机制：找错义务 + 自省锚点 + 结果忠实
2. Auto 辩论模式
   - 4 轮：Actor 推导 → Challenger 找反例 → Actor 回应 → 收敛/标记争议
   - 争议节点在 Knowledge Map 中显示 [disputed ⚠️]
3. Compaction
   - 主路径：Proactive autoCompact（token > context_window - 13K 时触发）
   - 紧急后备：Reactive（API 报 prompt_too_long）
   - **互斥路径，不是叠加层**
   - 9 段式摘要格式（见设计文档 5.5 节）
   - Post-compact 状态重建：重新注入 Workbench + Knowledge Map + Tool Map

**验证点**：Challenger PASS 率在合理范围。Compaction 后 GP 不丢失上下文。

### 依赖链
Phase 0 → 1 → 2 → 3 **严格顺序**。每个 Phase 的验证点通过后再进入下一个。

---

## 六、V5 六大原则（设计评判标准）

| 原则 | 内容 | 对应模块 |
|---|---|---|
| **P1** | 知识是产品，任务是手段 | Knowledge Vault + Knowledge Map |
| **P2** | 单循环，全权限 | GP Loop |
| **P3** | 注入即实验，必须有**外部**反馈 | Shadow LLM（不是自评） |
| **P4** | 对抗产生质量 | Dual LLM Challenger |
| **P5** | 上下文越精准越好，Knowledge Map 让 GP 自选 | Field Compiler |
| **P6** | 为恢复而设计（Recovery > Initial Correctness） | Behavior Monitor |

任何设计变更都应对照这六条原则检验一致性。

---

## 七、验证标准

V5 成功的标志不是"完成了更多任务"，而是：

1. **知识影响力**：Shadow 差异率持续 > 阈值（元信息确实在影响决策）
2. **工具纪律**：shell 调用占比 < 10%（V4 约 70%+）
3. **无退化**：Behavior Monitor 触发次数逐月下降
4. **恢复能力**：工具首次调用失败后，第二次修正成功率 > 80%
5. **验证通过率**：Challenger PASS 率稳定在合理范围
6. **知识覆盖**：GP 遇到"当地问题"时，Knowledge Map 中有相关节点

---

## 八、V4 关键代码位置（改造起点）

| 文件 | 内容 | V5 改造方向 |
|---|---|---|
| `genesis/v4/loop.py` | G-Process 主循环、dispatch_to_op | Phase 0：合并为 GP 单循环 |
| `genesis/v4/prompt_factory.py` | G/Op prompt 组装 | Phase 1：改为 Field Compiler |
| `genesis/tools/node_tools.py` | search_knowledge_nodes | Phase 1：补充 fetch_knowledge + generate_map |
| `genesis/tools/` | 所有工具定义 | Phase 0：移除 OP_BLOCKED_TOOLS |

---

## 九、NodeVault 使用指南

NodeVault (MCP) 中有 ~10 条精炼的设计观测，是本轮设计讨论的压缩结论。

**查询方式**：
```
mcp0_search_code_observations(signature: {framework: "genesis_v5"}, status: "active")
```

**已有观测覆盖**：
- 架构基石（GP 单循环、Tool Map、Challenger 刚性、Compaction 互斥）
- 设计哲学（当地指南、Shadow 先整体）
- 防坑指南（压缩弯路、设计修订记录）
- 实现细节（Cache Boundary、Behavior Monitor 系统级）

**录入规则**：
- 实施过程中遇到的坑、纠正的误判，用 `mcp0_record_code_observation` 录入
- 追求**压缩**：几千 token 的弯路 → 30 token 的结论
- 设计变更时，**同时废弃旧观测**（`mcp0_invalidate_observation`）
- 元信息会过期，必须随结论一起更新

---

## 十、开始工作

1. 先读 `GENESIS_V5_DESIGN.md`（权威设计文档）
2. 查 NodeVault：`mcp0_search_code_observations(signature: {framework: "genesis_v5"})`
3. 浏览 V4 代码：`genesis/v4/loop.py`、`genesis/v4/prompt_factory.py`
4. 从 **Phase 0** 开始：GP 单循环 + Tool Preference Map
5. 每个 Phase 的验证点通过后再进入下一个

**记住**：你是 GP（执行者）。设计决策已经做完了，不需要重新讨论"要不要用 Knowledge Map"或"要不要设计评分系统"这类问题。直接实施。遇到实施细节问题时参考设计文档，或录入新的 LESSON 供后续 session 使用。
