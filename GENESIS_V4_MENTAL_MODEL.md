# Genesis V4 心智模型 — 源码绝对真理基准

> 本文档基于对全部源码的逐行审阅提炼，不依赖任何现有说明文档。
> 一切后续调整和修复以本文档为准。

---

## 一、全局架构总览

Genesis V4 是一个 **单阶段 ReAct 循环 + 后台反思** 的 AI Agent 系统，通过 Discord Bot 作为人机接口。

```
用户消息 (Discord)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ discord_bot.py                                      │
│  - 接收 @提及消息                                    │
│  - 拉取频道近 10 条历史作为上下文                      │
│  - 保存附件到 runtime/uploads/                       │
│  - 调用 agent.process(full_input, callback)          │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ factory.py → create_agent()                         │
│  - 创建 ProviderRouter (LLM 提供商)                  │
│  - 创建 ToolRegistry，注册 11 个工具                  │
│  - 返回 GenesisV4(tools, provider)                   │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ GenesisV4.process()                                 │
│  每次调用创建一个全新的 V4Loop 实例（无状态）            │
│  → loop.run(user_input, step_callback)               │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ V4Loop.run() — 核心执行引擎                          │
│                                                     │
│  Phase 1: ASSEMBLY (装配)                            │
│    G 优先用 search_knowledge_nodes (可选)             │
│    输出 JSON 蓝图 (无需搜索也可直出)                   │
│         │                                           │
│         ▼                                           │
│  Phase 2: EXECUTION (执行)                           │
│    Op 获得全部 11 个工具                              │
│    System 注入已选节点的完整内容 (Context Injection)    │
│    按蓝图调用工具，收集结果 (带 Head-Tail 截断)         │
│    文本回复即终结                                     │
│         │                                           │
│         ▼                                           │
│  Phase 3: POST (对话记忆)                            │
│    store_conversation → MEM_CONV_* 节点              │
│         │                                           │
│         ▼                                           │
│  Phase 4: REFLECTION (C进程，独立反思)                │
│    基于 [执行摘要] 反思 (User Intent + Tool Results)   │
│    仅开放节点档案馆工具 (代码级强制白名单)               │
│    查重 → 沉淀 CONTEXT/LESSON 节点                   │

---

## 二、 G -> Op 派发协议 (Task Payload)

在早期的 V4 版本中，G 被要求输出严格的 JSON Blueprint。这种设计被证明在面对复杂意图或某些 LLM 时非常脆弱，容易触发 JSON 解析错误和死循环。

现在的 V4.2 采用了更健壮的**文本派发协议 (Dispatch Payload)**：

当 G 决定将任务移交给 Op 时，它会输出一个结构化的代码块：

```dispatch
OP_INTENT: <对 Op 目标的简短明确指令>
ACTIVE_NODES: <逗号分隔的节点 ID，如 CTX_XXX, LESSON_XXX>
INSTRUCTIONS:
<给 Op 的具体执行建议或上下文信息。写清楚你想让 Op 怎么做，因为 Op 看不到你之前的搜索过程。>
```

系统会正则表达式拦截这个块，提取内容：
1. **注入节点内容**：系统会去 `NodeVault` 提取 `ACTIVE_NODES` 对应的完整文本。
2. **构建 Op Context**：将 `OP_INTENT`、`INSTRUCTIONS` 和提取出的节点文本，组装成一个全新的 System Prompt 发给 Op。

---

## 三、精确数据流 (逐行级)

### 3.1 启动链

1. **`start.sh`**: 激活 venv (`/home/chendechusn/Genesis/nanogenesis/venv`)，运行 `discord_bot.py`
2. **`discord_bot.py`**: `load_dotenv()` → `create_agent()` → `discord.Client` 启动
3. **`factory.py → create_agent()`**:
   - `ProviderRouter(config)` — 根据 API key 可用性选择 provider
   - `ToolRegistry()` — 注册工具实例
   - `GenesisV4(tools, provider)` — 返回 agent 单例

### 3.2 消息处理链

1. Discord `on_message` 触发
2. 去除 @提及文本，保存附件
3. 拉取频道最近 10 条消息拼接为 `[频道近期聊天环境]`
4. 拼接: `{channel_ctx}\n\n[当前请求]\n{user_intent}`
5. 调用 `agent.process(full_input, DiscordCallback)`

### 3.3 V4Loop 内部状态机

**初始状态**: G 进程启动。

**执行流程**：

```
[Phase 1: G-Process]
  ├── 系统注入：历史记忆 + 检索工具权限
  ├── 循环调用 LLM
  │    ├── 如果调用 `search_knowledge_nodes`，执行并继续。
  │    └── 如果输出纯文本包含 ````dispatch` 代码块，则解析提取 Payload，跳出循环。
  └── 异常兜底：若超时未输出有效 Payload，则报告构建失败。

[UI Rendering]
  ├── 将 Payload 解析并渲染为可视化组件发送给用户 ("🧠 大脑已完成思考，正在派发任务...")

[Phase 2: Op-Process]
  ├── 系统重置上下文，注入：Payload 目标 + Payload 指导 + 节点详细正文 + 执行工具权限
  ├── 循环调用 LLM
  │    ├── 执行 shell/file/web 等工具，结果追加到上下文。
  │    └── 如果输出纯文本（无工具调用），则认为是任务最终总结，跳出循环。
  └── 异常兜底：耗尽 max_iterations，强制结束。

[Phase 3: C-Process (Post-Execution)]
  ├── 将 Op-Process 的执行轨迹压缩为摘要。
  ├── 唤醒 C 进程，注入摘要和写入权限工具 (`record_*`)。
  └── C 进程分析并调用工具保存知识，或回复 NO_ACTION。
```

**关键细节**：
- **Context Firewalling**: Op 看不到用户的闲聊，只能看到 G 的指令。
- **Output Truncation**: Shell 输出截断 (4000 chars), File 读取截断 (8000 chars)。防止 Context 爆炸。
- **Reflection Summary**: C 进程不再读取完整历史，而是读取精简的 `[执行过程摘要]`。

---

## 四、 万物皆节点 (NodeVault)

知识库 (`workshop_v4.sqlite`) 不再是长篇大论的文档，而是被拆解成了原子化的**认知节点 (Knowledge Nodes)**。

### 4.1 双层存储
*   **表一：`knowledge_nodes` (索引表)**
    *   存储 `node_id`, `type`, `title`, `human_translation`, `tags`, `embedding`。
    *   G 在搜索时，**只看这张表的内容**。这就好比你在图书馆只看书名和简介，极大地节省了 Token。
*   **表二：`node_contents` (内容表)**
    *   存储真正的 `full_content`。
    *   只有当 G 把某个 `node_id` 写进 Task Payload 后，系统才会在给 Op 构建上下文时，把这部分内容提取出来。

### 4.2 节点类型

| type | ID 前缀 | 含义 | 内容格式 |
|---|---|---|---|
| `CONTEXT` | `CTX_*` | 环境变量 / 状态参数 | 纯文本 key-value |
| `LESSON` | `LESSON_*` | 经验流程 / 排错手段 | JSON: `{IF_trigger, THEN_action, BECAUSE_reason}` |
| `CONTEXT` | `MEM_CONV_*` | 对话记忆 (特殊) | `用户: ...\nGenesis: ...` |

### 4.3 对话记忆机制

- 每轮对话结束后 `store_conversation()` 创建 `MEM_CONV_{timestamp}` 节点
- **滑动窗口**: 保留最近 10 条，超出自动清理 (`_cleanup_old_memories`)

---

## 五、 工具沙箱 (Tool Sandbox)

目前共有 12 个核心工具，分属于不同的命名空间，供不同的进程使用：

1. **G 进程专属 (Search)**
   - `search_knowledge_nodes`: 大脑查阅知识库。
2. **Op 进程专属 (Execution)**
   - `shell`: 执行系统命令。
   - `read_file` / `write_file` / `append_file`: 文件读写。
   - `list_directory`: 查看目录。
   - `web_search`: 使用 DuckDuckGo。
3. **C 进程专属 (Reflection)**
   - `record_context_node` / `record_lesson_node`: 沉淀新知识。
   - `delete_node`: 删除过期知识。
4. **废弃/隔离组件**
   - `workshop`: 属于 V3 遗留工具，操作 `workshop_v3.sqlite`。
   - `skill_creator`: 自动编写 Python 脚本扩充能力的模块。
6. **确定性执行原则**: 搜到 LESSON 则必须照搬 `THEN_action`，不准自行发明
7. **连带依赖原则**: prerequisites 必须一并放入 `active_nodes`

---

## 五、工具体系

### 5.1 注册表

11 个工具，在 `factory.py` 中显式注册 (V3 WorkshopTool 已移除):

| # | 工具名 | 类 | 来源文件 | 用途 |
|---|---|---|---|---|
| 1 | `read_file` | ReadFileTool | file_tools.py | 读取文本文件 |
| 2 | `write_file` | WriteFileTool | file_tools.py | 写入/覆盖文件 |
| 3 | `append_file` | AppendFileTool | file_tools.py | 追加内容到文件 |
| 4 | `list_directory` | ListDirectoryTool | file_tools.py | 列出目录内容 |
| 5 | `shell` | ShellTool | shell_tool.py | 执行 shell 命令 (同步/异步/后台) |
| 6 | `web_search` | WebSearchTool | web_tool.py | Tavily API 网络搜索 |
| 7 | `skill_creator` | SkillCreatorTool | skill_creator_tool.py | 动态创建新工具 |
| 8 | `search_knowledge_nodes` | SearchKnowledgeNodesTool | node_tools.py | 搜索知识节点 (向量+字面) |
| 9 | `record_context_node` | RecordContextNodeTool | node_tools.py | 写入 CONTEXT 节点 |
| 10 | `record_lesson_node` | RecordLessonNodeTool | node_tools.py | 写入 LESSON 节点 |
| 11 | `delete_node` | DeleteNodeTool | node_tools.py | 删除知识节点 |

### 5.2 工具暴露权限矩阵 (源码实际行为)

| 阶段 | 可用工具 | 控制机制 |
|---|---|---|
| **ASSEMBLY** | 仅 `search_knowledge_nodes` | `loop.py`: 动态过滤 |
| **EXECUTION** | 全部 11 个 | `loop.py`: 传入完整列表 |
| **REFLECTION (C进程)** | 仅 4 个节点工具 | `loop.py`: 代码级白名单 `_c_allowed` 过滤 |

### 5.3 关键工具行为细节

**ShellTool**:
- 默认 `use_sandbox=False` (宿主机直接执行)
- **UNIFIeDtLO P**install/build`/docker`  始终传入式)a  _s 后延长0s
- **常驻服务自动 spawn**``代码级 过滤
- 危险命令拦截: `rm -rf /`, `dd if=`, `mkfs`, fork bomb

**WorkshopTool** (V3 遗留):
- 独立数据库: `~/.nanogenesis/workshop_v3.sqlite`
- 允许 Genesis 执行任意 SQL (schema/query/execute)
- 护栏: 禁止 DROP TABLE 和无 WHERE 的 DELETE
- ⚠️ 与 V4 的 NodeVault (`workshop_v4.sqlite`) 是**两个完全独立的数据库**

**SkillCreatorTool**:
- 写入 `genesis/skills/{name}.py`，动态 `load_from_file` 加载
- `ToolRegistry.load_from_file` 有自动依赖安装逻辑 (pip install)
- 加载后验证 Schema 合法性，不合法则 rollback

---

## 六、LLM 提供商体系

### 6.1 Provider 继承树

```
LLMProvider (ABC)                    ← base.py
    ├── NativeHTTPProvider           ← provider.py (curl-based, 主力)
    │     └── SambaNovaProvider      ← provider.py
    ├── LiteLLMProvider              ← provider.py (可选, 需装 litellm)
    └── MockLLMProvider              ← provider.py (测试用)
```

### 6.2 Provider 注册 & 路由

**注册** (cloud_providers.py + registry.py):
- deepseek, openai, openrouter, antigravity (本地代理)
- 消耗品池: siliconflow, dashscope, qianfan, zhipu, sambanova

**路由优先级** (ProviderRouter):
- Failover 顺序: `deepseek → openrouter → openai → antigravity`
- 消耗品顺序: `sambanova → siliconflow → dashscope → zhipu → qianfan`

> ⚠️ **注册冲突**: `registry.py` 中硬编码注册了 `zhipu` 和 `sambanova`，`cloud_providers.py` 又重复注册了它们（会触发 "已存在，将被覆盖" 警告，但功能正常）。

### 6.3 NativeHTTPProvider 关键行为

- 使用系统 **curl** 发送请求（非 Python HTTP 库），绕过代理兼容性问题
- 流式: `asyncio.create_subprocess_exec` 运行 curl，逐行解析 SSE
- **反幻觉 Stop Sequences**: `["User:", "Observation:", "用户:", "Model:", "Assistant:"]`
- **启发式工具调用解析** (`_try_parse_tools_from_content`): 当 LLM 不通过 function calling 而是在文本中输出工具调用时，尝试从代码块、JSON、Python AST、正则中提取 (4 层 fallback)
- **Internal Reflection 剥离**: 自动删除 `<reflection>...</reflection>` 标签
- 每次请求的 payload 写入 `debug_payload.json` (5MB 轮转)

### 6.4 配置加载链 (ConfigManager)

优先级: **系统环境变量 > .env 文件 > OpenClaw 宿主配置 > 默认值**

支持自动从 `~/.local/share/openclaw/openclaw.json` 继承 API key、代理、Telegram token。

---

## 七、反思机制 (Phase 4 / C进程) 详解

### 7.1 触发条件

- `final_response` 非空时触发 (即主执行有结果)

### 7.2 上下文

- 完整继承主循环的 `built_messages` (包含 system prompt、用户输入、蓝图、工具调用结果、最终回复)
- 追加一段独立的反思 system prompt

### 7.3 反思 prompt 核心规则

1. **高价值增量原则**: 提取三类信息：(1) Aha Moment 破局点 (2) 新实体概念定义 (3) 用户画像与偏好。禁止流水账。
2. **双态节点架构**: 
   - `CONTEXT`: 环境变量、实体定义、用户画像 (`CTX_USER_`)
   - `LESSON`: 经验流程、故障解决路径
3. **机器码原则**: LESSON 的 `action_steps` 必须是可粘贴运行的 Bash 命令
4. **查重优先**: 先 `search_knowledge_nodes` 查重，再决定创建/覆盖/删除
5. **旧节点重构**: 有权删除非原子化旧节点并拆分为多个合规节点
6. **NO_ACTION 退出**: 无需沉淀时直接输出 "NO_ACTION"

### 7.4 执行约束

- 最多 3 轮迭代
- 不产生流式输出 (`stream=False`)

---

## 八、关键设计决策 & 源码事实

### 8.1 每次调用创建新 V4Loop

`GenesisV4.process()` 每次创建一个新的 `V4Loop` 实例 (agent.py:36)。`V4Loop.__init__` 创建 `FactoryManager()` → `NodeVault()` → `VectorEngine()`。三者均为单例，不会重复初始化。

> ✅ **已修复**: NodeVault 和 VectorEngine 均为单例模式，全局只有一个 DB 持久连接 (WAL 模式) 和一份向量矩阵。

### 8.2 SQLite 持久连接 + WAL

NodeVault 单例持有一个长连接 (`self._conn`)，启用 WAL (Write-Ahead Logging) 模式。所有 node_tools 工具和 manager 内部方法均复用此连接，消除了每次操作新建/销毁连接的开销。

### 8.3 搜索管线

搜索现在是三层管线：
1. **召回**: SQL LIKE 字面匹配 + Bi-Encoder (bge-small-zh) 向量匹配 → OR 合并候选集
2. **精排**: Cross-Encoder Reranker (bge-reranker-base) 按语义相关度重新排序
3. **展示**: 按 rerank_score 降序返回给 G，附带相关度分数

如果 Reranker 未加载，自动降级为原来的 usage_count 排序。

### 8.4 tool_calls 归一化

`_normalize_tool_calls` 将不同 provider 返回的异构 tool_call 格式统一为:
```json
{"id": "call_{iter}_{idx}", "type": "function", "function": {"name": "...", "arguments": "..."}}
```
这对支持多 provider 至关重要。

### 8.5 Step Callback 机制

`step_callback` 是一个 sync/async 通用回调函数，支持事件:
- `loop_start`: 迭代开始
- `reasoning`: LLM 推理过程 chunk
- `blueprint`: 蓝图 UI 渲染文本
- `tool_start`: 工具开始执行
- `tool_result`: 工具执行结果

Discord Bot 通过 `DiscordCallback` 实现，将这些事件实时发送到频道。

---

## 九、已修复的源码级问题 (2026-03-12)

| # | 问题 | 修复方式 | 涉及文件 |
|---|---|---|---|
| 1 | C 进程权限泄漏 | 代码级白名单 `_c_allowed` 过滤，只暴露 4 个节点工具 | loop.py |
| 2 | NodeVault 多实例重复加载 | NodeVault 改为单例模式 (`__new__` + `_initialized` 守卫) | manager.py |
| 3 | V3 WorkshopTool 遗留 | 从 factory.py 移除注册，删除 workshop_tool.py 文件 | factory.py |
| 4 | 蓝图 JSON 解析脆弱 | 新增 `_extract_json_object` 栈匹配方法 | loop.py |
| 5 | Provider 重复注册 | 移除 registry.py 中硬编码，统一由 cloud_providers.py 注册 | registry.py |
| 6 | seed 节点清理硬编码 | 移除 `_ensure_seed_nodes` 方法及其调用 | manager.py |
| 7 | 确定性执行原则硬编码 | “一字不差照搬”改为“优先参考方案”，Op 保留判断权 | manager.py |
| 8 | 搜索结果 Discord 截断 | 专用 `search_result` 事件 + 格式化展示 | loop.py, discord_bot.py |
| 9 | base.py 死代码 | 移除未使用的 ContextBuilder/Intent/Diagnosis/Strategy | base.py |
| 10 | FetchURLTool 占位符 | 移除未实现的 TODO 占位类 | web_tool.py |
| 11 | LiteLLMProvider 死代码 | 移除类定义 + litellm 导入 + provider_manager 引用 | provider.py, provider_manager.py |
| 12 | debug_payload.json 调试残留 | 移除生产环境的 payload 写入逻辑 | provider.py |
| 13 | 搜索降级 dump TOP50 | 搜不到直接返回“未知区域”，不再鼓励低质量随机选择 | node_tools.py |
| 14 | resolves 非必填 | 加入 `record_lesson_node` 的 required 列表，强制语义锚点 | node_tools.py |
| 15 | C 进程无度量数据 | 注入执行度量摘要 (迭代次数/工具调用/节点命中/token消耗) | loop.py |
| 16 | 搜索排序依据 usage_count | 接入 Cross-Encoder Reranker (bge-reranker-base) 按语义相关度精排 | vector_engine.py, node_tools.py |
| 17 | SQLite 每次新建连接 | NodeVault 持久连接 + WAL 模式，消除 ~12次/请求的连接开销 | manager.py, node_tools.py |

---

## 十、文件清单与职责映射

```
Genesis/
├── factory.py                    # V4 工厂入口，组装 agent
├── discord_bot.py                # Discord 接口层
├── start.sh                      # 启动脚本
├── .env                          # API keys 等敏感配置
├── genesis/
│   ├── core/
│   │   ├── base.py               # 所有抽象基类 (Tool, LLMProvider, Message, etc.)
│   │   ├── config.py             # 配置管理 (单例, env/dotenv/openclaw 三源)
│   │   ├── registry.py           # ToolRegistry + ProviderRegistry (含动态加载)
│   │   ├── provider.py           # LLM 实现 (NativeHTTP/Mock/SambaNova)
│   │   ├── provider_manager.py   # ProviderRouter (failover 路由)
│   │   ├── sandbox.py            # Docker 沙箱 (当前未启用)
│   │   └── jobs.py               # 后台任务管理 (spawn/poll)
│   ├── v4/
│   │   ├── agent.py              # GenesisV4 入口 (极薄, 委托给 Loop)
│   │   ├── loop.py               # V4Loop 核心状态机 (装配→执行→反思)
│   │   ├── manager.py            # NodeVault + FactoryManager + NodeManagementTools
│   │   └── vector_engine.py      # 向量引擎 + Reranker (单例, bge-small-zh + bge-reranker-base)
│   ├── tools/
│   │   ├── file_tools.py         # 4 个文件操作工具
│   │   ├── shell_tool.py         # Shell 执行 (同步/异步/后台)
│   │   ├── web_tool.py           # Tavily 搜索
│   │   ├── visual_tool.py        # 截图 (ADB/桌面) — 未注册到 V4
│   │   ├── skill_creator_tool.py # 动态工具创建
│   │   └── node_tools.py         # 4 个知识节点管理工具
│   ├── providers/
│   │   └── cloud_providers.py    # 8 个云 provider 工厂注册
│   └── skills/                   # 动态生成的技能存放目录 (27 个已有)
```

> **注意**: `visual_tool.py` 定义了 `VisualTool`，但 `factory.py` 中未注册它。

---

## 十一、核心概念术语对照表

| 术语 | 源码实体 | 含义 |
|---|---|---|
| G (厂长) | LLM 在 ASSEMBLY 阶段的角色 | 看标题目录，选节点，组装蓝图 |
| Op (执行器) | LLM 在 EXECUTION 阶段的角色 | 拿到节点内容和工具集，按蓝图执行 |
| C (反思进程) | LLM 在 REFLECTION 阶段的角色 | 审查执行结果，沉淀知识节点 |
| 蓝图 | JSON `{op_intent, active_nodes, execution_plan}` | G 的输出，Op 的输入 |
| 节点 | knowledge_nodes + node_contents 行 | 知识库的原子单元 |
| 白盒/Glassbox | step_callback 机制 | 执行过程对用户可见 |
| NodeVault | V4 的知识管理 | 双层结构化节点库 |

---

*本文档生成时间: 2026-03-12, 基于 Genesis V4.2 (Glassbox) 全部源码审阅。最后更新: 2026-03-12 19:19*
