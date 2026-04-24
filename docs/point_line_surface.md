# 点线面元信息架构

> 2026-04-24 讨论，替代圆锥模型

## 核心动机

圆锥模型用数字评分（confidence/凝实度）衡量价值，跟实际脱节，无法调试。点线面用拓扑替代数字——价值不是算出来的，是从结构中涌现的。

---

## 点（Point）

- = LESSON / 锚点，LLM写，LLM读
- 分新点和旧点
- 新点 = 本轮探索中产生的新知识
- 旧点 = vault中已有的知识节点

---

## 线（Line）

线 = **推理链片段**，不是数字权重。

- 新点 → 旧点的线："我为什么觉得旧LESSON有用"（**异轮**线贡献旧点入线数，同轮线不贡献——防自刷）
- 新点 → 新点的线："新洞察基于什么想法/观察产生"（记录因果但不贡献入线数，防自刷）
- **同轮定义**：同一轮 GP 迭代中产生的所有新点互为同轮。reasoning_lines.same_round=1 标记同轮线，入线数查询排除同轮线。

### 线拆分为两个概念

- **因果（GP可见）**：推理链"基于什么产生"，GP可以知道因果关系
- **入线数（GP不可见）**：点被多少异轮新点基于它产生（reasoning_lines WHERE same_round=0），仅供后台判断价值。同轮线（same_round=1）不贡献入线数——否则 GP 可自刷入线数

### 线 = 逻辑去重

线是比内容语义更本质的去重维度。内容是表象，线是因果。

> **注意**：下表的"线相似"指推理链语义相似（因果关系相同），不是 basis 集合重叠。当前碰撞检测只实现了 basis 集合重叠（线相似的必要不充分条件），2×2 矩阵的完整实现需推理链语义比较，为远期目标。

| 线 | 内容 | 判定 | 操作 | 当前可判定？ |
|---|---|---|---|---|
| 相似 | 相似 | 纯重复 | 合并 | ✅ 碰撞检测可识别 |
| 相似 | 不同 | 逻辑重复/换皮 | 合并 | ⚠️ 需语义比较 |
| 不同 | 相似 | 殊途同归 | 保留，甚至建边 | ⚠️ 需语义比较 |
| 不同 | 不同 | 独立创新 | 保留 | ✅ basis 不重叠即可判定 |

殊途同归 = 多条线到同一结论 = 该结论更可靠，反而值得保留。殊途同归同时暗示：两条线引用的节点之间存在尚未被显式记录的关系（隐含边信号）。

### 写前去重（碰撞检测）

GP 准备写新点并连线到 A,B,C,D，发现 A,B,C 都已有线指向同一个点 X → "我要写的可能跟 X 重复"。

线的目标节点集合本身就是指纹，集合重叠度高 = 逻辑重复。不需要额外相似度算法。

**碰撞检测只提醒，不自动判定。** 返回给 GP："你引用的 A,B,C 已被节点 X 引用，X 的摘要是 xxx，确认是否重复"。让 GP 判断，不让算法判断——引用相同素材可以写出完全不同的结论，纯集合重叠会误杀合法创新。

GP 选择：
- 跟 X 重复 → 不写，标记虚点，继续推进或打磨当前方向
- 跟 X 部分重叠 → 写，但标注差异
- 不重复 → 正常写

### 虚点

写前去重发现重叠时不创建新点，标记虚点：
- 只有通过 1-hop 关系能搜到，不注入面
- GP 不能修改已有的点，只能选择继续推进或打磨
- 虚点 = "这里本该有个新洞察，但已有节点覆盖了"的占位符
- 虚点可被真理区分消费——反复出现在同一位置的虚点 = 该位置知识饱和

**虚点饱和信号必须注入面。** 虚点不注入面会导致 GP 看到沙漠 → 反复探索已饱和区域 → 空转。注入方式：不是注入虚点内容，而是注入一句话"该区域已有 N 个虚点 = 知识饱和"。

**⚠️ 虚点创建路径断裂**：碰撞检测后 GP 选择不写时，当前无工具调用来创建虚点。饱和信号依赖虚点存在→虚点依赖创建工具→创建工具不存在 = 逻辑死循环。**临时方案**：碰撞检测返回的碰撞候选（已有节点 X）本身携带了"此区域已有覆盖"的信号，搜索结果中标注碰撞候选即可替代虚点饱和信号，无需显式创建虚点。远期再补虚点创建工具。

### 采集方式

GP通过 `reasoning_basis` 参数主动连线。创新必须带线——reasoning_basis 为空时拒绝执行（validateInput）。没有线的创新 = 无法判断价值 = 无法去重 = 噪音。

---

## 面（Surface）

面 = **一次性的信息引用组合**，由点构成，每轮搜索后组装一次，用完即弃。

- 面不是持久结构，是当轮的上下文窗口填充
- 面用线的拓扑结构（入线数决定BFS流向），但不呈现线的因果内容（reasoning字段GP不可见）
- 面是搜索的后处理层，不替代搜索

```
search_knowledge_nodes → 找到种子点 A, B
  ↓
expand_surface(seed_ids, context_budget) → BFS扩散组装面
  ↓
GP看到：知识网络 + 前沿在哪 + 空洞在哪 + 点的角色（基础/探索）
```

### 面的两阶段组装

水流扩散和替换策略是两个方向相反的力，必须分阶段执行：

**阶段一：填充（优先队列遍历）** — 从种子点出发，优先队列按入线数排序遍历邻居。reasoning_lines 只沿 new→old 方向（走向已验证基础），node_edges 双向走。入线数高的路径优先扩展 = 已被反复验证的推理通道 = 可靠的推理基础。此阶段 GP 站在已验证的基础上。

**阶段二：推进（替换策略）** — 逐步将起点的点替换成边缘的点（新点），效果：GP 被推向知识前沿。

先填充基础，再推向前沿。不是同时生效。

### 冷启动

种子点 = 搜索命中节点，不需要额外机制。

### 点的角色标签

面中的点需要区分角色，让 GP 知道脚下哪里是实的：
- **基础**：入线数 ≥ 3（已被至少 3 条异轮线引用），已被反复验证，可靠的推理基础
- **探索**：入线数 < 3，新近产生，尚未被验证的前沿

不是数字评分，是角色标签。GP 不看到入线数数字，只看到角色标签（基础/探索）。数字会诱导 GP 把入线数当 confidence 用，回到圆锥模型老路。阈值 3 是经验值，可调。

### 面选择策略

暂不考虑。以 10 万 token 为假定上限，先塞满上下文，MVP 验证后再做面的选择优化。

---

## 价值信号 = 入线数

入线数 = 点被多少新点基于它产生 = 被后续推理验证的次数。不是"受欢迎程度"，是**被实践反复确认的次数**。

---

## 真理逼近

一生二，二生三，三生万物的倒推结构：点 A 被越多线连上 → 倒推 A 越接近真理。

### 真理区分（RAG消融）

点 A 积累足够入线后，从面中移除 A，**搜索结果中也隐藏 A**（否则 GP 会通过搜索绕过消融），观察 N 轮：

- **向前**：面缺了 A，LLM 依然推出正确结论 → A 是 LLM 内部已有的知识，不需要外部锚点 → **降级**
- **向后**：面缺了 A，LLM 推理链断裂或结论偏差 → A 是必要的逻辑跳板，没有它 LLM 虽然知道但调不出来 → **确认价值**

LLM 不缺真理，缺的是捋顺的逻辑链。向后不是说明 LLM 不知道，而是说明这个点作为推理链的中间跳板是必要的。

---

## 与圆锥模型的对比

| | 圆锥模型 | 点线面 |
|---|---|---|
| 价值信号 | confidence数字评分 | 入线数（拓扑） |
| 给GP看什么 | 凝实度摘要（数字） | 知识网络（拓扑） |
| 可调试性 | 黑盒 | 可观测：没有入线=没人基于它推理过 |
| 去重方式 | 内容语义相似度 | 线逻辑去重 |
| GP定位 | 看核心/高置信知识 | 始终在知识前沿 |

---

## 当前代码现状（2026-04-24 实施后更新）

### 已实现（9步全部完成）

| 组件 | 文件 | 状态 |
|---|---|---|
| reasoning_lines 表 + same_round 列 | `v4/manager.py` | ✅ 入线数查询排除同轮线 |
| RecordLessonNodeTool reasoning_basis | `tools/node_tools.py` | ✅ validateInput + 同轮检测 + 自动连线 |
| auto_mode 工具名修复 | `auto_mode.py` | ✅ record_lesson_node / record_context_node |
| 入线数 + 角色标签（严格版） | `tools/search_tool.py` | ✅ 只显示基础/探索，不显示数字 |
| 碰撞检测 | `tools/node_tools.py` | ✅ find_collision_candidates，只提醒不阻止 |
| 面两阶段组装 | `v4/surface.py` | ✅ 真替换（非追加），封装良好 |
| 虚点机制 | `v4/manager.py` + `search_tool.py` | ✅ is_virtual + 搜索过滤 + 饱和信号 |
| 旧架构清理 | `prompt_factory.py` + `knowledge_query.py` | ✅ 凝实度→密度，PROVEN/UNTESTED→基础/探索 |
| 真理区分 | `v4/manager.py` + `surface.py` | ✅ ablation_active + 双层过滤 |

### C-Phase 园丁模式（2026-04-24 改造）

点线面架构下，C 不创建新节点（LESSON_C_ 是拓扑死点：入线数永远=0）。
C 只修图不种树：

| C 的职责 | 机制 | 点线面角色 |
|---|---|---|
| Arena W/L 反馈 | 环境信号→活跃节点胜率更新 | 互补信号（入线数=被引用次数，W/L=引用后结果） |
| Persona 学习 | Multi-G 人格胜率 | 独立系统 |
| Trace Pipeline | 执行流实体提取 | 独立系统 |
| 消融触发 | 入线数≥5→隐藏节点，记录baseline_env_ratio | 面健康维护 |
| **矛盾检测** | LLM→CONTRADICTS边 | GP搜索可见，旧节点被标记 |
| **关联发现** | LLM→RELATED_TO边 | 面BFS跨锥体连接 |

全新知识的记录是 GP 的职责，C 不补作业。

### 未实现（设计-实现缺口）

| 缺口 | 说明 | 优先级 |
|---|---|---|
| 虚点创建工具 | 碰撞后GP选择不写时无显式标记虚点的调用，虚点1-hop可见性无从谈起 | 中 |
| 线语义去重 | 2×2矩阵中"线相似"需推理链语义比较，当前碰撞检测=basis集合重叠=必要不充分条件 | 远期 |
| 殊途同归隐含边 | 多条线到同一结论暗示basis间有未记录关系，未实现 | 远期 |
| ~~消融评估闭环~~ | ✅ 已实现：C-Phase 每轮检查 ablation_observing 节点，比较 current_env_ratio vs baseline，自动判定向前/向后 | ~~中~~ |
| 消融触发条件 | 设计要求三条件（入线数+idle rounds+面包含次级节点），实现只用了入线数≥5 | 低 |

### 保留兼容（不删除）

| 字段 | 原因 |
|---|---|
| confidence_score | Arena/Evidence Assessor 仍在用 |
| epistemic_status | schema 保留，显示层已替换 |
| IF/THEN/BECAUSE 模板 | LESSON 内容结构，与点线面不矛盾 |

---

## 工程实施计划

### Step 1：创建 reasoning_lines 表 + 写入接口

**文件**：`v4/manager.py`
- `_ensure_schema()` 中新增：
  ```sql
  CREATE TABLE IF NOT EXISTS reasoning_lines (
      line_id INTEGER PRIMARY KEY AUTOINCREMENT,
      new_point_id TEXT NOT NULL,       -- 新点（线的起点）
      basis_point_id TEXT NOT NULL,     -- 旧点（线的终点，被引用的节点）
      reasoning TEXT,                   -- GP 填写的因果说明
      source TEXT DEFAULT 'GP',         -- GP（C-Gardener 不创建 reasoning_lines，只加 node_edges）
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (new_point_id) REFERENCES knowledge_nodes(node_id),
      FOREIGN KEY (basis_point_id) REFERENCES knowledge_nodes(node_id)
  )
  CREATE INDEX IF NOT EXISTS idx_rl_basis ON reasoning_lines(basis_point_id)
  CREATE INDEX IF NOT EXISTS idx_rl_new ON reasoning_lines(new_point_id)
  ```
- 新增方法 `create_reasoning_line(new_point_id, basis_point_id, reasoning, source)`
- 新增方法 `get_incoming_line_count(node_id) -> int`：`SELECT COUNT(*) FROM reasoning_lines WHERE basis_point_id = ?`
- 新增方法 `get_basis_set_for_node(node_id) -> set`：返回某新点连线指向的所有 basis_point_id 集合（碰撞检测用）

### Step 2：RecordLessonNodeTool 加 reasoning_basis 参数

**文件**：`tools/node_tools.py`（class RecordLessonNodeTool）
- parameters 新增：
  ```python
  "reasoning_basis": {
      "type": "array",
      "items": {"type": "string"},
      "description": "此经验基于哪些已有节点产生（节点ID数组）。必填。搜索知识库后记录LESSON必须声明推理依据。"
  }
  ```
- required 列表加入 `"reasoning_basis"`
- execute() 签名加 `reasoning_basis: List[str] = None`
- execute() 开头加 validateInput 校验：
  ```python
  if not reasoning_basis:
      return "Error: reasoning_basis 不能为空。记录 LESSON 必须声明基于哪些已有节点产生此经验。请先搜索知识库，找到相关节点后填写 reasoning_basis。"
  ```
- execute() 写入节点后，遍历 reasoning_basis 调用 `self.vault.create_reasoning_line(node_id, bid, source="GP")`

### Step 3：修复 auto_mode 的工具名引用

**文件**：`auto_mode.py`
- 当前 `gp_unblock_tools: ["record_point", "record_line", "record_context_point"]` 引用了不存在的工具
- 方案：统一用现有工具名 `["record_lesson_node", "record_context_node"]`
- record_lesson_node 已含 reasoning_basis（Step 2 添加后），不需要单独的 record_line 工具
- 线的创建内嵌在 record_lesson_node 的 execute() 中

### Step 4：入线数计算 + 搜索输出改造

**文件**：`v4/manager.py` + `tools/search_tool.py`
- `get_digest()` 改造：移除 FACT/BELIEF/HYPOTHESIS 认知论，改为展示入线数 TOP 节点
- `search_tool.py` 搜索结果中每个节点内联入线数（供面组装使用）
- 入线数 = `get_incoming_line_count(node_id)`，搜索时批量计算避免 N+1

### Step 5：碰撞检测（validateInput 扩展） ✅

**文件**：`tools/node_tools.py`（RecordLessonNodeTool.execute）
- 在 reasoning_basis 校验通过后、写入节点之前，调用 `vault.find_collision_candidates(valid_basis, min_overlap=2)`
- 一次 SQL GROUP BY 找到 basis 集合重叠的已有节点，不需要 Jaccard 相似度
- **碰撞检测 = 线相似的必要不充分条件**：basis集合重叠≠推理链相似（引用相同素材可写出不同结论），只提醒不阻止
- 返回格式：`⚠️ 碰撞检测：你引用的节点已被 [X] 'title' (重叠N个basis)。确认是否重复？`
- 线语义去重（2×2矩阵的完整实现）为远期目标，当前碰撞检测足够 MVP

### Step 6：面两阶段组装（expand_surface）

**文件**：新建 `v4/surface.py` 或在 `v4/manager.py` 中新增
- `expand_surface(seed_ids, context_budget)` 方法：
  - **阶段一填充**：从种子点出发，沿 node_edges + reasoning_lines **有向**遍历（优先队列，非标准 BFS），优先走高入线数方向。线和边混走但**遵守方向约束**：
    - reasoning_lines：只沿 new→old 方向（从新点跳到被它引用的旧点），不反向跳。反向跳等于在填充阶段就推进到前沿，违反两阶段顺序。
    - node_edges：双向走（RESOLVES/TRIGGERS/REQUIRES 是强因果边，RELATED_TO 是弱关联边）
    - 这样填充阶段自然沿高入线数方向走向已验证基础，不会提前跳到前沿新点
  - **阶段二推进**：预算 60% 用完后，真正踢掉 fill 中高入线数节点（非追加），加入边缘新点
  - 输出：点列表 + 角色标签（基础/探索）
- **文件**：`tools/search_tool.py`
  - 搜索后处理调用 `expand_surface`，替换现有圆锥凝实度摘要
  - 输出末尾：`[面] N 点(N基础, M探索) | 虚点饱和: X区域`

### Step 7：虚点机制 ✅（部分）

**文件**：`v4/manager.py` + `tools/search_tool.py`
- knowledge_nodes 表新增标记：`is_virtual INTEGER DEFAULT 0`
- 虚点搜索可见性：搜索结果中 is_virtual=1 的节点被过滤，不直接出现
- 虚点不注入面，但面的输出末尾注入饱和信号：`[饱和] XXX 已有 N 个虚点 = 知识饱和`
- **⚠️ 未实现**：虚点创建路径——碰撞检测后GP选择不写时，无显式工具调用 `vault.create_node(is_virtual=1)`。虚点1-hop可见性需要虚点有边连向其他节点，当前虚点根本不会被创建，1-hop可见性无从谈起。需后续补一个"标记虚点"工具或在碰撞提醒中引导GP调用。

### Step 8：清理旧架构

- `search_tool.py:666-714`：圆锥凝实度摘要 → 替换为入线数+角色标签
- `knowledge_query.py get_digest()`：epistemic_status → 入线数 TOP
- `prompt_factory.py build_gp_prompt()`：knowledge_digest 注入面拓扑信息
- confidence_score 字段保留但不作为主要价值信号（向后兼容）

### Step 9：真理区分（RAG消融） ✅（基础框架）

- 消融触发条件：**简化版**——入线数≥5（设计要求三条件：入线数≥N + idle rounds≥3 + 面包含全部次级节点，后两者需 trace 数据支撑，MVP 跳过）
- 消融机制：knowledge_nodes 新增 `ablation_active INTEGER DEFAULT 0`（0=正常，1=消融观察中，2=已降级）
- 面组装时跳过 ablation_active>0 的点
- 搜索结果中也隐藏（ablation_active>0 的节点被过滤）
- **评估标准**：消融观察≥5分钟后（`activated_at < now - 300`），C-Phase 比较 current_env_ratio vs baseline_env_ratio：
  - env_ratio 下降 ≥ 0.1 → 向后（必要跳板，ablation_active→0，恢复可见）
  - env_ratio 不变或上升 → 向前（LLM内部已有，ablation_active→2，降级）
  - 无 baseline 数据 → 默认向后（保守策略：宁可保留也不丢失跳板）
- baseline_env_ratio 在 activate_ablation 时记录到 ablation_baselines 表
- **评估信号语义**：env_ratio 测的是 Op 执行成功率（环境信号），不是 LLM 推理链是否断裂。这是**代理信号**——缺了跳板→GP 推理偏差→Op 执行失败→env_ratio 下降。信号链：消融隐藏节点 → GP 搜索缺跳板 → GP 推理偏差 → Op 执行失败 → env_ratio 下降。不是直接测 LLM 推理，而是测 LLM 推理的下游后果。
- 当前线数据为空（刚创建表），消融机制需线积累后自然激活
