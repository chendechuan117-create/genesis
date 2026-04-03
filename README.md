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
DISCORD_BOT_TOKEN=your_token_here

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

## 🏗️ 阶级跃迁 — Class Leap Refactoring

Genesis V4 经历了一轮系统性架构重构（"阶级跃迁"），将多个 God Class 拆解为职责单一的模块：

### 跃迁路线图

| 阶段 | 改动 | 效果 |
|------|------|------|
| **第一跃** | `manager.py` 2770L → 拆出 `prompt_factory.py`、`signature_constants.py` | 降至 1683L，提示词/常量不再耦合主循环 |
| **第二跃** | 拆出 `pipeline_config.py`（frozen dataclass） | 魔数集中管理，运行时不可变 |
| **第三跃** | 拆出 `diagnostics.py`（DiagnosticSignal + 断路器） | 信号体系独立，支持自动降级 |
| **第四跃** | 碎片治理：`is_project_debris()` 门卫 + `use_scratch=true` 默认翻转 | 写入默认进 scratch，读取/列目录自动标注碎片 |

### 工程防线

```
写入端: WriteFile/AppendFile 默认 use_scratch=true → 临时产物自动进 runtime/scratch
读取端: ReadFile 输出 ⚠️ [debris:xxx] 标注 → LLM 不会把碎片当源码
目录端: ListDirectory 自动过滤 6 个碎片根 → 搜索不受干扰
Shell端: ShellTool cwd 在碎片区时输出警告 → 提醒操作者
```

### 测试覆盖

- **51 个单元测试**：覆盖 DiagnosticSignal、SignatureEngine、PipelineConfig、DispatchTool 合约
- **Auto 产出遥测**：每轮自动记录 G→Op→C pipeline trace（5000+ 事件/轮），作为端到端集成验证
- **断路器机制**：诊断信号超阈值自动触发降级，带冷却和自动恢复

## 项目结构

```
genesis/
├── core/               # 基础设施
│   ├── artifacts.py    #   产物管理 + 碎片门卫（is_project_debris）
│   ├── provider.py     #   LLM Provider 抽象
│   ├── registry.py     #   工具注册表
│   └── config.py       #   全局配置
├── v4/                 # V4 引擎
│   ├── loop.py         #   主循环（G → Op → C pipeline）
│   ├── manager.py      #   NodeVault 知识库管理
│   ├── blackboard.py   #   Multi-G 黑板竞争机制
│   ├── diagnostics.py  #   DiagnosticSignal + 断路器
│   ├── signature_engine.py  # 元信息签名推断/归一化
│   ├── signature_constants.py  # 签名维度常量/别名
│   ├── pipeline_config.py   # 不可变 pipeline 参数
│   ├── prompt_factory.py    # 提示词工厂
│   ├── lens_phase.py   #   Multi-G 透镜阶段
│   └── background_daemon.py # 后台守护进程
├── tools/              # 工具集
│   ├── node_tools.py   #   知识库 CRUD（9 个工具）
│   ├── file_tools.py   #   文件读写（带碎片标注）
│   ├── shell_tool.py   #   Shell 执行（带碎片警告）
│   └── dispatch_tool.py #  G → Op 任务分派
├── providers/          # LLM provider 注册
├── skills/             # 扩展技能
└── mcp_server.py       # MCP 服务端（Windsurf/Cascade 用）

tests/                  # 单元测试 + 回归测试
scripts/                # 运维脚本（doctor.sh、autopilot 等）
```

## 许可证

MIT License. Copyright (c) 2025-2026.

---

**Genesis 不是工具，是身体。云 API 来了又走，但身体会记住每一次经历。**