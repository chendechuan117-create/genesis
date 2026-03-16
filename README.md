# Genesis V4 🧠

Genesis 是一种**高自主性、强工程化、具备记忆与自修改能力**的本地 AI Agent 架构。相比于市面上繁杂的多智能体框架，Genesis V4 采用了独特的**“玻璃盒（Glassbox）”三体认知架构**，专为解决“上下文污染”、“超长上下文调试”以及“经验沉淀”等复杂工程问题而生。

## 🌟 核心特性 (Key Features)

- **Tri-Process 认知管线**：
  - `G-Process` (大脑)：负责深思熟虑、搜索本地知识库、编写执行派发书（Payload），绝对不直接碰代码。
  - `Op-Process` (手脚)：纯粹的无状态执行器。拿到派发书后，只管调用各种 Tool 执行任务，执行完毕即销毁，彻底杜绝了模型做着做着“忘了自己在干嘛”的幻觉。
  - `C-Process` (潜意识)：后台异步运行的经验沉淀节点，专门将 Op 刚踩过的坑固化为结构化知识。

- **NodeVault 本地知识金库**：
  - 并非简单的 Markdown 文本堆砌。Genesis 内部维护了一个带权重的**SQLite + 向量图谱引擎**。
  - 支持 `CONTEXT`（环境状态）和 `LESSON`（排错经验）等节点的严格签名匹配（基于 OS, Language, Framework 等）。当它再次遇到类似报错时，能像资深工程师一样精准挂载历史解决方案。

- **Skill Creator (工具自进化)**：
  - Genesis 内置了一个极度危险但也极度强大的能力：当它发现现有工具不足以完成任务时（比如缺一个处理某种特殊格式的脚本），它可以**自己编写 Python 代码、自己注册为新的 Tool 供自己使用**。

- **极简且纯净的内核**：
  - 零重度框架依赖（没有 LangChain，没有 LlamaIndex）。纯净的底层代码，毫秒级启动，完全白盒可见。

## ⚙️ 架构图解

```mermaid
graph TD
    User((User)) -->|Input| G_Process
    
    subgraph "Genesis V4 Core"
        G_Process[G-Process (Brain)\nSearches Knowledge, Plans Task]
        Op_Process[Op-Process (Hands)\nExecutes Payload via Tools]
        C_Process[C-Process (Subconscious)\nReflects & Stores Lessons]
        
        NodeVault[(NodeVault\nSQLite + Vector Graph)]
        
        G_Process -->|Query| NodeVault
        G_Process -->|Dispatch Payload| Op_Process
        Op_Process -->|Execution Results| G_Process
        Op_Process -.->|Triggers| C_Process
        C_Process -->|Save Node/Edge| NodeVault
    end
    
    Op_Process -->|Sys Calls| OS_Tools((Local File/Shell Tools))
```

## 🚀 快速开始

### 1. 环境准备

Genesis 极其轻量，你需要 Python 3.10+ 环境。

```bash
git clone https://github.com/chendechuan117-create/genesis.git
cd genesis
pip install -r requirements.txt
```

### 2. 配置密钥

创建 `.env` 文件并填入你喜欢的模型 API Key。Genesis 原生支持深改、OpenAI 等任意兼容提供商。

```bash
# 复制或创建 .env 文件
DEEPSEEK_API_KEY=sk-your-key-here
# 也可以配置免费代理提供商池（如需要）
SILICONFLOW_API_KEY=sk-xxx
```

### 3. 运行 Discord Bot 

本项目自带了一个完备的 Discord 机器人接口，支持在频道里和 Genesis 进行沉浸式长周期协作。

```bash
# 在 .env 中追加你的 Discord Token
DISCORD_BOT_TOKEN=your-bot-token

# 启动！
python discord_bot.py
```

## 🧠 设计哲学 (Philosophy)

1. **大模型的脑容量是有限的，必须“洗脑”**：
   单体 Agent 在解决复杂 Bug 时，历史记录会迅速堆积大量报错日志和无意义的尝试，导致模型产生幻觉。Genesis 的 `Op-Process` 永远是“失忆”的，它只拿到**当前所需的最小破局点**，从而保持最高智商的执行力。
2. **真正的记忆不是 RAG 文本，是图谱**：
   把所有聊天记录灌进向量数据库叫“检索增强”，把“遇到 Nginx 端口冲突 -> 应该执行 `lsof -i:80` -> 杀死进程”这种标准操作流沉淀为有向边，才叫**认知图谱**。

## 📄 许可证

本项目基于 [MIT License](./LICENSE) 开源。欢迎任何有意思的 PR 和探索！
