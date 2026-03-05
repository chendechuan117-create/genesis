# Genesis V2.5 (NanoGenesis) 🌱

**基于维度语言架构（Dimensional Language Architecture）的本地化 AI 代理**

> ⚠️ **Status**: Active Development (V2.5)

Genesis 不是另一个基于 RAG 或巨大上下文的聊天机器人。它是一个**基于精确维度索引的行动框架**。它不依赖"模糊搜索"或"运气"来找到工具，而是发明了一套维度语言 `(scope, action, target)`，将自然语言意图翻译为精确的数据库查询指令，像图书管理员一样精准调取技能与记忆。

---

## 🚀 核心差异 (Why Genesis V2?)

市面上大多数 Agent（包括 OpenClaw）采用的是"大杂烩"策略：把所有工具描述、历史对话、相关文件一股脑塞进 Context，或者用向量检索（RAG）撞运气。

Genesis V2.5 彻底抛弃了这种做法，引入了**维度语言架构**：

### 1. 维度语言 vs 向量检索 (The Dimensional Advantage)
*   **OpenClaw/传统 RAG**: 用户说"帮我修下网"，RAG 可能会检索到"网球"或"网站开发"，因为它是基于文本相似度的模糊匹配。
*   **Genesis V2**: 厂长（Manager）将"帮我修下网"翻译为维度坐标 `{"scope": "network", "action": "fix", "target": "config"}`。系统**精确查询**数据库中挂载了这些标签的工具和事实。
    *   **优势**: 0 幻觉，极低的 Token 消耗，精确度接近 SQL 查询。

### 2. "外科医生"式上下文 (Sterile Context)
*   **OpenClaw**: 历史对话越长，智商越低。因为错误的尝试和无关的闲聊污染了短期记忆。
*   **Genesis V2**: 每次行动（Op）都是**全新**的。
    *   Manager 像外科医生一样，只将当前任务**绝对必要**的 3 个工具和 5 条事实摆在台面上（OpSpec）。
    *   执行器（Executor）在一个无尘的、无历史包袱的环境中执行。
    *   执行结束，有价值的信息被提取为**结构化事实（Facts）**存入数据库，废话直接丢弃。

### 3. 元认知闭环 (Meta-Cognition Loop)
*   **OpenClaw**: 错了就重试，依赖 LLM 的随机性。
*   **Genesis V2**: 错了会进行**根因分析**。
    *   它不只是重试，而是会生成一条**模式（Pattern）**存入 `metacognition_workshop`。
    *   例如："上次我以为 `pacman` 能在 Debian 上用，结果报错了。模式：检查 OS 发行版再选包管理器。"
    *   下次行动前，Manager 会先阅读这些"错题集"，避免重蹈覆辙。

### 4. 自进化词典 (Self-Optimizing Dictionary)
*   如果用户提出了一个新的概念（比如 "调试 SambaNova"），而现有维度字典里没有这个分类。
*   Genesis 不会卡死，而是会**发明**新的维度标签，将其注册到系统中。随着使用，它的维度语言会越来越丰富，越来越懂你的行话。

---

## ⚖️ 局限性 (Limitations vs OpenClaw)

虽然 Genesis V2 在精准度和工程化上更强，但在某些方面不如 OpenClaw 这种"直觉型" Agent：

1.  **创意发散能力较弱**:
    *   OpenClaw 适合"陪聊"或"头脑风暴"，因为它保留了大量上下文涟漪。
    *   Genesis V2 极其功利，它只想把事做完。如果你跟它聊人生，它可能会试图把你的"人生感悟"翻译成数据库维度，然后发现无法匹配任何工具而感到困惑。

2.  **冷启动摩擦**:
    *   OpenClaw 丢进去一堆乱七八糟的文档就能跑。
    *   Genesis V2 需要（自动或手动）将知识结构化。虽然它有自动归档机制，但在没有任何维度数据的初期，它可能不如暴力检索的 Agent 灵活。

3.  **调试复杂度**:
    *   OpenClaw 出错通常只是 Prompt 没写好。
    *   Genesis V2 出错可能是：意图翻译错维度了？维度匹配没查到？还是工具本身的 Bug？排查链路更长。

---

## 🏗️ 架构概览

```mermaid
graph TD
    User["用户: '帮我配置代理'"] --> Translator
    
    subgraph Manager ["厂长 (Manager)"]
        Translator["意图翻译器"] -->|{"scope":"network", ...}| Matcher["维度匹配器"]
        Matcher <-->|SQL| DB[(Workshops SQLite)]
        Matcher -->|匹配的Facts/Tools| Assembler["Op装配器"]
        Digest["馆藏摘要"] --> Assembler
    end
    
    Assembler -->|OpSpec (无尘任务书)| Executor["执行器 (Executor)"]
    Executor -->|执行结果| Learner["学习机"]
    
    Learner -->|新事实| DB
    Learner -->|新维度| Translator
```

---

## 🛠️ 快速开始

### 环境要求
*   Linux (Ubuntu/Arch/Debian)
*   Python 3.10+
*   Git

### 安装

```bash
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis/nanogenesis
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置 (.env)

```ini
# 必须配置
DEEPSEEK_API_KEY="sk-..."

# 推荐配置 (用于 Discord 机器人)
DISCORD_BOT_TOKEN="OT..."

# 可选配置
TAVILY_API_KEY="tvly-..."
```

### 启动

```bash
# 启动 Web 界面 (推荐)
streamlit run web_ui.py

# 启动 Discord 守护进程
python3 discord_bot.py
```

---

## 📄 License
MIT
<!-- Last Updated: 2026年 03月 05日 星期四 10:32:38 CST -->
