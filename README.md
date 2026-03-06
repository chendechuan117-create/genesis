# Genesis V4 — 白盒认知装配师 (The Glassbox Amplifier) 🔮

> **AI 不是替代你思考的黑箱，而是放大你认知的白盒。**

Genesis 是一个**面向人类认知增强**的 AI Agent 框架。它的核心理念不是追求 AGI（通用人工智能），而是通过**暴露 AI 的全部思考过程**，让使用者在每一次交互中都能学到新东西。

---

## ⚖️ 系统兼容性 (System Compatibility)

| Platform | Support | Notes |
| :--- | :--- | :--- |
| **Linux** | ✅ **Native** | Recommended (Ubuntu, Arch, Debian). Best performance. |
| **macOS** | ✅ **Native** | Fully supported (Apple Silicon & Intel). |
| **Windows** | ⚠️ **WSL2 Only** | **NOT supported natively**. Requires [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) (Ubuntu). |

---

## 💡 核心哲学：用户共生 (Human-AI Co-Evolution)

大多数 AI Agent 追求的是"替你做完一切"。Genesis V4 追求的是**"让你看着它怎么做，然后你变得更强"**。

```
你提供方向 (新概念、新工具、纠错)
        ↓
   ┌─────────────┐
   │  厂长 G      │ ← 认知装配师
   │  选择节点    │
   │  组装管线    │
   │  暴露全过程  │
   └──────┬──────┘
          ↓
你看到了拆解过程 → 你的架构思维被训练
          ↓
   下一次你给出更精准的方向
          ↓
       认知飞轮 🔄
```

**越用越聪明的不是 AI —— 是你。**

---

## 🧩 万物皆节点 (Everything is a Node)

Genesis V4 的核心数据结构是**双面节点 (Dual-Faced Node)**：

| 面 | 给谁看 | 用途 | 示例 |
|---|---|---|---|
| **A 面** (Machine Payload) | 给 AI 看 | 极度压缩的 JSON，省 Token | `{"name":"web_search","params":["query"]}` |
| **B 面** (Human Translation) | 给你看 | 自然语言解释，教你这是什么 | `网络搜索引擎：突破知识库限制，实时拉取互联网信息` |

节点分为三类：
- 🔌 **TOOL** — 能力节点（搜索、执行命令、读写文件...）
- 🧠 **CONTEXT** — 情境节点（你的偏好、当前项目状态...）
- 📖 **LESSON** — 经验节点（错题集、踩坑记录...）

---

## 🔧 装配单实拍 (What You Actually See)

当你在 Discord 中 `@genesis 帮我查一下 OpenClaw 的生态`，你会看到：

```
🔧 [厂长已完成装配]
目标：探索通过当前令牌访问 OpenClaw 生态的可行性和方法

已加载认知节点：
  🔌 [SYS_TOOL_WEB_SEARCH] 网络搜索引擎：突破知识库限制，实时拉取互联网信息
  🔌 [SYS_TOOL_WORKSHOP] 记忆工坊引擎：直接用 SQL 读写长期记忆数据库

执行管线 (Op Sequence)：
  ⚡ 1. [SYS_TOOL_WEB_SEARCH] 搜索 'OpenClaw skill社区 evomap 生态 访问 令牌'
  ⚡ 2. [SYS_TOOL_WEB_SEARCH] 搜索 'Genesis Factory Manager V4 连接 OpenClaw API'
  ⚡ 3. [SYS_TOOL_WORKSHOP] 查询本地数据库
  ⚡ 4. [INTERNAL] 分析搜索结果，评估可行路径

🟢 [节点激活]: web_search 运行中...
✅ [web_search 节点反馈]: 结果数: 5 ...
🟢 [节点激活]: workshop 运行中...
✅ [workshop 节点反馈]: Workshop has 5 table(s) ...
```

---

## 📦 快速开始

### 1. 准备环境
确保你已安装 Python 3.10+ 和 Git。

### 2. 克隆与安装

```bash
# 1. 克隆仓库
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis/nanogenesis

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt
```

### 3. 配置 (.env)

在 `nanogenesis/` 目录下创建 `.env` 文件：

```ini
# 必须：LLM 提供商 (至少配一个)
DEEPSEEK_API_KEY="sk-..."

# 推荐：Discord 机器人
DISCORD_BOT_TOKEN="OT..."

# 可选：网络搜索能力
TAVILY_API_KEY="tvly-..."
```

### 4. 启动

```bash
# 启动 Discord 机器人 (推荐)
python3 discord_bot.py
```

---

## 🏛️ 项目结构

目录核心逻辑：系统主要开发和运行环境位于 `nanogenesis/` 目录下。

```
nanogenesis/
├── discord_bot.py          # 入口：Discord 交互层 + UI 回调
├── genesis/
│   ├── core/               # 底层基座 (Provider, Registry, Base)
│   ├── v4/                 # ★ V4 白盒架构
│   │   ├── agent.py        #   GenesisV4 入口
│   │   ├── loop.py         #   双阶段执行引擎 (蓝图→执行)
│   │   └── manager.py      #   厂长 G (NodeVault + FactoryManager)
│   ├── v3/                 # V3 自组织架构 (历史保留)
│   ├── v2/                 # V2 维度语言架构 (历史保留)
│   └── tools/              # 9 个基础工具
└── ~/.nanogenesis/
    └── workshop_v4.sqlite  # 节点数据库 (A/B 双面)
```

---

## 🧬 版本进化史

| 版本 | 核心理念 | 状态 |
|---|---|---|
| **V1** | Ouroboros 循环 — 尝试让 AI 自我修改代码 | 🪦 已废弃 |
| **V2** | 厂长-车间-执行器 — 维度语言精确调度 | 📦 存档 |
| **V3** | 极简 ReAct — 让 AI 自由组织记忆和身份 | 📦 存档 |
| **V4** | **白盒装配师 — 暴露思考过程，与人共生** | ✅ 当前版本 |

---

## 📄 License

MIT

---

> *"AI 之于人类，就像回音。基于用户的输入，进行更大波纹的反馈。"*
