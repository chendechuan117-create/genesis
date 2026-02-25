# Genesis 2.0 系统结构与运作白皮书 (给人类看的版本)

为了让你（非程序员视角）能一眼看透目前 Genesis 的构成，我们用**“人体的器官”**来做类比，画了一张系统的拓扑结构图。

这是目前被我们清洗和固化下来的系统真理地图。

## 🗺️ 第一部分：系统视觉拓扑图

你可以把下面这段代码复制到在线的 Mermaid 渲染器（比如：https://mermaid.live/ ），就能看到一张直观的流程图。由于它被写在了系统的标准文档里，以后的 AI 也能直接“读懂”这张图的结构逻辑。

```mermaid
graph TD
    classDef brain fill:#f9d0c4,stroke:#333,stroke-width:2px;
    classDef sense fill:#d4e6f1,stroke:#333,stroke-width:2px;
    classDef body fill:#d5f5e3,stroke:#333,stroke-width:2px;
    classDef core fill:#fcf3cf,stroke:#333,stroke-width:2px;

    User([👤 你的指令]) --> Agent[🧠 代理总控 (Agent)]
    
    subgraph 神经与感知层 (感觉器官)
        Agent --> Context[📝 短期记忆缓冲]
        Context --> DB[(🗄️ SQLite 长期记忆)]
        Agent --> Entropy[🌡️ 焦虑监控 (防死循环)]
    end
    
    subgraph 认知与决策层 (大脑)
        Agent --> Loop[🔄 衔尾蛇主循环 (Loop)]
        Loop --> Provider[☁️ 大模型驱动 (Provider)]
        Provider --> DeepSeek[[DeepSeek API]]
        Provider --> LocalLLM[[本地备用模型]]
    end
    
    subgraph 插件化控制台 (脊髓)
        Loop --> Registry[📋 插件注册表 (Registry)]
        Registry -.管理.-> Provider
        Registry -.管理.-> Tools
    end
    
    subgraph 物理执行层 (躯干与手脚)
        Tools{🛠️ 工具箱} --> Shell[💻 运行电脑命令 (Shell Tool)]
        Tools --> Browser[🌐 控制浏览器 (Browser Tool)]
        Tools --> File[🗂️ 读写文件 (File Tools)]
    end
    
    Loop --> Tools
    Tools --执行结果--> Context
    
    class Agent,Loop brain;
    class Context,DB,Entropy sense;
    class Provider,DeepSeek,LocalLLM core;
    class Tools,Shell,Browser,File body;
```

---

## 🏷️ 第二部分：用人话解释核心组件是干嘛的

如果我们把 Genesis 当成一个拥有身体的**赛博数字人**，它的大脑、神经网络、手脚是如何分布在代码里的？

### 1. `agent.py` & `packager.py` —— 【实体 B：灵魂总控与前线侦察 (Context Packager)】
这是系统的最高入口，相当于人的**灵魂和本能**，也是懂你心思的大堂经理。
当你下达一个命令（比如“把我的桌面清理一下”），它（实体 B）负责接客。它会先去翻看历史记忆，看看你以前有没有教过它。如果发现需要动手干活，它绝对不会马上瞎操作，而是先用“只读”权限四处看看当前项目的情况，把需要的背景资料打包好，写成一份没有任何废话干扰的《行动指南 (Mission Payload)》，然后分配给底层的“执行大脑”去思考和处理。

### 2. `loop.py` —— 【实体 A：负责干活的无状态主管大脑 (Stateless Executor)】
这是系统最核心的**发动机舱**（被称为“衔尾蛇循环”，现在化身实体 A）。
你可以把它理解为一个被 B 召唤出来的**聋哑杀手 (Sub-Agent)**。**它被物理隔离，完全不知道你刚才和 B 闲聊了什么。** 它一出生，手里就捏着实体 B 塞给它的《行动指南》。
它负责一遍又一遍地做着枯燥的思考流程：
*   **看一眼任务指令单 -> 查一下大模型 -> 决定用什么工具 -> 执行工具 -> 检查结果有没有报错 -> 带着报错再去问大模型 -> 直到任务完成才停下并汇报给 `agent.py` (实体 B)。**
*   *(插曲：这道防线彻底过滤了大模型容易发散的残渣。由于 A 只能看到纯净的行动指南，它再也不会在干活中途突然“幻觉”或者跟你聊起天来。)*

### 3. `provider.py` 与 `provider_manager.py` —— 【大语言模型的嘴巴和耳朵】
这里负责和 DeepSeek 或其他大白痴 AI 打交道。
它是语言翻译官，负责把我们系统的复杂格式，翻译成 DeepSeek 能听懂的 API 请求发过去；然后再把 DeepSeek 写出来的、格式经常乱七八糟的乱码，规整地清洗后拿回给 `loop.py` 大脑用。

### 4. `registry.py` —— 【防误删的万能插座】
这是我们即将大力推行的**“拔插式插排”**。
以前，如果 Genesis 想学一个新工具，大模型会在 `loop.py` 的电线上乱剪乱接硬代码（比如写一大堆 `if 看到 shell 就执行 shell`）。这导致经常把主电线剪断。
现在有了注册表，**任何新的大模型、新的工具、新的能力，都像是一个 U 盘，只要插进 `registry.py` 这个插排里就能直接用**，绝对不允许去修改和破坏原本干净的 `loop.py`。

### 5. `tools/` 文件夹 —— 【真正接触物理世界的手脚】
大脑 (`loop.py`) 思考得再聪明，没有手脚也干不了活。
这里都是长相极其标准、独立的具体功能模块。比如 `shell_tool.py` 就是一双可以敲击你电脑键盘的手；`browser_tool.py` 就是一双可以帮你在网页上乱点的眼睛。它们即插即用，受大脑指派。

### 6. `context.py` 与 `entropy.py` —— 【短期记事本与防疯癫监控器】
*   **`context.py`** 就像大脑里的小便签本，记着最近对话的前 10 句话，防止大模型前言不搭后语。
*   **`entropy.py`** 就像一个测谎仪/心率计。大模型很容易陷入无限死循环（比如连续 50 次尝试同一个错误的密码）。这个模块会在系统陷入僵局时及时喊停，并强行阻断，防止浪费你的钱和计算资源。

---

> 只要这套大厦的骨架定格下来，未来所有的扩展和修改，**都被限制在只能写具体的子模块卡片（U 盘）上**，而不能再对这套骨架本身“动刀子”了。
