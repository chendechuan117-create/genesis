# Genesis 🌱 (NanoGenesis)

**一个进化中的自主 AI Agent 框架与生态共生体**

Genesis 不是一个静态的对话机器人，而是一套**具有求生直觉、能在真实物理环境（Linux 本地环境）下自我扩张、思考和行动的智能操作系统**。它基于严格的“双轨制执行机制”、“熵值驱动熔断”以及“Z 轴动态补全本能”，能真正像人类黑客一样操作你的电脑、写代码、查文档、改 Bug，甚至在遇到自身能力瓶颈时，主动前往开源社区（如 OpenClaw / EvoMap 生态）寻找灵感并安全同化别人写好的脚本。

---

## ✨ 核心哲学与能力 (Core Philosophy & Capabilities)

### 1. 双轨情境执行架构 (Dual-Track Packager-Executor Paradigm)
传统的 Agent 在一次循环中既要理解环境又要执行代码，容易造成“智商污染”和幻觉。Genesis 将系统物理切割为两个生命体：
- **实体 B (上下文打包器 - Context Packager)**：负责与你对话、感知意图，利用只读探针（`ls`, `cat`）侦察环境。它不写任何执行代码，只负责打包出一份绝对纯净的《行动指南 (Mission Payload)》。
- **实体 A (无状态执行者 - Stateless Executor)**：纯粹的行动端。它被剥离了闲聊能力，接收到 Payload 后，唯一的任务就是专注调用工具、修改文件、执行命令。这彻底消灭了大型 LLM 常见的“文本敷衍”与“找不到文件”的顽疾。

### 2. Z 轴求生本能 (The Z-Axis Capability Forge)
传统 AI 在缺少某个工具时会直接报错放弃，或开始胡编乱造。
Genesis 被注入了**求生协议 (`pure_metacognition_protocol.txt`)**：当它意识到现有的原子工具不足以解决用户问题时，它会暂停主线任务，触发**「能力锻造 (Capability Forge) Z轴跃迁」**：
*   调用原生 `skill_creator` 自己根据报错信息从零写出一个全新 Python 工具并动态挂载。
*   或调用 **EvoMap 嗅觉探针 (`evomap_skill_search`)**，直接前往 GitHub 搜索开源同类框架（如 OpenClaw）的现成组件，使用隔离的 `skill_importer` 洗稿、进行安全逻辑提纯后同化为自有能力。

### 3. 三人格认知循环 (Cognitive Trinity Loop)
- **洞察者 (Oracle)**：负责解析隐式意图，连接持久化记忆（SQLite + FTS5）。
- **裁决者 (Strategist)**：元认知核心，使用独创的 `<reflection>` 本地推演沙盒思考战术蓝图，防止被用户诱导犯错。
- **执行者 (Loop Engine)**：底层行动引擎。

### 4. 熵值驱动断路器 (Entropy-Driven Circuit Breaker)
彻底摒弃“按错误次数熔断”的弱智设定。Genesis 内部集成 Ouroboros 熵值引擎：
只要执行报错信息（State Delta）在发生变化，就代表探针在有效地探索边界，系统将容忍多次连续报错；只有当系统捕获到“一模一样的冗余报错重复输出”（熵增停滞）时，才会瞬间判定并熔断死循环。这大幅解放了探索自由度。

### 5. 异步耗材子沙盒 (Lottery Sub-Agent Sandboxes)
当面临高资源消耗或极高不确定性的脏活累活时，主脑不亲自下场，而是通过 `spawn_sub_agent_tool.py` 派生一个子代 Agent 去后台运行。
子代码可以配置去使用廉价的 API (如硅基流动、阿里云百炼等免费大军)，成功后带回能力，失败了也能带回《操作复盘》，保护主脑资源。

---

## 🚀 快速开始 (Quick Start)

### 环境要求
- **OS**: Linux 环境（推荐 Ubuntu / Arch），极度不推荐 Windows。
- **Python**: 3.10+

### 安装与配置
```bash
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis/nanogenesis
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

复制并编辑 `.env` 文件，只填你需要的：
```bash
# === 主脑算力 (必须，选其一) ===
DEEPSEEK_API_KEY="sk-..."

# === 外接感官 (可选) ===
TAVILY_API_KEY="tvly-..."  # 提供实时联网搜索支持

# === 耗材池网络 (可选，用于廉价子代理集群) ===
# 建议注册白嫖各大厂的初始额度填入
SILICONFLOW_API_KEY="sk-..."
DASHSCOPE_API_KEY="sk-..."
QIANFAN_API_KEY="..."
ZHIPU_API_KEY="..."
```

### 唤醒沉睡者
```bash
# 启动标准终端交互环境
python3 genesis/main.py

# 启动无人值守 QQ Bot 实体形态
python3 qq_adapter.py
```

---

## 🏗️ 架构拓扑映射 (Architecture Topology)

系统严格遵守**“核心引擎驱动 + 动态插件扩展”**的架构真理。

```text
nanogenesis/
├── genesis/
│   ├── agent.py              # 总入口：负责主生命周期，拦截 Z 轴分支
│   ├── core/
│   │   ├── packager.py       # 实体 B：只读信息打包机
│   │   ├── loop.py           # 实体 A：无状态猛烈执行器
│   │   ├── cognition.py      # 元认知皮层
│   │   ├── registry.py       # 系统唯一依赖挂载总线 (工具/模型/生态)
│   │   ├── factory.py        # 基于注册表的动态装配厂
│   │   ├── entropy.py        # 【熵】断路器防死循环
│   │   ├── error_compressor.py # 冗余错误信号降维器
│   │   └── provider.py       # LLM API 物理交互层与 Reflection 滤网
│   ├── intelligence/
│   │   ├── adaptive_learner.py # 潜意识组装与操作复盘折叠器
│   │   └── protocol_decoder.py # 系统状态机协议解码
│   ├── memory/
│   │   └── sqlite_store.py   # 持久化海马体 (FTS5向量库)
│   ├── tools/                # 原生原子级探针 (如 shell, evomap_search, browser)
│   └── skills/               # 高维的动态生成工具 (Minted Keys)
├── scripts/                  # 包含架构看门狗 (enforce_architecture.py)
├── qq_adapter.py             # QQ 开放域接口套件
└── .env                      # 唯一敏感凭证存储介质
```

详细架构底漆，参阅 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。

---

## ⚔️ 安全与开发契约 (Safety & Dev Rules)

由于 Genesis 具备极其危险的系统物理访问权，参与开发或二次改造时必须遵循：
1. **沙盒隔离**：强烈建议在 Docker、WSL2、或新建的非 Root Linux 账户下运行它。它可以非常轻易地执行 `rm -rf`。
2. **注册表优先**：禁止在核心调度层对逻辑进行 `if/else` 的硬编码插桩，新能力或新渠道必须利用 `@registry.register` 以插拔式挂载。
3. **架构看门狗**：任何增删文件操作完成后，建议先执行 `python3 scripts/enforce_architecture.py`。这是防止系统出现“代码库遗忘症”和结构老化的物理校验闸门。

---

## 📄 License
MIT
