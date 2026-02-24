# Genesis 🌱

**一个进化中的自主 AI Agent 框架**

Genesis 是一个运行在你本地机器上的 AI 执行代理。它不只是一个聊天机器人——它拥有工具调用能力、长期记忆、任务树管理和元认知进化机制，可以真正执行任务：操控桌面、运行代码、搜索网络、管理文件。

---

## ✨ 核心能力

### 🧠 三人格认知架构
| 人格 | 角色 | 职责 |
|------|------|------|
| **洞察者 (Oracle)** | `cognition.py → awareness_phase` | 意图识别、记忆召回、任务分类 |
| **裁决者 (Strategist)** | `cognition.py → strategy_phase` | 元认知战略规划，生成执行蓝图 |
| **执行者 (Executor)** | `loop.py` | 工具调用、LLM 交互、结果反馈 |

### 🔄 自愈任务树 (Mission Context Tree)
- 任务以有向树结构存储于 SQLite
- 执行失败时通过 `[STRATEGIC_INTERRUPT]` 触发回溯
- 自动爬回父节点重试，注入失败路径避免重蹈覆辙
- 根节点失败才终止并输出 AUTO-DEBRIEF

### 📚 进化式记忆系统
- **短期上下文**：当前会话对话历史
- **长期记忆**：SQLite 持久化，FTS5 全文检索
- **经验提炼**：`AdaptiveLearner` 在交互中不断提炼认知原理，注入未来的 system prompt

### 🔍 元认知深度反思
每次任务回溯触发**双维度锚点反思**（异步非阻塞）：
1. **[锚点认知]** 从成功/失败对比提炼域无关的思维原理
2. **[工具审计]** 计算每个工具的失败率，标记需要改进的工具

### 🛠️ 工具生态
- `shell_tool` — 执行系统命令
- `browser_tool` — 浏览器自动化（xdotool）
- `web_tool` — 网络搜索（Tavily API）
- `visual_tool` — 截屏与视觉分析
- `system_health_tool` — 系统自检
- `spawn_sub_agent_tool` — 派生子代理（后台异步执行）
- `skill_creator` — 动态创建新工具技能
- 支持通过 `registry.py` 无限扩展

---

## 🚀 快速开始

### 环境要求
- Python 3.10+
- Linux（推荐 Arch / Ubuntu）

### 安装
```bash
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis/nanogenesis
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置
复制并编辑 `.env` 文件：
```bash
# 主模型（必填，选其一）
DEEPSEEK_API_KEY="sk-..."

# 网络搜索（可选）
TAVILY_API_KEY="tvly-..."

# 耗材池（可选，用于子代理任务，节省主模型 Token）
SILICONFLOW_API_KEY="sk-..."
DASHSCOPE_API_KEY="sk-..."
```

### 运行
```bash
# 命令行交互模式
python3 genesis/main.py

# QQ Bot 模式
python3 qq_adapter.py
```

---

## 🏗️ 架构概览

```
nanogenesis/
├── genesis/
│   ├── agent.py              # 认知主控制器（总入口）
│   ├── core/
│   │   ├── loop.py           # 衔尾蛇执行引擎
│   │   ├── cognition.py      # 三人格认知处理器
│   │   ├── mission.py        # 任务上下文树 + 决策日志
│   │   ├── provider.py       # LLM 驱动层
│   │   ├── registry.py       # 插件注册表（万物注册于此）
│   │   ├── factory.py        # 动态装配车间
│   │   ├── entropy.py        # 熵值监控/死循环断路器
│   │   └── error_compressor.py  # 错误信号压缩器
│   ├── intelligence/
│   │   └── adaptive_learner.py  # 元认知进化引擎
│   ├── memory/
│   │   └── sqlite_store.py   # 长期记忆（SQLite + FTS5）
│   ├── tools/                # 原子级工具
│   └── skills/               # 复合技能
├── qq_adapter.py             # QQ Bot 接入层
└── .env                      # 配置文件
```

---

## 🧬 进化机制

Genesis 不是静态的。它在运行中持续学习：

```
任务执行
  ├── 成功 → 决策标记 success
  └── 失败/回溯 → 决策标记 backtracked
              └── 触发锚点深度反思
                    ├── [锚点认知] 提炼思维原理
                    └── [工具审计] 标记高失败率工具

认知原理 → 注入下次请求的 system prompt
```

随着使用，Genesis 会逐渐知道：哪类起点通常失败、哪个工具需要改写，并自动调整策略。

---

## ⚙️ 开发约定

见 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。核心原则：
- **禁止硬编码**：新能力通过 `registry.py` 插件化挂载
- **Schema 纯洁**：所有 LLM payload 必须经过清洗器
- **配置隔离**：常量/密钥只存 `.env` 或 `config.py`
- **修改核心后必须跑压测**：`scripts/stress_test_full.py`

---

## 📄 License

MIT
