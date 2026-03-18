# Genesis V4 🧠

Genesis 是一种**高自主性、强工程化、具备记忆、自修改能力与原生视觉**的本地 AI Agent 架构。

相比于市面上繁杂的多智能体框架，Genesis V4 采用了独特的**“玻璃盒（Glassbox）”三体认知架构**，结合**后台拾荒者（Scavenger）**和**动态多模型路由**，专为解决“上下文污染”、“超长上下文调试”、“本地环境控制”以及“经验持续沉淀”等复杂工程问题而生。

---

## 🌟 核心特性 (Key Features)

### 1. 三体认知管线 (Tri-Process Architecture)
彻底解决传统单体 Agent 做长任务时容易“忘记初衷”和“陷入死循环”的痛点：
- **`G-Process` (大脑/Thinker)**：负责深思熟虑、结合上下文图像（原生视觉）、搜索本地知识库、编写严格的 JSON 执行派发书（Payload），绝对不直接触碰底层代码。
- **`Op-Process` (手脚/Executor)**：纯粹的无状态执行器。拿到派发书后，只管调用各种 Tool 执行终端命令、文件读写、MCP 检索等任务，执行完毕即销毁。彻底杜绝了模型执行过程中产生的幻觉。
- **`C-Process` (潜意识/Reflector)**：后台异步运行的经验沉淀节点，专门将 Op 刚才踩过的坑和成功的路径，固化为结构化知识，永久保存在 SQLite 知识图谱中。

### 2. NodeVault 本地知识金库 & Knowledge Arena
- **非传统 RAG**：Genesis 内部维护了一个带置信度衰减（GC）的**SQLite + 向量图谱引擎**。包含 9 大节点类型（LESSON, CONTEXT, ASSET 等）和丰富的关联边。
- **Knowledge Arena (知识竞技场)**：借鉴 Hyperspace AGI 思想，知识节点不是和平共存的。同一问题的多个排错经验（LESSON）会在实际使用中通过成功/失败的反馈闭环进行竞争，胜出的知识获得高置信度（Boost），失败的知识被淘汰衰减（Decay）。
- **层级推理式检索 (Reasoning-Based Retrieval)**：取代粗暴的全量向量搜索，G-Process 会先阅读知识库目录（Digest），像翻书一样沿着树状层级和图谱关联（REQUIRES, RESOLVES）进行推理导航。
- **Metadata 签名过滤**：支持环境状态的严格签名匹配（基于 OS, Language, Framework 等），精准挂载历史解决方案。

### 3. 后台发酵与验证进程 (Daemons)
Genesis 不是一个只会“被动响应”的工具。它自带了基于 `Systemd` 的多个独立驻留守护进程，利用免费大模型 API 池在后台默默为你打工：
- **Scavenger (拾荒者)**：在盲盒模式下生成技术好奇心 Query，自动在互联网上爬取、提炼前沿技术文章，并作为待验证资产 (`unverified`) 喂给主知识库。
- **Fermentor (发酵池/假设引擎)**：扫描孤立的知识节点建立图谱关联，并基于已有的 LESSON 发现知识空白，提出新的可测试假设 (Hypotheses)。
- **Verifier (审计员)**：定期回顾久未使用的知识，用大模型构建测试场景，验证那些随框架版本升级而过时的陈旧代码和方案。

### 4. 动态多模型路由 (Dynamic Provider Router)
- **原生兼容**：支持 DeepSeek, Gemini (兼容 OpenAI 规范), OpenAI, OpenRouter 等。
- **原生多模态视觉**：底层已打通图像处理链路，给 G-Process 直接喂图（通过 Discord 拖拽或传入路径），模型可以直接“看到”报错截图和架构图。
- **限流降级（Failover）**：自动捕获 `429 Too Many Requests`，并在高并发任务（如复杂的 Op 循环）中无缝热切换到备用模型（如从 Gemini 切到 DeepSeek），保证执行流不中断。

### 5. 跨系统整合与可观测性
- **Tool 体系**：内置本地 Shell、文件读写、URL 抓取、系统进程管理等工具。
- **Skill Creator (工具自进化)**：当现有工具不足时，Genesis 能自己编写 Python 代码、自己注册为新的 Tool 供自己使用。
- **MCP (Model Context Protocol) 整合**：支持接入 GitNexus 等底层知识库索引协议，打通全仓库代码级别的认知。
- **Tracer 全链路追踪**：内置轻量级 SQLite 和 Langfuse 链路追踪，清晰回放每一次 LLM 调用的 Prompt、Token 消耗、耗时和挂载的知识节点。

---

## ⚙️ 架构图解

```mermaid
graph TD
    User((User)) -->|Input + Images| G_Process
    
    subgraph "Genesis V4 Core"
        G_Process[G-Process (Brain)\nSearches Knowledge, Multimodal Plan]
        Op_Process[Op-Process (Hands)\nExecutes Payload via Tools]
        C_Process[C-Process (Subconscious)\nReflects & Stores Lessons]
        
        NodeVault[(NodeVault\nSQLite + Vector Graph + GC)]
        
        G_Process -->|Query Context| NodeVault
        G_Process -->|Dispatch Payload| Op_Process
        Op_Process -->|Execution Results| G_Process
        Op_Process -.->|Triggers| C_Process
        C_Process -->|Save/Promote Node| NodeVault
    end
    
    subgraph "Autonomous Daemon"
        Scavenger[Scavenger\nFree API Pool] -->|Web Forage| NodeVault
    end
    
    Op_Process -->|Sys Calls| OS_Tools((Local File/Shell/MCP Tools))
```

---

## 🚀 快速开始

### 1. 环境准备

Genesis 极其轻量，基于原生 Python 构建，不依赖任何重型框架（No LangChain, No LlamaIndex）。你需要 Python 3.10+ 环境。

```bash
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis
pip install -r requirements.txt
```

### 2. 配置密钥

创建 `.env` 文件并填入你的 API Key。支持多 Key 混用以应对不同管线。

```bash
# 首选主力大模型（如支持多模态的 Gemini 或极具性价比的 DeepSeek）
GEMINI_API_KEY=your-gemini-key
DEEPSEEK_API_KEY=your-deepseek-key

# Scavenger 拾荒者使用的免费算力池（填一个即可）
SILICONFLOW_API_KEY=your-siliconflow-key
DASHSCOPE_API_KEY=your-dashscope-key

# Discord 交互端 Token
DISCORD_BOT_TOKEN=your-discord-bot-token
```

### 3. 运行 Discord Bot (主交互端)

本项目自带了一个完备的 Discord 机器人接口，支持在频道里和 Genesis 进行沉浸式长周期协作，**支持直接发送图片给 Agent 识别**。

```bash
# 启动 Genesis 大脑！
python discord_bot.py
```

### 4. 启动后台服务群 (可选)
如果你在 Linux 环境下，可以通过 systemd 让 Genesis 持续在后台自主学习和验证：
```bash
cp genesis/v4/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
# 拾荒者 (自动爬取前沿技术)
systemctl --user enable --now scavenger
# 审计员 (自动验证库内陈旧知识)
systemctl --user enable --now verifier
# 发酵池 (自动寻找知识盲区并提出假设)
systemctl --user enable --now fermentor
```

### 5. 启动 API Server (可选)
让 Genesis 成为你的项目认知中台，提供 RESTful 接口供其他系统调用：
```bash
# 启动 FastAPI 服务 (默认端口 8046)
./start_api.sh
```
通过 `POST /v1/chat` 即可向 Genesis 派发任务。

---

## 🧠 设计哲学 (Philosophy)

1. **大模型的脑容量是有限的，必须“洗脑”**：
   单体 Agent 在解决复杂 Bug 时，历史记录会迅速堆积大量报错日志和无意义的尝试，导致模型产生幻觉。Genesis 的 `Op-Process` 永远是“失忆”的，它只拿到**当前所需的最小破局点**，从而保持最高智商的执行力。
2. **真正的记忆不是 RAG 文本，是动态图谱**：
   把所有聊天记录灌进向量数据库叫“检索增强”，把“遇到 Nginx 端口冲突 -> 应该执行 `lsof -i:80` -> 杀死进程”这种标准操作流沉淀为有向边，才叫**认知图谱**。
3. **不能自我供养的智能不是真智能**：
   引入 Scavenger 和知识衰减机制，让 AI 摆脱被动投喂，具备自发生长和遗忘的能力。

## 📄 许可证

本项目基于 [MIT License](./LICENSE) 开源。欢迎探索。
