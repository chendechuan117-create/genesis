# Genesis 核心架构真理地图 (The Source of Truth)

> **[GENESIS DIRECTIVE]**：此文档是 Genesis 系统的物理法则与唯一真理。禁止未来的任何 AI 助理凭空脑补系统结构。在修改任何模块前，必须查阅本档案以确认模块职责边界。**严禁在核心引擎中进行针对特定组件的 if/else 硬编码。** 所有新能力、新供应商、新模型必须通过 `registry.py` 以插件形式动态挂载。

---

## 🏗️ 1. 系统骨架映射 (Architectural Topology)

Genesis 系统的代码物理分布遵循严格的“**核心引擎驱动 + 动态插件扩展**”结构。

### 🧠 主轴核心 (The Spine & Brain)
绝对核心的运转逻辑。**原则上禁止随意修改这些文件中的业务流程，它们的职责仅限于流转和调度**。本架构严格遵循**“情境包装与清白执行的双轨制 (Dual-Track Packager-Executor Paradigm / Decoupled Execution from Packaging)”**。系统被切割为负责沟通与筹备的实体 B（Packager）和纯粹负责干活的实体 A（Executor）。
*   `nanogenesis/genesis/agent.py` & `nanogenesis/genesis/core/packager.py` - **认知主控制器 & 包装器 (实体 B / Context Packager & Orchestrator)**：系统的总入口与前端大脑。负责生命周期管理、策略调度和宏观任务流转。
    1. **Context Packager (前置侦察)**：它承载着会话状态与记忆，负责与用户进行正常、符合语境的聊天。当对话**需要转化为物理行动时**，它变成“先锋侦察兵”，利用只读工具（`ls`, `cat` 等）扫描项目环境，打包出一份绝对纯净、没有任何闲聊干扰的《行动指南 (Mission Payload)》，空投给底层的实体 A。
    2. **Z 轴调度 (The Z-Axis Jump)**：当收到 `[CAPABILITY_FORGE]` 信号时，它负责拦截主线并横向派生 Z 轴的“能力锻造子任务”。
    3. **Phase 3 Packager (后置包装)**：接收实体 A 底层无生命特征的执行日志，结合上下文记忆，将其包装为连贯的自然语言回复人类。
*   `nanogenesis/genesis/core/loop.py` - **无状态执行门 (实体 A / Stateless Executor Sub-Agent)**：真正下达修改和执行指令的行动端。**它被物理剥夺了获取用户上下文和历史对话的能力。** 它的出生即被实体 B 喂养了“全开视野”的上下文（行动指南），唯一要做的就是专注写代码、改文件、调工具。此机制彻底消灭了 LLM 在执行环境交互时的文本“幻觉”、“找不到文件”和“偷懒心理”。内部集成了智能容错与 Ouroboros 熵值断路器机制。
*   `nanogenesis/genesis/core/cognition.py` - **认知处理器**：管理反思、策略生成和深度思考协议 (`Polyhedron` 等)。在 Phase 1 (战略阶段)，协助实体 B 提炼问题意图并下发给 `loop.py`，或在需要时触发 `[CAPABILITY_FORGE]` 求生本能。

### 💡 插件化注册骨干 (The Registry Backbone)
**这是解决误删和级联崩溃的终极方案。** 系统不再依赖硬编码来判断应该调用哪个组件。
*   `nanogenesis/genesis/core/registry.py` - **万物注册表**：全局单例。管理 `Provider`、`Tool`、`Skill` 的注册与实例化。
*   `nanogenesis/genesis/core/factory.py` - **动态装配车间**：读取配置并依据 `registry.py` 的清单，动态构建和拉起所需的系统组件。

### 🔌 供应商与算力 (Providers)
负责与各大 LLM 对接的驱动隔离层。
*   `nanogenesis/genesis/core/provider_manager.py` - **供应商路由网关**：负责处理 API 的负载、重试与 Failover。
*   `nanogenesis/genesis/core/provider.py` - **云端/通用驱动**。包含 **The Silent Thinker (物理隔离阀门)**：负责在底层截断 Executor 产生的 `<reflection>` 内部推演标签，确保返回层级的永远是绝对干净的动作。
*   `nanogenesis/genesis/core/provider_local.py` - **本地算力驱动**。

### 🛠️ 工具与躯体 (Tools & Skills)
*   `nanogenesis/genesis/tools/` - **原子级原生工具**：
    - `visual_tool.py`: Visual processing tool mapping to VLM inference.
    - `web_tool.py`: Standard web search.
    - `browser_tool.py`: Physical browser automation.
    - `douyin_tool.py`: Target specific site logic (e.g. Douyin API/Scraping).
    - `system_health_tool.py`: Health checking diagnostic tool.
    - `spawn_sub_agent_tool.py`: Tool to delegate tasks to a sterile sub-agent sandbox.
    - `check_sub_agent_tool.py`: Tool to retrieve the results from a running sub-agent.
    - `skill_importer_tool.py`: The Assimilator Tool for securely absorbing 3rd party scripts.
    - `evomap_skill_search_tool.py`: The survival instinct search tool connecting to OpenClaw / EvoMap.
    - `chain_next_tool.py`: Tool to ensure long tasks are logically separated into multiple turn chains.
*   `nanogenesis/genesis/tools/spawn_sub_agent_tool.py` & `sub_agent_manager.py` - **异步子代理沙盒**：支持将高容错、长耗时任务剥离给便宜的耗材 API（隔离主脑 Token 消耗）。
*   `nanogenesis/genesis/tools/skill_importer_tool.py` - **跨框架技能同化器**：负责拉取外部开源 Agent 脚本（如 OpenClaw），经过安全审计后重写为本地原生技能。
*   `nanogenesis/genesis/tools/github_skill_search_tool.py` - **求生直觉网格**：当原生工具失效时，赋予 Genesis 去 Github 自动寻猎可用组件的基础嗅觉。
*   `nanogenesis/genesis/skills/` - **复合技能**：由 Agent 动态学习或造物主（Skill Creator）现场锻造的复杂操作流。
*   `nanogenesis/genesis/core/sandbox.py` - **执行安全屏障**。

### 🧬 高阶认知与进化体系 (Intelligence & Evolution)
*   `nanogenesis/genesis/intelligence/adaptive_learner.py` - **潜意识组装与认知折叠**：吸收子代理带回的《操作复盘 (Cognitive Insights)》，通过握手协议（Handshake Protocol）确认后，无缝融合进主脑的 System Prompt 中，实现永久基因变异。
*   `nanogenesis/genesis/intelligence/intent_analyzer.py` - 解析用户隐式意图。
*   `nanogenesis/genesis/intelligence/polyhedron_prompt.py` - 构建高维的结构化推演 Prompt。
*   `nanogenesis/genesis/intelligence/protocol_encoder.py` - 协议与信号编码层。
*   `nanogenesis/genesis/intelligence/protocol_decoder.py` - 将控制标记解析为机器意图 (例如将 `[CAPABILITY_FORGE]` 转换为程序操作)，剥离核心引擎的硬编码癌。
*   `nanogenesis/genesis/intelligence/strategy_tool.py` - 纯逻辑面的策略制定外设模块。
*   `nanogenesis/genesis/intelligence/tool_generator.py` - `skill_creator` 依赖的底层生成器，负责无结构指令到代码的翻译。
*   `nanogenesis/genesis/intelligence/troubleshoot_tool.py` - 故障排查逻辑抽象。
*   `nanogenesis/genesis/intelligence/user_persona.py` - 长期会话中提取的用户画像。

### 💾 记忆、感知与信号处理 (Memory, Entropy & Signal)
*   `nanogenesis/genesis/core/context.py` - **短期上下文缓冲**：管理与当前任务紧密相关的系统、历史和用户消息。内置了 Stateless Executor 的 `sys_prompt`。
*   `nanogenesis/genesis/core/context_pipeline.py` - 会话管线与长短期缓冲合并管道。
*   `nanogenesis/genesis/core/memory.py` - **长期持久化接口**：定义与具体存储介质间（SQLite等）的抽象。
*   `nanogenesis/genesis/memory/` - **持久化存储层**：包含 SQLite 会话管理器及向量检索。
*   `nanogenesis/genesis/core/compression.py` - **记忆坍缩引擎 (History CompressionEngine)**：负责将太长的历史对话降维浓缩。
*   `nanogenesis/genesis/core/entropy.py` - **系统熵值监控**：防止系统陷入无限死循环的断路器。每次新对话开始时自动 `reset()`，避免跨会话误触发 stagnant。
*   `nanogenesis/genesis/core/error_compressor.py` - **错误信号压缩器 (ErrorCompressor)**：将工具执行产生的原始错误 log（可达百行）压缩为结构化 JSON`{error_type, core_message, suggestion, raw_tail}`，供 LLM 高效诊断。
*   `nanogenesis/genesis/core/mission.py` - **3D 任务树 (3D Mission Tree)**：维护带 `parent_id` 的层级任务树，触发 `[CAPABILITY_FORGE]` 时允许派生 Z 轴分支用于造工具。
*   `nanogenesis/genesis/core/capability.py` - **世界模型扫描仪 (CapabilityScanner)**：巡查物理环境约束（Git/Root/OS）。
*   `nanogenesis/genesis/core/jobs.py` - **异步壳层管理器 (JobManager)**：跨并发跟踪后台跑着的 `nohup` 或服务。
*   `nanogenesis/genesis/core/scheduler.py` - **总线定时器 (AgencyScheduler)**：处理 Cron 计划任务与轮询机制。
*   `nanogenesis/genesis/core/trust_anchor.py` - **决策透明化信用锚点 (TrustAnchorManager)**：高敏感度动作确认。
*   `nanogenesis/genesis/core/diagnostic.py` - **系统深层诊断探针**：主动排障体系。
*   `nanogenesis/genesis/core/base.py` - 全局数据结构定义（如 `Message`, `PerformanceMetrics`, Tool基类）。
*   `nanogenesis/genesis/core/conversation.py` - Role 和 Message Schema 骨架。
*   `nanogenesis/genesis/core/config.py` - **中央配电盘**：环境变量与核心设定的绝对载体。
*   `nanogenesis/genesis/core/representation.py` - UI 表单或终端渲染。

### 🌐 外部接口 (External Adapters)
*   `nanogenesis/qq_adapter.py` - **QQ Bot 接入层**：通过 `botpy` SDK 接入 QQ 开放平台，支持频道 @消息 / 私信 / 群消息三种类型路由至 Genesis 处理。单例 Agent 模式，`on_ready` 时异步预热（180s 超时），由于它有自己的事件循环，通常作为长驻守护进程（Daemon）运行。

---

## 🚫 2. 核心开发契约 (Development Constraints)

如果你（未来的 AI 助理）需要为 Genesis 添加新的功能，**必须** 遵守以下法则：

1.  **禁止在主循环中做判断**：如果你要增加对某个新 AI 模型（如 Claude 3.5）的支持，**绝不** 允许修改 `provider_manager.py` 中的 `if model == "..."`。你必须在 `provider.py` 中新建一个实现了标准 `Provider` 接口的类，并通过 `@registry.register` 注入它。
2.  **Schema 纯洁法**：任何需要向 LLM API 发送的数据，必须被抽象为标准 `Message` 对象数组。涉及 Tool Calls 时，必须遵循 `[User] -> [Assistant (with tool_calls)] -> [Tool (or User observation)]` 的铁律。**禁止在 `agent.py` 的任何分支中绕过清洗逻辑直发 Payload。**
3.  **配置物理隔离**：所有的常数（Max Iterations, Timeouts, Default Models）必须被抽取到配置文件（如 `.env`）或交由 `core/config.py` 收口。代码中严禁出现裸露的硬编码数值和 API Keys。
4.  **原子隔离测试**：任何对底层的修改（特别是涉及 `core/` 下的逻辑结构变动），在完成代码编写后，必须主动执行对应的单元或回归压测脚本（例如 `scripts/stress_test_full.py`），通过后方可声明任务完成。

---


> 修改时间戳: 2026-02-23
> 验证签名: Genesis Registry Protocol V1.0

