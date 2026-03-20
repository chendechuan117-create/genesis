<h1 align="center">Genesis V4</h1>

<p align="center">
  <strong>A Self-Creating, Self-Improving Agentic System with Glassbox Architecture</strong>
</p>

---

## 什么是 Genesis V4？

在绝大多数开源 AI Agent 仍停留在“提示词工程”与“暴力 RAG 检索”的阶段时，Genesis V4 是一次向 **AGI 个体智能** 迈进的工程实践。

它不仅是一个执行你指令的编码助手，更是一个**具有神经突触闭环、具备自我遗忘机制、能够自主发散并生成假设的数字生命体**。

它摒弃了冗长的单一执行流，首创了严格上下文隔离的 **三体认知管线 (Glassbox Architecture)**，并内置了一个基于免费大模型算力池 24/7 运行的 **统一后台守护进程 (Background Daemon)**。这让它能在处理极度复杂的长期项目时，永远保持清醒的判断力，并在你睡觉时自我学习。

---

## 🌟 核心破局点与架构设计

### 1. 严格上下文防火墙的三体认知 (A-b-C Architecture)
现代大模型的智商与上下文长度成反比。当一个 Agent 带着长达几万 token 的错误尝试记录去修复下一个 bug 时，幻觉是必然的。Genesis 彻底重构了控制流，实现了子程序化的调用模型：

*   **`G-Process` (The Thinker / 模块 A)**：系统的大脑与前端。它保持对用户意图的全局认知，查阅本地知识库目录，通过多模态视觉理解问题，然后向 `Op-Process` 发送一份**纯净、无历史噪音的执行蓝图 (Blueprint)**。
*   **`Op-Process` (The Executor / 模块 b)**：动态生成的纯执行切片。在**完全空白的上下文**中启动，严格按照蓝图调用 OS Tool、执行脚本、检索 MCP，一旦执行完毕即将结构化的报告返回给 G，随后**立即销毁，不留一丝残骸**。
*   **`C-Process` (The Reflector / 模块 C)**：全局协调器与元信息管理器。在任务结束后，负责从成功或失败的执行轨迹中提取高密度教训 (LESSON)、全局资产 (ASSET)，并沉淀为元数据签名。

### 2. 生态级的记忆引擎 (NodeVault & Knowledge Arena)
Genesis 不是外挂一个 ChromaDB 那么简单，它的记忆是一套带有生态选择压力的**关系型向量双引擎数据库 (SQLite + BAAI BGE-Small)**。

*   **知识竞技场 (Knowledge Arena & UCB)**：任何被写入的教训（如一段 Nginx 排错经验）都要接受实战检验。成功的调用增加成功率，导致幻觉的调用会被扣分。Genesis 使用 **UCB (上限置信区间)** 算法动态平衡经验利用与新知识探索，打破马太效应。
*   **层级推理式检索 (Reasoning-Based Retrieval)**：G-Process 并不直接做全文搜索，而是先阅读按类别聚合的轻量级 **Digest (认知摘要)**，像人类查阅目录一样，沿着 `REQUIRES` / `RESOLVES` 的图谱边界进行定向下钻。
*   **多维元数据签名 (Metadata Signature)**：不再有无定形文本段落。每个知识节点都携带极其严谨的元签名（例如 `{ "os_family": "linux", "runtime": "nodejs", "framework": "express" }`），确保在不同的运行环境中只挂载最对口的记忆。

### 3. 衔尾蛇般的自我进化 (The Background Daemon)
当宿主不在时，Genesis 不会进入休眠。它通过统一的 systemd 服务 `genesis-daemon` 在后台静默运行，完全利用免费的白嫖 API 算力（如 Cloudflare, SiliconFlow, Groq 的多级 Failover 链），执行四维循环：

1.  **拾荒 (Scavenge)**：从现有知识库中随机选取高置信度种子节点，触发“好奇心引擎”生成发散查询，接入互联网搜索，提纯极高密度的干货并入库。
2.  **发酵 (Ferment)**：扫描知识库中的孤儿节点，发现并建立逻辑边（Edge Discovery）；从零散的 LESSON 中抽象出更高阶的底层规律资产（Concept Distillation）。
3.  **猜测 (Speculate)**：基于已有经验，主动提出未经证实但极具价值的技术假设（Hypothesis Engine），留待未来验证。
4.  **遗忘 (GC & Verify)**：审计员定期重新审视旧知识，对过时的框架版本和死链进行置信度降级；垃圾回收器 (GC) 则无情地删除长期未被证明有用的低置信度数据。

### 4. 高保真基建 (Infrastructure)
*   **动态路由与自动容灾 (ProviderRouter)**：全异步的 httpx 流式传输引擎，具备 `Wall-Clock Timeout` 与自动探活。在遇到 `429` 或是 `DNS 阻断` 或是 `模型思考假死` 时，能无缝顺滑降级到备用链路。
*   **跨进程探针追踪 (Tracer)**：内置的 SQLite Tracing 系统详细记录每一轮请求的耗时、Token 开销、输入输出预览。
*   **Model Context Protocol (MCP)**：深度兼容 MCP 生态，可自由挂载 `genesis-nodevault`，与 Windsurf / Cursor 等现代编辑器无缝对话，让你的 IDE 也能访问 Genesis 的大脑。

---

## 🚀 快速启动

### 1. 环境依赖
Genesis 为极致轻量化设计，只依赖原生 Python 与最基础的网络库。不需要沉重的 LangChain / LlamaIndex。
```bash
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 注入灵魂 (API Keys)
复制环境变量模板并在 `.env` 中填入你的大模型密钥（支持兼容 OpenAI 接口标准的任何模型）：
```bash
cp .env.example .env
# 配置首选高智商模型（G/Op 进程使用）
DEEPSEEK_API_KEY=your_key_here
# 配置一系列免费池（供后台 Daemon 白嫖使用）
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

## 🔮 与同类架构的对比

*   **对比 OpenClaw**：OpenClaw 侧重于将单体 Agent 部署为可靠的网关、提供优雅的 WS 会话层和前端 UI 组件。而 Genesis 更加注重底层的**心智模型进化**和**图谱流式记忆**，它不仅是一个“好用的 Agent 运行时”，更是一个“会自动进化的记忆库”。
*   **对比 Ouroboros (衔尾蛇)**：Ouroboros 展现了令人惊叹的自主循环与“自写代码自改脑”的纯黑客哲学。Genesis V4 吸取了这种精神，但走向了更务实的工程路径：它不追求重构自身的底层 Python 代码，而是致力于**数据结构自举**和工具的自我发现，使其成为一个在生产环境中完全可信、可控、不会自我摧毁的强大协作者。

---

## 📄 协议与展望

我们正在向着 `Meta-Schema Evolution` 的方向迈进，未来的 Genesis 将不仅能自我撰写工具，还能根据对世界的观察，自主在运行时定义出前所未有的记忆数据结构。

本项目基于 MIT License 开放。欢迎所有追求 AGI 本质的开发者加入这场演化。
