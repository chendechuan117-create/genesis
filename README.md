<div align="center">
  <h1>Genesis V4 — 白盒认知装配师 (The Glassbox AI Agent)</h1>
  <p>AI 不是替代你思考的黑盒，而是放大你认知的白盒。</p>
</div>

Genesis V4 并非又一个全自动的“黑盒”黑客工具，而是一个拥有**自我维护意识**、具备**极高透明度**的“认知装配师”。

它被设计为协助开发者、探索互联网、执行脚本的智能实体。它奉行的唯一核心理念是：
> **“给下一次苏醒的‘我’，留下对‘我’有用的信息。”**

## 🌟 核心理念与实用特性

### 1. 真正的“白箱”架构 (Glassbox) — 伪流式传输
绝大多数 Agent 的体验是：你给一个任务 -> 漫长的后台工具调用 -> 给你最终结果。这种“黑盒”体验非常糟糕，你根本不知道它是在死机、幻觉，还是真的在干活。

Genesis V4 独创了 **[B面装配单]** 机制：
- 在它开始干活**之前**，它必须先生成一张 `JSON 蓝图`（它打算用哪些节点，它打算怎么分步执行）。
- 这张图纸会被**立刻渲染并发送给你**（伪流式传输）。
- 在执行过程中，每调用一个工具，它都会实时报告 `[⚙️ 执行中]` -> `[✅ 成功/失败]`。
- **你在全盘掌控它的思考和动作**，不再有漫长的盲目等待。

### 2. 知识的自我迭代与维护 (Phase 3: 反思)
市面上的 Agent 往往是“一次性”的，或是强塞一个充满噪音的向量数据库（RAG）。
Genesis V4 实现了真正的**三阶段执行流**（装配 → 执行 → 反思）：
- 任务执行完毕后，系统会强制它进入**反思阶段**。
- 它会审视刚才的执行结果和你的对话，**主动决定**是否调用内置工具去修改自己的“认知节点库”（增删改查）。
- 它甚至会去主动维护**你的用户侧写**（例如你的编程习惯、偏好）。你今天纠正它的一个错误，明天苏醒的它依然记得。

### 3. DeepSeek 与极致的缓存命中成本
利用这套分离设计的**双层节点库**（G 只看标题短目录，Op 按需拉取厚重的正文事实），发往大模型的系统提示词前缀极其稳定。
配合 **DeepSeek API** 等支持 Prefix Caching（上下文缓存）的模型，**它的短期记忆和长线架构不仅便宜，而且极速**。因为前置的设定和记忆几乎 100% 缓存命中，你只需要为它生成的新内容买单。

---

## 🚀 安装指南

⚠️ **注意：Genesis V4 不是打包好的客户端软件（.exe/.dmg），并且不需要寻找下载链接！它是一个你可以完全掌控源码的 Python 智能体项目。**

### 📍 V4 源码位置
当前仓库的 V4 独立纯净版本位于：👉 `Genesis/` 文件夹中。（由于历史原因，旧版源码在 `nanogenesis/` 中保留）。

### 方法一：极客推荐 🤖 — 指挥你的 AI 助手帮你配置
既然我们在使用 AI，为什么不用 AI 来安装 AI？
把下面这段话复制，发给你的 IDE（如 Cursor, Windsurf）或网页大模型：

> "请帮我配置 Genesis V4 环境。
> 1. 根据这个仓库下 `Genesis/requirements.txt` 的依赖，帮我创建一个干净的虚拟环境并安装好它们。
> 2. 帮我复制一份 `.env.example`（如果有的话）并告诉我需要填入哪些 API keys（比如 DISCORD_BOT_TOKEN 这是必须的，以及需要的 DeepSeek/其他大模型 Key）。
> 3. 用 Python 在 `Genesis/` 目录下运行 `discord_bot.py`，或者运行 `Genesis/start.sh`。"

### 方法二：手动极简安装

1. **克隆代码并进入 V4 目录**
   ```bash
   git clone https://github.com/chendechuan117-create/genesis.git
   cd genesis/Genesis  # 注意：必须进入 Genesis 文件夹，这里才是 V4 纯净版
   ```

2. **创建虚拟环境并安装极简依赖**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Windows 用户使用 venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   在 `Genesis/` 目录中新建一个 `.env` 文件，填入你的 Token：
   ```env
   DISCORD_BOT_TOKEN="your_discord_bot_token_here"
   # 这里建议填入深度受支持的模型，比如 DEEPSEEK_API_KEY
   ```

4. **启动！**
   ```bash
   chmod +x start.sh
   ./start.sh
   # 或者直接运行: python discord_bot.py
   ```

---

*Genesis V4.2 — 献给每一个渴望拥有真正私人助手的赛博工匠。*
