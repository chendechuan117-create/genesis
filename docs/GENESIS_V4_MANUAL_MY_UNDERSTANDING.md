# Genesis V4 核心理解与自用说明书 (Glassbox Architecture)

这份说明书是我基于对源码（不依赖现有说明文档）的逐行审阅后，提炼出的心智模型。它将作为后续任何调整和修复的**绝对真理基准**。

## 1. 核心定位：白盒认知装配师 (The Glassbox)

Genesis V4 不是一个传统的“接到指令就去用工具”的黑盒 Agent。它强行将思考和执行解耦，并在每次行动前强制“查表设点”，每次收尾后强制“复盘存盘”。

整个系统是一个基于 Discord 的服务，核心驱动引擎是 `V4Loop`。

## 2. 核心架构：三相管线 (The Three-Phase Pipeline)

`V4Loop` (在 `genesis/v4/loop.py`) 是整个系统的心脏。它强制将每一次用户请求拆解为严格隔离的三个（内部其实是四个）阶段：

### Phase 1: 装配期 (Assembly by 厂长 G)
- **输入**: 用户请求 + 极简的“近期短期对话记忆”。
- **权限**: 此时大模型被**剥夺**了所有普通工具的使用权，**仅能**使用 `search_knowledge_nodes` 工具。
- **目标**: 主动在 SQLite 知识库 (`NodeVault`) 中检索相关节点标题。
- **输出强制约束**: 必须输出一张严格格式的 JSON 蓝图 (Blueprint)，包含 `op_intent` (意图), `active_nodes` (启用的节点 ID), 和 `execution_plan` (执行计划步骤)。
- **降维打击**: 如果找到了对应的 `LESSON` 节点，G 必须毫无保留地把节点里的步骤照搬进 `execution_plan`，**严禁自行发明或猜测**（Cache 取代 Compute）。

### Phase 2: 执行期 (Execution by 执行器 Op)
- **触发**: 系统拦截并解析 JSON 蓝图。
- **上下文注入**: 从 `NodeVault` 中拉取 G 选定的 `active_nodes` 的**完整正文内容**，直接塞进上下文。
- **权限释放**: 将所有的底层工具（文件交互、命令执行、乃至爬虫和自编写的技能库）全部开放给模型。
- **行为**: 模型根据刚才的蓝图和节点提供内容的“外脑”，开始疯狂调用底层工具去干活，直至任务完成，向用户回复最终自然语言。

### Phase 3/4: 反思与沉淀 (Reflection by 沉淀器 C)
- **触发**: 在给用户发完最终回复之后，由于是在同一次 `process` 中跑的，系统会利用所有刚才的执行足迹（包含报错和成功日志）启动一个**独立的 C 进程**。
- **权限**: 这是一个特殊授权的 LLM 会话，它**只有**四个能力：`search_knowledge_nodes`, `record_context_node`, `record_lesson_node`, `delete_node`。
- **目标**: 提取“破局点 (Aha Moment)”。如果发现刚才的操作是因为某个特殊路径、某种特定报错对应的命令才修好的，它必须将其转化为原子化的双态节点（CONTEXT 或 LESSON）。
- **要求**: 写入内容必须是机器码或可以直接执行的命令行，严禁写废话。这也是为什么很多时候它自己就能变聪明。

## 3. 灵魂数据结构：双层 NodeVault

知识库 (`genesis/v4/manager.py`) 使用了精妙的双层 SQLite 设计，为了解决 Context Window 爆炸的问题：
1. **索引层 (`knowledge_nodes`)**: 仅包含 `node_id`, `type`, `title`, `tags`。这是发给“厂长 G”搜索用的极轻量级目录。
2. **内容层 (`node_contents`)**: 包含巨长的 `full_content`。仅在 G 选定后，才提供给“执行器 Op”。

### 节点类型 (Type)
- **CONTEXT节点**: 静态变量，比如某个服务的 API URL、某台机器的特定怪异配置路径。
- **LESSON节点**: 执行流，结构非常严谨（`IF_trigger` -> `THEN_action` (数组/脚本) -> `BECAUSE_reason`）。
- **短期对话记忆**: `MEM_CONV_xxx` 前缀，作为滑动窗口（默认留底10条）维持基础的用户连贯对话，避免长期节点的逻辑污染。

## 4. 强大的底层鲁棒性：Provider (\`genesis/core/provider.py\`)

源码显示，开发者极度不信任 LLM 所谓的“Native Tool Calling”：
- **原生 HTTP (`NativeHTTPProvider`)**: 根本不用外部 SDK（如 OpenAI SDK），直接手搓 curl 调用 DeepSeek。这规避了 Python 代理的一系列古怪问题。
- **极致的兜底反格式化 (Heuristic Parsing)**: 即使大模型幻觉了，没有输出合法的 function call，而是输出了带有 `{"action": "..."}` 的纯文本 JSON、甚至输出了带有 Python AST 定义的工具调用（比如 `tool_name(arg="val")` 代码块），Provider 的 `_try_parse_tools_from_content` 方法居然都能把它逆向解析回合法的 `ToolCall` 执行！

## 5. 自我进化：SkillCreatorTool

在 `genesis/tools/skill_creator_tool.py` 中，系统具备了“自我繁衍引擎”。
当它发现预置工具或者 bash 命令行做不到某些事时，它可以编写一段纯 Python 代码，严格继承 `Tool` 类，输出到 `skills/` 目录下热加载。这种动态热拔插的能力配合 C 进程的 Lesson 沉淀，构成了系统的闭环。

---

## 💡 后续开发/协同军规 (给我的提示词原则)

1. **绝对不要破坏三相管线**:
   如果用户报了工具执行的错，检查是不是 G 阶段拿到了错的蓝图，还是 Op 阶段传错了参，抑或是底层工具崩溃。任何试图让 G 越界去直接执行代码的操作都是非法的。
2. **信任本地知识库**:
   如果是逻辑重复的问题，不用去改代码框架，而是要引导系统去搜、去修改本地的 `LESSON` 节点（或者我自己通过工具帮它删改对应的 node）。
3. **Provider 永远是最脆弱也是最强大的屏障**:
   如果换了模型（比如换成了不支持 function call 很好的杂牌模型），只要调整 `_try_parse_tools_from_content` 的正则抓取即可，不需要伤筋动骨。
4. **工具开发的死律**:
   若要为其加开发新工具，绝对不能有阻塞主线程的死循环（如 `while True:` 且无 `asyncio` 回避），否则大模型线程会当场暴毙。任何持续侦听器必须被抛到后台。

## 6. 架构演进与运维释疑 (运维 F.A.Q)

针对本次引入的“因果图谱架构升维”，以下是关于系统运维和数据兼容性的解答：

### Q1: Genesis 修改完代码后需要重启吗？Discord 那边是怎么处理的？
**需要重启**。
Genesis 的骨架是 `discord_bot.py`，它是一个长驻内存的 Python 异步进程（通常由 `start.sh` 或 systemd 守护）。我们刚才修改的 `manager.py`, `loop.py`, `node_tools.py` 都是核心构件，Python 模块在内存中不会自动热重载这些修改。
- **操作建议**：在宿主机终端执行 `kill -9 $(pgrep -f "discord_bot.py")` 然后重新执行 `sh start.sh`，或者如果您有 systemd 服务，执行 `systemctl restart genesis`。

### Q2: 没做调整前的数据会被 C 进程转化为调整后的格式吗？
**不会自动批量转化，而是通过“读取即重构”的渐进式转化**。
- **底层数据库安全**：我们在 `manager.py` 的建表逻辑中加入了 `ALTER TABLE` 自动增加 `prerequisites` 和 `resolves` 列的逻辑，因此**老数据绝对安全，不会崩溃**。老节点这两个新字段默认是空值 (`NULL`)。
- **C 进程的转化逻辑**：C 进程在后台反思时，它的 Prompt 第 2 点写明了 `[查重与旧时代重构]`，它有权调用 `delete_node` 删除大段非原子化的旧节点，然后用进化后的 `record_lesson_node` 附带上图谱依赖重新写入。它是一边工作一边顺手“打扫卫生”的。

### Q3: 需要下载外挂的 Embedding 模型（向量数据库）吗？
**目前阶段：完全不需要**。
为了贯彻 Genesis “人机共生”与“极致轻量”的哲学，本次升维**没有引入**任何基于 Python 的重型向量数据库（如 Chroma、FAISS），也没有强迫下载任何 Embedding 模型。
- 我们采用了**图谱解包 (Graph Unwrapping)** 与 **字段扩充匹配 (BM25 字面语义平替)** 的方案。
- `search_knowledge_nodes` 目前是通过精确的图谱依赖连线（`prerequisites` 逗号分隔数组）来查找连带节点的，它的准度远远高于在本地跑一个 1.5B 参数的 Embedding 模型去做余弦近似检索。我们用“关系明确的高密度知识”取代了“大力出奇迹的算力盲搜”。
