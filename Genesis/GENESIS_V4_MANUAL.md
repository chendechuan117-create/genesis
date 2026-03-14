# Genesis V4 源码级技术白皮书 (The Glassbox Manual)

> **版本**: V4.2 (Glassbox)  
> **生成时间**: 2026-03-12  
> **基准**: 100% 基于源代码事实 (`genesis/core`, `genesis/v4`, `genesis/tools`)  
> **定位**: 开发者/维护者/高级用户完全指南

---

## 1. 核心架构设计

Genesis V4 采用 **单阶段 ReAct 循环 + 后台反思 (Single-Pass ReAct + Reflection)** 架构，强调执行过程的透明性（Glassbox）和知识的自动沉淀。

### 1.1 系统拓扑

```mermaid
graph TD
    User[Discord User] -->|Message + Attachments| DiscordBot
    DiscordBot -->|Context + Input| Agent[GenesisV4 Agent]
    
    subgraph "Core Runtime (V4Loop)"
        direction TB
        Phase1[Phase 1: Assembly<br>(Role: G)] -->|Search & Blueprint| Phase2
        Phase2[Phase 2: Execution<br>(Role: Op)] -->|Tools & Results| Phase2
        Phase2 -->|Final Text| Phase3
        Phase3[Phase 3: Memory<br>(Store Conversation)] --> Phase4
        Phase4[Phase 4: Reflection<br>(Role: C)] -->|Analysis & Sedimentation| NodeVault
    end

    Agent --> V4Loop
    
    subgraph "Infrastructure"
        NodeVault[(NodeVault<br>SQLite + WAL)]
        VectorEngine[VectorEngine<br>BGE + Reranker]
        ProviderRouter[LLM Provider Router]
    end

    V4Loop --> NodeVault
    V4Loop --> ProviderRouter
    NodeVault <--> VectorEngine
```

### 1.2 关键实体定义

| 实体 | 源码对应 | 职责 | 权限范围 |
|---|---|---|---|
| **G (Factory Manager)** | `genesis/v4/manager.py` | 装配师。负责查阅知识库，生成执行蓝图 (JSON)。 | 仅检索工具 (`search_knowledge_nodes`) |
| **Op (Operator)** | `genesis/v4/loop.py` | 执行器。负责根据蓝图调用具体工具解决问题。 | 全部业务工具 (Shell, File, Web, etc.) |
| **C (Reflector)** | `genesis/v4/loop.py` | 反思者。负责事后复盘，提炼经验并写入知识库。 | 仅节点管理工具 (`search`, `record`, `delete`) |
| **Vault (Database)** | `genesis/v4/manager.py` | 知识库。双层存储（索引+内容），单例持久连接。 | - |

---

## 2. 基础设施层 (Infrastructure)

### 2.1 配置中心 (`genesis/core/config.py`)
- **零配置启动 (Zero-Conf)**: 
  1. **OpenClaw 寄生**: 自动读取宿主配置 `~/.local/share/openclaw/openclaw.json` (API Key, Proxy, Telegram)。
  2. **Env Vars**: 系统环境变量优先级最高。
  3. **.env**: 自动递归向上查找 `.env` 文件。
- **代理自动注入**: 检测并注入 `HTTP_PROXY`/`HTTPS_PROXY` 到进程环境。

### 2.2 LLM 提供商体系 (`genesis/core/provider*.py`)
- **NativeHTTPProvider**: 
  - 核心实现不依赖 Python SDK，直接调用系统 `curl` 命令。
  - **优势**: 彻底解决 Python `requests`/`aiohttp` 在某些代理环境下的握手问题。
  - **能力**: 支持 SSE 流式解析、反幻觉 Stop Sequences、启发式工具调用解析。
- **ProviderRouter**:
  - **Failover**: `DeepSeek` (主力) -> `OpenRouter` -> `OpenAI` -> `Antigravity` (本地)。
  - **Consumables**: 独立的消耗品池 (`siliconflow`, `dashscope`, `zhipu` 等) 用于低成本任务。
- **启发式解析 (Heuristics)**:
  - 当模型未遵循 Function Calling 协议时，通过 `_try_parse_tools_from_content` 挽救：
    1. **JSON Action**: `{"action": "tool", "args": ...}`
    2. **Python AST**: 解析 Markdown 代码块中的 `tool(arg=val)`。
    3. **Regex**: 兜底匹配 `name="..." arguments="..."` 结构。

### 2.3 知识库引擎 (`genesis/v4/manager.py`)
- **NodeVault (单例)**:
  - **存储**: SQLite (`~/.nanogenesis/workshop_v4.sqlite`)。
  - **模式**: `WAL` (Write-Ahead Logging) 开启，支持并发读写。
  - **表结构**:
    - `knowledge_nodes` (索引层): `node_id`, `type`, `title`, `tags`, `embedding`, `prerequisites`, `resolves`.
    - `node_contents` (内容层): `node_id`, `full_content` (Op 专用).
- **VectorEngine (`genesis/v4/vector_engine.py`)**:
  - **模型**: `BAAI/bge-small-zh-v1.5` (Embedding) + `BAAI/bge-reranker-base` (精排)。
  - **机制**: 启动时全量加载 Embedding 到内存 `numpy` 矩阵。
  - **搜索管线**: 
    1. **召回**: 向量相似度 (Top-K) + SQL LIKE 字面匹配 -> 并集。
    2. **精排**: 使用 Cross-Encoder 对候选集打分重排。
    3. **展示**: 附带 `prerequisites` 自动展开依赖图谱。

---

## 3. 运行时详解 (V4Loop)

### 3.1 启动与上下文 (`discord_bot.py`)
- **附件处理**: 保存至 `runtime/uploads`，路径注入 Prompt。
- **环境注入**: 拉取频道最近 11 条消息，构建 `[频道近期聊天环境]`，解决多轮对话上下文断裂问题。
- **UI 协议 (Glassbox)**: `DiscordCallback` 实时透传内部状态：
  - `blueprint`: 渲染 G 的装配图纸。
  - `tool_start/result`: 显示工具调用状态。
  - `search_result`: 格式化展示知识库检索结果（区分语义/字面来源）。

### 3.2 阶段一：装配 (Assembly)
- **角色**: G (Factory Manager)
- **输入**: 用户请求 + 频道历史 + 附件。
- **行为**: 
  - 系统强制要求先调用 `search_knowledge_nodes`。
  - 必须输出 **JSON 蓝图**: `{op_intent, active_nodes, execution_plan}`。
  - **依赖原则**: 若选中 LESSON 节点，必须连带其 `prerequisites` 一并列入 `active_nodes`。

### 3.3 阶段二：执行 (Execution)
- **角色**: Op (Operator)
- **状态转换**: 收到蓝图 JSON 后，System 提示词自动切换模式，注入 `[已加载节点内容]`。
- **静默协议**: 严禁输出解释性文本，直接 Function Call。
- **防死锁**: 
  - 300秒超时限制。
  - 连续纯文本输出拦截机制 (User Prompt 警告)。

### 3.4 阶段三：记忆 (Memory)
- **机制**: 滑动窗口 (Sliding Window)。
- **存储**: 对话结束后存入 `MEM_CONV_{timestamp}` 节点。
- **清理**: 每次写入时自动清理超过 10 条的旧记忆 (`_cleanup_old_memories`)。
- **注入**: 下次启动时，G 只会看到最近 5 条对话。

### 3.5 阶段四：反思 (Reflection)
- **角色**: C (Reflector)
- **触发**: 主任务完成后 (final_response 非空)。
- **隔离**: 代码级白名单 (`_c_allowed`) 仅暴露 4 个工具：
  - `search_knowledge_nodes`
  - `record_context_node` (上下文/变量)
  - `record_lesson_node` (经验/流程)
  - `delete_node` (清理旧数据)
- **逻辑**: 
  - 接收完整执行上下文 + **性能度量** (Token/Steps/Tools)。
  - 提取 "Aha Moment" (破局点) 和新概念。
  - **机器码原则**: LESSON 的 `action_steps` 必须是可执行 Bash/代码，禁止自然语言。

---

## 4. 工具生态系统 (`genesis/tools`)

### 4.1 已注册工具 (Active)
| 工具名 | 源码 | 描述 |
|---|---|---|
| `shell` | `shell_tool.py` | 执行/Spawn/Poll 命令。支持 Docker 沙箱 (`nanogenesis-sandbox`)。危险命令拦截。 |
| `web_search` | `web_tool.py` | Tavily API 搜索。使用 `curl` + `socks5h` 强力穿透。 |
| `read/write/append_file` | `file_tools.py` | 文件读写。 |
| `list_directory` | `file_tools.py` | 目录浏览。 |
| `skill_creator` | `skill_creator_tool.py` | 动态编写 Python 工具并热加载。含 Schema 校验。 |
| `search_knowledge_nodes` | `node_tools.py` | 混合搜索 (Vector + LIKE)。 |
| `record_*_node` | `node_tools.py` | 写入 CONTEXT/LESSON 节点 (C进程专用)。 |
| `delete_node` | `node_tools.py` | 删除节点 (C进程专用)。 |

### 4.2 未注册/隐藏工具 (Hidden)
- **`visual` (`visual_tool.py`)**: 
  - **状态**: 代码存在，但在 `factory.py` 中未注册。
  - **能力**: 截图 (`adb` / `desktop`)，OCR (`tesseract`)。
  - **特殊**: 包含针对 Linux 桌面 (`scrot`/`mss`) 的 X11/Wayland 适配逻辑。

---

## 5. 部署与扩展

### 5.1 系统依赖 (System Requirements)
Genesis V4 极度依赖底层工具，而非 Python 库：
- **核心**: `curl` (网络层), `sqlite3` (数据库), `python3`
- **可选**: 
  - `docker`: 用于沙箱隔离执行。
  - `adb`: 用于 `visual` 工具的 Android 截图。
  - `scrot` / `xauth`: 用于 `visual` 工具的桌面截图。
  - `tesseract-ocr`: 用于图片 OCR。

### 5.2 Python 依赖
- 基础: `discord.py`, `python-dotenv`
- 向量引擎 (可选): `sentence-transformers`, `numpy` (若缺失则自动禁用向量能力)

### 5.3 扩展指南
1. **添加新工具**:
   - 在 `genesis/tools/` 下新建 `.py`。
   - 继承 `Tool` 基类，实现 `execute`。
   - 在 `factory.py` 中导入并 `tools.register()`。
2. **添加 LLM Provider**:
   - 在 `genesis/providers/cloud_providers.py` 添加 `_build_xxx` 工厂函数。
   - 调用 `provider_registry.register`。
   - `ProviderRouter` 会自动发现并纳入 Failover 链。

---

## 6. 数据流向速查

1. **User** `@Genesis 部署个 Nginx`
2. **DiscordBot** 包装上下文 -> `Agent.process()`
3. **V4Loop** (Iter 1): 
   - Phase: ASSEMBLY
   - G: Call `search_knowledge_nodes(["nginx", "deploy"])`
4. **Tool**: Search -> Rerank -> Returns Nodes `LESSON_NGINX_DEPLOY`
5. **V4Loop** (Iter 2):
   - G: Output JSON Blueprint `{"active_nodes": ["LESSON_NGINX_DEPLOY"], ...}`
6. **V4Loop** (Internal): 
   - Detect JSON -> Load Content of `LESSON_NGINX_DEPLOY` -> Inject to System Prompt
   - Switch Phase -> EXECUTION
7. **V4Loop** (Iter 3):
   - Op: Call `shell(command="apt install nginx")` (Following Lesson)
8. **V4Loop** (Iter ...): Op executes remaining steps...
9. **V4Loop**: Op Output Text "部署完成" -> `final_response`
10. **V4Loop** (Post):
    - Save Conversation to Vault.
    - Switch Phase -> REFLECTION (C Process)
11. **C Process**: 
    - Review execution.
    - Call `record_lesson_node` if new tricks found.
12. **DiscordBot**: Send "部署完成".

---
