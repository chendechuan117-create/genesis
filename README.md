# Genesis V4 — 自我进化的 AI Agent 内核

<p align="center">
  <strong>A Self-Evolving Agent Kernel with Active Knowledge Metabolism and Glassbox Architecture</strong>
</p>

<p align="center">
  <a href="#理念">理念</a> •
  <a href="#核心特性">特性</a> •
  <a href="#架构">架构</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#许可证">许可证</a>
</p>

---

## 理念

Genesis 不是又一个 AI Agent 框架。它是一个**具备活性知识代谢能力的 Agent 内核**。

大多数 Agent 系统是"无状态的"——每次对话从零开始，工具调用结果用完即弃。Genesis 的设计哲学不同：**云 API 是意识，本地机器是身体，元信息系统是神经**。系统在执行任务的同时，持续地学习、验证、遗忘，让知识库保持"此时此地的最佳状态"。

## 核心特性

### 🧠 三体认知管线 — Context Firewall

```
用户请求 → Multi-G 透镜（3~7 个 MBTI 人格并行分析）
         → G-Process（思考者：规划 + 知识检索 + 蓝图分派）
         → Op-Process（执行者：纯净上下文，原子任务，工具调用）
         → C-Process（反思者：提炼经验、记录教训、更新知识图谱）
```

- **G** 只看得到知识库和用户请求，负责"想"
- **Op** 只看得到 G 给的蓝图，负责"做"——**上下文防火墙**隔绝噪音
- **C** 只关注 Op 的物理执行结果，负责"学"——不记录脑内幻想

### � Multi-G 多维感知

每次请求自动激活 3~7 个基于 MBTI 16 型人格的"透镜"并行分析任务，共享 NodeVault 但各自用不同的认知框架解读信息。BlackBoard 竞争机制选出最佳视角，Persona Arena 在线学习淘汰弱者。

### 🧬 活性知识代谢

后台 Daemon 24/7 运转：

| 进程 | 功能 |
|------|------|
| **Scavenger（拾荒者）** | 自动从互联网搜集信息填补知识空洞 |
| **Fermentor（发酵池）** | 发现节点间语义关联，生成假设 |
| **Verifier（验证器）** | 审计知识新鲜度，衰减/提升置信度 |
| **GC** | 清理被遗忘的过时知识 |

知识不是静态存储——它在被创建、验证、关联、淘汰。

### 📊 元信息签名系统

每个知识节点携带 metadata_signature（OS、语言、框架、任务类型等维度），搜索时自动硬过滤+软评分。C-Process 写入时若发现新维度，自动学习并持久化。维度空间无限扩展，节点类型固定不变。

### 🏟️ 双竞技场在线学习

- **Knowledge Arena**：任务成功/失败后，被引用的知识节点 confidence 动态升降
- **Persona Arena**：参与任务的 Multi-G 人格被记录胜负，按 task_kind 细分，弱者被淘汰替换

### ⚡ 信息论安全蒸发

G 和 Lens 的历史工具输出被压缩为轻量存根（零 LLM 调用、零信息损失），最大化 DeepSeek prefix caching 命中率。Op 保留完整 ReAct 记忆，不蒸发。

## 架构

```
用户 → Discord Bot → V4Loop
  ├── Multi-G 透镜预激活（3~7 MBTI 人格并行，共享 prefix cache）
  ├── Phase 1: G-Process（search_knowledge_nodes + dispatch_to_op）
  ├── Phase 2: Op-Process（16 个工具，纯净上下文，≤12 轮）
  ├── Phase 3: POST（对话记忆 → MEM_CONV 滑动窗口）
  ├── Phase 4: C-Process（FULL/LIGHT/SKIP 三级，8 个节点工具）
  └── Post-C: 信息空洞自动入库（VOID 节点 → Scavenger 填补）

后台守护进程（BackgroundDaemon）：
  ├── Scavenger  — 优先填补 VOID 节点，web_search + read_url + 提纯入库
  ├── Fermentor  — 语义向量搜索发现边缘关联 + 假设生成
  ├── Verifier   — LLM 审计节点新鲜度 + confidence 衰减/提升
  └── GC         — 清理被遗忘的节点

外部服务：
  ├── SearXNG（自建元搜索，聚合 Google/Bing/DuckDuckGo）
  └── Playwright Chromium（headless 浏览器）

知识库：NodeVault（SQLite + 向量引擎 BGE-small-zh）
Provider：DeepSeek（主力）→ Gemini（failover）| FreePoolManager（Daemon 用免费池）
```

### 工具权限矩阵

| 阶段 | 可用工具 | 控制机制 |
|------|---------|----------|
| **Lens** | `search_knowledge_nodes` | schema 只传 1 个工具 |
| **G** | `search_knowledge_nodes` + `dispatch_to_op` | schema 只传 2 个 |
| **Op** | 16 个工具减去 8 个节点工具 | 代码级过滤 |
| **C** | 8 个节点工具 | 白名单 |

## 快速开始

### 环境要求

- Python 3.11+
- CUDA GPU（可选，加速向量引擎）
- DeepSeek API Key（必需）

### 安装

```bash
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
# 核心 LLM（必需）
DEEPSEEK_API_KEY=your_key_here

# 免费池（Daemon 后台用，可选）
GROQ_API_KEY=your_key_here

# Discord Bot（可选）
DISCORD_TOKEN=your_token_here

# 代理（墙内环境需要）
HTTPS_PROXY=socks5://127.0.0.1:20170
```

### 启动

```bash
# Discord 机器人（主接口）
python discord_bot.py

# 后台守护进程（知识代谢）
python -m genesis.v4.background_daemon

# 或用 systemd 管理
systemctl --user start genesis-v4.service
```

## 项目结构

```
genesis/
├── core/           # 基础设施：provider, registry, config
├── v4/             # V4 引擎：loop, manager, blackboard, daemon
├── tools/          # 工具集：node_tools, file_tools, web_tool, url_tool
├── providers/      # LLM provider 注册
└── mcp_server.py   # MCP 服务端
```

## 许可证

MIT License. Copyright (c) 2025-2026.

---

**Genesis 不是工具，是身体。云 API 来了又走，但身体会记住每一次经历。**