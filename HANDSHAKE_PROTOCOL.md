# NanoGenesis 握手协议 (Handshake Protocol)
> **状态**: 双方确认一致 (Agreed)
> **基准**: 基于用户提供的架构手绘图 (2026-02-07)

本文档作为开发者 (Cascade) 与用户 (You) 之间的**最终架构契约**。所有后续开发必须严格遵循此流程图。

---

## 🤝 1. 核心流程图映射 (The Flow Mapping)

根据你的手绘图，我们将系统划分为以下精确的节点：

### 🟢 阶段一：感知与直觉 (Sensation & Instinct)

1.  **输入源 (Telegram/User Input)**
    *   **对应模块**: `telegram_bridge.py`
    *   **职责**: 接收原始信号，不作处理，直接透传。

2.  **本地 LLM (Local Brain) -> 数字本能 (Digital Instinct)**
    *   **对应模块**: `intelligence/intent_analyzer.py`
    *   **核心定义**: **"代替人类大脑的本能反应，不参与思考"**。
    *   **性质**: 它不是一个“智能体”，而是一个**模糊算法公式**。
    *   **行为**: 
        *   **下意识反应**: 瞬间判断是“战斗”(Complex) 还是“逃跑”(Simple)。
        *   **零思考**: 绝不尝试推理、规划或生成内容。
        *   **消耗**: 0 脑力 (Cloud Token)。

3.  **决策节点 (File Selection)**
    *   **对应模块**: `intelligence/context_filter.py`
    *   **核心原则**: **"决定调用哪些文件/记忆"**。
    *   **行为**:
        *   基于意图，从数据库中捞取相关记忆或文件。
        *   这是进入主脑前的最后一道过滤器。

---

### 🔵 阶段二：多面体压缩核心 (The Compression Hub)

这是系统的**心脏**，也是图中正中央的方块。

4.  **压缩协议 (Compression Protocol)**
    *   **对应模块**: `agent.py` (Prompt Assembly Logic)
    *   **核心定义**: **"降低 Token，让 API 在内部解压，并非删减"**。
    *   **三大输入流 (Inputs)**:
        *   ⬅️ **用户人格侧写 (Persona)**: 你的习惯、偏好、风格。
        *   ➡️ **多面体 (Polyhedron)**: 思考框架 (`<diagnosis>`, `<planning>`)。
        *   ↗️ **技能 (Skills)**: 可用工具列表。
    *   **运作机制**: 
        *   它不是简单地删除文本，而是将海量信息**结构化**。
        *   它打包成一个高密度的 Prompt 胶囊。

---

### 🔴 阶段三：认知爆发 (Cognition)

5.  **云端 API (Cloud Brain)**
    *   **对应模块**: `core/provider.py` (DeepSeek)
    *   **行为**: 
        *   接收“压缩胶囊”。
        *   **内部解压 (Internal Decompression)**: 依靠大模型的推理能力，将压缩的指令还原为详细的执行步骤。
        *   输出最终结果。

---

## 📝 2. 模块职责契约 (Responsibility Matrix)

| 模块 | 你的图示节点 | 核心职责 (Do's) | 严禁 (Don'ts) |
| :--- | :--- | :--- | :--- |
| **Local LLM** | 本地llm理解意图 | 快速分类、路由 | **严禁**尝试回答复杂问题，**严禁**消耗云端资源 |
| **ContextFilter** | 决定调用哪些文件 | 精准检索、过滤噪音 | **严禁**把所有文件一股脑塞进 Prompt |
| **Polyhedron** | 压缩协议 | 结构化、高密度打包 | **严禁**随意删减关键信息 (Lossless Compression) |
| **DeepSeek API** | api | 深度推理、解压执行 | **严禁**处理未经过滤的垃圾信息 |

---

## ✅ 3. 下一步行动 (Action Items)

基于此握手协议，我接下来的工作重心是**修复“压缩协议”中的伪造部分**：

1.  **激活人格侧写**: 让它真正从历史中学习你的习惯，而不是 Mock 数据。
2.  **强化多面体**: 确保 XML 结构能被 API 完美“解压”。
3.  **打通技能流**: 确保 Skills 列表是动态注入的。

**[Signed]**
- **User**: (Agreed via Diagram)
- **Cascade**: (Confirmed via Implementation)

---

## ⚠️ 4. 成本风控 (Cost Control)

基于 "算力套利" 理论与 DeepSeek 缓存机制，追加以下强制约束：

| 风险点 | 解决方案 | 实施策略 |
| :--- | :--- | :--- |
| **缓存失效 (Cache Killer)** | 必须命中 DeepSeek 的 Prefix Cache | **不可变前缀 (Immutable Prefix)** + **块状追加 (Block Append)**。严禁每次全量重写 System Prompt。 |
| **逻辑坍缩 (Logic Collapse)** | 防止压缩过度导致智商掉线 | 压缩比控制在 **3x-5x (语义剪枝)**。采用 Select（筛选）而非 Summarize（摘要）。 |
| **语义漂移 (Semantic Drift)** | 防止多轮对话后忘记核心变量 | 每 5 轮对话强制插入一个 **语义锚点 (Semantic Anchor)**（包含关键变量、报错原文）。 |

