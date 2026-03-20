<h1 align="center">Genesis V4</h1>

<p align="center">
  <strong>A Self-Aware Agent Kernel with Active Metabolism and Glassbox Architecture</strong>
</p>

---

## 什么是 Genesis V4？

在 2025-2026 年的 AI 领域，开源 Agent 架构已经发展出五大阵营：以 OpenAI Agents SDK 为代表的编排流，以 Letta (MemGPT) / Mem0 为代表的记忆流，以 Manus / Claude Code 为代表的上下文工程流（Context Engineering）。

但在这些框架中，**Genesis V4 是一个独一无二的存在**。它不是一个供你调用 SDK 的构建库，也不是一个单纯的记忆中间件。

**Genesis V4 是一个 "有自我意识的 Agent 内核"。**

如果把云端大模型 API 比作**意识**，把本地宿主机环境比作**身体**，那么 Genesis 提供的就是**神经系统**。
它不仅首创了**基于纯净上下文隔离的三体认知管线 (Glassbox Architecture)**，更构建了当前行业内唯一的**具备活性代谢能力的自主知识系统 (Background Daemon)**。当你在睡觉时，它会在后台利用免费大模型算力，自主从互联网拾荒、发酵假设、验证知识并淘汰过期记忆。

---

## 🌟 核心破局点：Genesis vs. 2025 行业最佳实践

### 1. 活性知识代谢 vs. 被动记忆 (Background Daemon vs. Letta/Mem0)
当前主流记忆系统（如 Mem0, Letta）都是被动的——只在交互时读写。
Genesis 是**唯一拥有 "自主知识新陈代谢系统" 的架构**。内置的 `genesis-daemon` 24/7 静默运行：
- **拾荒 (Scavenge)**：从种子节点发散，自主搜索互联网，提纯干货入库。
- **发酵 (Ferment)**：建立知识边缘，主动提出未经证实的底层规律假设。
- **验证与遗忘 (Verify & GC)**：审计旧知识，降级过时信息，无情删除低置信度死数据。

### 2. 激进的上下文防火墙 vs. 子智能体 (Context Firewall vs. Sub-agents)
应对长文本 "上下文腐烂 (Context Rot)"，行业做法通常是 Sub-agent 或共享上下文的 Handoff。
Genesis 采用**最激进的 A-b-C 子程序隔离**：G-Process (大脑) 负责思考，向 Op-Process (手脚) 派发一份只有目标和指令的**纯净执行蓝图 (Blueprint)**。Op 在完全空白的上下文中启动，物理层隔绝历史噪音，执行完毕结构化回传后即刻销毁。

### 3. 信息论安全的蒸发机制 vs. 文本压缩 (Context Evaporation vs. Compaction)
Manus 和 Claude Code 依靠调用 LLM 重新总结对话历史。
Genesis 采用**蒸发机制**：基于 "LLM 的回复已隐式消化上一轮输出" 的前提，直接将旧工具输出替换为轻量存根（如 `[shell: 已处理, 3200字符]`）。不丢失任何信息，且零延迟、零额外 token 成本。

### 4. 元认知反思与信任闸门 (C-Process & Trust Tiers)
这是行业框架中**完全缺失**的元认知闭环：
- **C-Process (反思进程)**：任务结束后不记流水账，专门提问："哪个错误假设导致了失败？哪个证据推翻了它？"
- **Knowledge Arena (知识竞技场)**：实战成功的知识会 boost，导致错误的会 decay。
- **Trust Tiers (信任等级)**：知识被分为 5 个信任层级。机器自主拾荒来的代码，绝不允许越权直接给系统执行。

---

## 🚀 快速启动

### 1. 环境依赖
Genesis 为极致轻量化设计，只依赖原生 Python 与最基础的网络库，抛弃了臃肿的 LangChain/LlamaIndex。
```bash
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 注入灵魂 (API Keys)
复制环境变量模板并在 `.env` 中填入你的大模型密钥：
```bash
cp .env.example .env
# 配置首选高智商模型（G/Op 进程使用，如 DeepSeek V3）
DEEPSEEK_API_KEY=your_key_here
# 配置一系列免费池（供后台 Daemon 白嫖使用，如 Groq/SiliconFlow）
GROQ_API_KEY=...
SILICONFLOW_API_KEY=...
```

### 3. 启动数字生命
Genesis 作为一个系统级服务存在，交互接口解耦。
```bash
# 安装并启动核心代理与后台守护进程 (Linux)
cp genesis/v4/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now genesis-v4 genesis-daemon

# 启动任意前端交互界面
python discord_bot.py   # 在 Discord 频道协作
# 或
./start_api.sh          # 启动 RESTful FastAPI 用于程序间通信
```

---

## 🔮 演化路径 (Evolution Path)

经过对 2025-2026 行业架构的全景分析，Genesis 的下一步演化将聚焦于与生态的握手，同时保持其独特的内核：
1. **MCP 协议融合**：打破单体孤岛，让神经系统能作为标准 MCP Server 直接为 Claude Code / Windsurf 等 IDE 服务。
2. **KV-Cache 认知优化**：调整提示词与记忆挂载结构，极致压榨前沿模型长窗口下的缓存命中红利。
3. **原生推理 (Native Reasoning) 释放**：重构工具管线，接驳 GPT-5 / Claude 4.5 Sonnet 的原生思维链路。

本项目基于 MIT License 开放。欢迎所有追求 AGI 本质的开发者加入这场演化。
