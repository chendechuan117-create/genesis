# Genesis V4 架构规格书

## 核心理念

**给下一个"我"留下对"我"有用的信息。**

Genesis = **厂长 G** + **执行管线 Op**

G 不是一次性的装配师。G 是一个会学习、会反思、会维护自己知识库的认知中枢。

---

## 信息分类

Genesis 只处理两类信息：

| 类型 | 谁用 | 存哪 | 举例 |
|---|---|---|---|
| **利好 G** | G 装配和反思时参考 | G 的记忆（prompt 注入） | "上一轮在搞 n8n API 认证" |
| **利好 Op** | Op 执行时参考 | 元信息节点（node_contents） | `CTX_n8n_API认证: 密钥认证方式...` |

**记忆 ≠ 元信息。** 记忆是 G 的短期上下文，元信息是 Op 的长期积木。

---

## 节点系统

**节点是标题，内容用链接联通。G 看标题，Op 看内容。**

```sql
-- 索引层（G 扫描用）
knowledge_nodes: node_id, type, title, tags, usage_count

-- 内容层（Op 按需拉取）
node_contents: node_id, full_content, source
```

节点类型：
- `TOOL` — 工具定义（系统内置，G 用来组装 Op）
- `CONTEXT` — 事实性知识（G 或反思阶段创建/更新）
- `LESSON` — 经验教训（反思阶段提炼）

---

## 四阶段执行流

```
Phase 1: 装配 (Assembly)
    G 扫描: 记忆 + 节点目录 + 用户请求
    G 输出: JSON 蓝图 { op_intent, active_nodes, execution_plan }
    渲染:   B面装配单 → 用户可见

Phase 2: 执行 (Execution)
    Op 按蓝图依次调用工具
    工具结果回流到消息历史

Phase 3: 回复 (Final Reply)
    G 看到所有的执行结果，不再有节点管理的思想包袱
    G 只负责：用极其自然、干脆的“人话”向用户汇报结论或交流
    渲染:   对话文本出流 → 用户可见

Phase 4: 独立反思 (Independent Reflection)
    在回复结束后，启动一次**独立的大模型思考（C）**
    输入：用户的原始请求 + 所有的工具执行结果 + 刚才 G 的回复
    任务：专职判定【是否需要保存新知】、【是否需要删改旧认知】、【是否更新用户侧写】
    如果有动作，调用节点管理工具（UI可见），这保证了反思的严谨，同时放过了 G 的自然交流。
```

### 反思阶段的关键规则

1. **G 是知识的主人** — G 拥有调用工具（`create_or_update_node`, `delete_node`）增删改元信息节点的完全权限。
2. **反思是基于提示词的** — 反思不是通过写死的代码逻辑 `if tools_used > 0` 来触发的，而是由系统提示词在执行流结束前自然引导。这意味着即使是一次纯对话（如纠正一个事实），G 也能根据提示词判断此时应该更新节点。
3. **白盒反思** — 反思过程（如删除了哪个过时节点、新增了哪个知识）同样会在 B 面（装配流水线 UI）向用户公开。用户的掌控感建立在系统的每一个动作都是透明的之上。
4. **给下一个"我"** — G 每次苏醒处理任务时都要同时考虑：这个信息对下一次苏醒的我（无论是处理项目还是了解用户）有用吗？
5. **用户侧写同样是节点** — 用户偏好、语言习惯、个人信息等不是硬编码的系统配置，而是特殊的元信息节点（如 `CTX_USER_PROFILE`）。G 同样有能力并在需要时**主动修改这些侧写节点**，从而实现对用户的动态对齐。

---

## G 的启动上下文

G 每次苏醒时看到的分层结构：

```
[用户配置]              ← 硬编码，不可选
  语言、身份偏好

[你的近期记忆]           ← 最近 5 轮对话（不压缩）
  上一轮: 用户问了 XXX, Genesis 回复了 YYY
  
[元信息节点目录]         ← TOOL/CONTEXT/LESSON 的标题+标签
  <TOOL> [SYS_TOOL_WEB_SEARCH] web_search
  <CONTEXT> [CTX_n8n_API认证] n8n API认证方式
  <LESSON> [LESSON_服务检查方法] 服务状态检查方法
```

---

## 缓存友好设计

Prompt 的前缀（配置 → 记忆 → 目录）是稳定的，LLM 的 prefix cache 自然命中。
越用越便宜 — 跟越用越聪明走的同一条线。

---

## 目录结构

```
Genesis/
├── factory.py           ← 极简工厂
├── discord_bot.py       ← Discord 入口（含频道历史注入）
├── start.sh             ← 启动脚本
├── .env                 ← API 配置
└── genesis/
    ├── core/            ← 最小依赖（base, config, registry, provider）
    ├── v4/              ← 引擎（agent, loop, manager）
    ├── tools/           ← 基础工具
    ├── skills/          ← Genesis 自己创建的技能
    └── providers/       ← LLM 提供商
```
