# 点线面元信息架构

> 2026-04-24 讨论，替代圆锥模型

## 核心动机

LLM 没有内部记忆。每次调用，上下文窗口打开，它诞生；窗口关闭，它死亡。任何不在窗口里的东西，对它而言都不存在。

但 LLM 需要理解一个复杂的代码库——信息量远超上下文窗口容量。它需要在每一轮"新生"时，瞬间继承所有历史探索的成果，知道哪里是稳固的基础，哪里是未探索的前沿，哪里是反复修补的伤疤。

点线面架构就是这个继承系统。它不是知识库，不是代码压缩，不是依赖图。它是 LLM 在探索过程中用推理链编织的一张外部菌丝网络。这张网络让一个只有"此刻"的智能体，在出生的瞬间就能一窥全貌。

圆锥模型用数字评分（confidence/凝实度）衡量价值，跟实际脱节，无法调试。点线面用拓扑替代数字——价值不是算出来的，是从结构中涌现的。

---

## 点（Point）

点 = LLM 在探索时产生的认知片段。不是"这段代码做什么"的客观描述，而是"我读到这段代码时，我理解了什么"。

类比：人类阅读代码时，脑子里闪过的不是 AST，而是一些半成品般的念头——"这个函数在这里做了权限校验"、"这个模块似乎在处理支付回调"、"这里的逻辑跟之前看到的 X 很像"。点就是这些念头的显式记录。

由此，点天然具备以下性质：
- **片面性**：它只捕捉当时 LLM 所见的那个角度
- **可错性**：它记录的是一种理解，而理解可能是错的
- **语境依附**：它诞生于某一次具体的探索，带着当时的上下文印记

不追求客观完整，追求的是"那一刻的真实"。

- 分新点和旧点
- 新点 = 本轮探索中产生的新认知片段
- 旧点 = vault中已有的认知锚点

区分新旧是为了追踪认知的演化方向。新点包含着本轮探索的发现，旧点代表着历史积累的基础。

### 地层（次概念）

地层只是点的来源背景，不是点线面的第四层，也不是新的价值评分。它用于解释：同样是"旧点"或"0入线点"，可能来自不同制度年代，不能简单等同为未探索前沿。

- **遗留地层**：点线面部署前由旧系统留下的节点。它们可能有价值，只是没有被 reasoning_lines 重新连入拓扑。
- **新生地层**：点线面部署后由 GP 通过点/线机制产生的节点。它们的入线数更能反映当前拓扑价值。
- **重连地层**：遗留节点被新点重新引用后，开始进入点线面的现代推理网络。
- **种子地层**：人工注入的概念地图节点，用于冷启动导航；它们先是坐标系，之后才可能被 GP 引用成推理 basis。

因此，0入线只表示"当前点线面拓扑尚未反复引用它"，不直接表示无价值。对遗留地层，正确动作不是立刻降权，而是等待或触发重连：让新的 GP 在验证它时写出新点，并用线把它接回网络。

---

## 线（Line）

线 = **推理链片段**，不是数字权重。

线记录的不是代码的依赖关系（A 调用了 B），而是推理的依赖关系："我之所以产生新认知 B，是因为我基于旧认知 A"。

类比：人类在理解一段代码时，突然说"啊，这个逻辑跟之前那个 X 是同一个问题"。这句话本身，就是一条线。它把两个原本可能分散在不同模块、不同时间点上的认知，用推理链连接了起来。

- 新点 → 旧点的线："我基于已有的某个认知，产生了这个新洞察。"（**异轮**线贡献旧点入线线数，同轮线不贡献）
- 新点 → 新点的线："我这个新洞察，是基于同轮中另一个新发现产生的。"（记录因果但标记为同轮线）
- **同轮定义**：同一 trace_id + round_seq 的 GP 工具执行轮中产生的所有新点互为同轮。reasoning_lines.same_round=1 标记同轮线，入线数查询排除同轮线；缺少轮次元信息时才退回时间窗兼容逻辑。

### 同轮隔离：为什么同轮线不算数

LLM 在单次调用中连续推理，产生的链条如果每条都算数，就等于"我引用我自己当证人"。这是循环论证。

因此，同轮线不贡献入线数。只有跨调用——完全不同的 LLM 实例，在完全不同的上下文里，独立踩上了同一条推理路径——才算一次真正的验证。

**同轮隔离不是防御性的工程约束，而是维持信任测量有效性的唯一前提。**

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

**虚点创建路径**：碰撞检测后由系统自动调用 `ensure_virtual_point()` 创建或递增虚点，并把虚点连向碰撞涉及的 basis 节点。GP 不需要、也不应该手动创建虚点。

### 采集方式

GP 优先通过低摩擦工具采集：先用 `record_point` 写新点，再用 `record_line` 为每个依据节点写因果线。旧工具 `record_lesson_node(reasoning_basis=...)` 保留兼容，但不再是 GP 主入口。没有线的创新 = 无法判断价值 = 无法去重 = 噪音。

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
- **基础**：入线数 ≥ P75（分布前25%，已被反复验证），可靠的推理基础
- **探索**：入线数 < P75，新近产生，尚未被验证的前沿

不是数字评分，是角色标签。GP 不看到入线数数字，只看到角色标签（基础/探索）。数字会诱导 GP 把入线数当 confidence 用，回到圆锥模型老路。阈值用分布分位数（P75）而非固定值，随知识库规模自适应：库小时阈值低，库大时阈值自动升高。

### 面选择策略

暂不考虑。以 10 万 token 为假定上限，先塞满上下文，MVP 验证后再做面的选择优化。

---

## 价值信号 = 入线数

入线数 = 点被多少个"异轮"新点基于它产生 = 这个点作为推理依据，被后来的探索者独立踩过多少次。

入线数不是"这个点说得好"的评分，不是受欢迎程度，不是点赞数。它是"这个点被后来的探索者反复踩过"的频次记录。被踩的次数多了，自然就成了路。

由此，入线数标记的往往不是正确答案，而是**反复被拆、反复被补的那面墙**。它高，不是因为设计得好，而是因为它处于冲突和修补的中心。

入线数的查询排除同轮线：`SELECT COUNT(*) FROM reasoning_lines WHERE basis_point_id = ? AND same_round = 0`。同轮线是用来记录因果的，不是用来做独立验证的。

LLM 不看到精确的入线数，只看到角色标签（"基础"或"探索"）。这个设计防止 LLM 把入线数当成置信度，然后开始追逐数字，走回把一切都打分的老路。

---

## 真理逼近

一生二，二生三，三生万物的倒推结构：点 A 被越多线连上 → 倒推 A 越接近真理。

### 真理区分（RAG消融）

点 A 积累足够入线后，从面中移除 A，**搜索结果中也隐藏 A**（否则 GP 会通过搜索绕过消融），观察 N 轮：

- **向前**：面缺了 A，LLM 依然推出正确结论 → A 是 LLM 内部已有的知识，不需要外部锚点 → **降级**
- **向后**：面缺了 A，LLM 推理链断裂或结论偏差 → A 是必要的逻辑跳板，没有它 LLM 虽然知道但调不出来 → **确认价值**

LLM 不缺真理，缺的是捋顺的逻辑链。向后不是说明 LLM 不知道，而是说明这个点作为推理链的中间跳板是必要的。

### 主动遗忘与置换

真理区分同时承担系统的主动遗忘功能。当节点密集到一定程度，系统不仅通过真理区分验证必要性，还在网络已经足够密的前提下，主动剔除某些"旧1"（旧的解释模型），观察系统是否能产生"新1"（新的、更好的解释模型）。

旧1被剔除后，原本被它压制的、散落各处的探索点突然获得连接的机会。在认知真空里，菌丝网络的生长本性会驱使系统寻找新的路径去解释那些失去了旧依赖的现象。新1可能由此涌现——它更简洁、解释力更强，但它不是从旧1推导出来的，而是在旧1遗留的空白里新长出来的。

**涌现的真正位置**：不是设计一个复杂系统让它涌现，而是设计一个定期清空、逼系统重新生长的机制，让涌现成为常态。

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

## 概念地图

概念地图是在代码库层面为 LLM 提前构建的领域认知框架。它告诉 LLM：“这是什么样的世界、你在跟什么概念打交道、哪些规则是不可违背的、哪里埋着历史的伤疤。”

与菌丝网络的动态生长不同，概念地图是领域知识的冷启动注入。它让 LLM 在第一次面对代码时，就拥有一个导航坐标系，不至于在混乱中迷失。

概念地图与点线面的关系：
- 概念地图 = 静态的领域骨架（代码库的不可违背的约束、架构边界、历史伤疤）
- 菌丝网络 = 动态的探索足迹（LLM 在探索中产生的点和线）
- 两者互补：概念地图提供方向感，菌丝网络提供具体路径

---

## 自洽性检验

从“LLM 没有状态”这一条约束出发，整个架构是逐步推论后的必然产物：

- 没有内部记忆，所以记忆必须在外部
- 外部记忆不能只存原始经验，必须压缩
- 压缩不能丢逻辑关系，所以依赖必须记录为推理链
- 推理链的信任不能来自同一实例，所以同轮不计数
- 信任累积导致惯性，所以需要纠偏——填充之后必须推进，必要时必须遗忘
- 遗忘不能只针对已知节点，所以未来需要覆盖面之外的新猜测
- 一切操作最终不是为了存储更多信息，而是为了让无状态的 LLM 在出生的瞬间，找到抵达问题本质的最短路径

在这个逻辑链中，点的定义与线的定义匹配（足迹需要推理链来追溯价值），入线数与真理区分匹配（一个测频次，一个测必要性），面的填充与推进匹配（先踩稳再探索），碰撞检测与同轮隔离匹配（用跨实例验证来去重）。每一对机制彼此咬合，没有互相矛盾的定义。

### 必然性论证

在这个逻辑链里没有一个节点是可选配置：

- 去掉压缩，经验日志会撑爆窗口
- 把依赖定义为语义相近而不定义为推理链，会混同“殊途同归”和“换皮重复”，丢失对知识价值的判断能力
- 允许同轮线计入验证，入线数就退化成自刷游戏
- 只有面的填充没有推进，探索者会永远踩在旧知识上无法走向前沿
- 没有真理区分——通过反事实切除测试必要性——系统就无法区分“被内化的旧跳板”和“仍然必要的外部锚点”
- 没有虚点标记饱和，探索者就会在已经探索完毕的区域反复空转

所有这些机制的必然性，都源于最初那个被彻底接纳的约束：**LLM 没有状态，它只有此刻。** 你为这个只有此刻的存在，搭建了一个能承载时间、历史与探索的外部拓扑。它踩着这张网走进未知，每走一步，网又向外延伸一寸。

---

## 当前代码现状（2026-04-24 实施后更新）

### 已实现（9步全部完成）

| 组件 | 文件 | 状态 |
|---|---|---|
| reasoning_lines 表 + same_round/trace_id/round_seq | `v4/manager.py` | ✅ 入线数查询排除同轮线，优先按轮次身份判断 |
| 低摩擦 point/line 工具 + 旧工具兼容 | `tools/node_tools.py` | ✅ record_point / record_line 为 GP 主入口；record_lesson_node 保留兼容 |
| auto_mode 工具暴露 | `auto_mode.py` | ✅ record_point / record_line 默认可见；record_context_node 按需解锁 |
| 入线数 + 角色标签（严格版） | `tools/search_tool.py` | ✅ 只显示基础/探索，不显示数字 |
| 碰撞检测 | `tools/node_tools.py` | ✅ find_collision_candidates，只提醒不阻止 |
| 面两阶段组装 | `v4/surface.py` | ✅ 真替换（非追加），封装良好 |
| 虚点机制 | `v4/manager.py` + `search_tool.py` | ✅ is_virtual + 搜索过滤 + 饱和信号 |
| 旧架构清理 | `prompt_factory.py` + `search_tool.py` + `knowledge_query.py` | ✅ GP 可见数字评分/密度语言→基础/探索/面状态 |
| 真理区分 | `v4/manager.py` + `c_phase.py` + 搜索/面过滤 | ✅ ablation_active + 双层过滤，搜索后处理保持纯读 |

### C-Phase 园丁模式（2026-04-24 改造）

点线面架构下，C 不创建新节点（LESSON_C_ 是拓扑死点：入线数永远=0）。
C 只修图不种树：

| C 的职责 | 机制 | 点线面角色 |
|---|---|---|
| Arena 成败反馈 | 环境信号→活跃节点胜率更新 | 互补信号（入线数=被引用次数，成败记录=引用后结果） |
| Persona 学习 | Multi-G 人格胜率 | 独立系统 |
| Trace Pipeline | 执行流实体提取 | 独立系统 |
| 消融触发 | 入线数≥5→隐藏节点，记录baseline_env_ratio | 面健康维护 |
| **矛盾检测** | LLM→CONTRADICTS边 | GP搜索可见，旧节点被标记 |
| **关联发现** | LLM→RELATED_TO边 | 面BFS跨锥体连接 |

全新知识的记录是 GP 的职责，C 不补作业。

### 未实现（设计-实现缺口）

| 缺口 | 说明 | 优先级 |
|---|---|---|
| ~~面BFS方向约束~~ | ✅ 已修复：`get_neighbor_map()` 增加 `include_reverse_reasoning` 参数，填充阶段传 `False`（只走 new→old） | ~~高~~ |
| ~~BASIS_INCOMING_THRESHOLD~~ | ✅ 已修复：固定阈值→自适应分位数 `BASIS_INCOMING_PERCENTILE=75`（P75），随知识库规模变化 | ~~中~~ |
| ~~虚点创建路径~~ | ✅ 已修复：碰撞检测后自动调用 `ensure_virtual_point()`（系统行为，非GP行为），虚点自动连向碰撞basis节点（1-hop可见） | ~~中~~ |
| ~~概念地图~~ | ✅ 已实现：`_ensure_concept_seeds()` + `concept_seeds.yaml`，首次部署时注入 CONTEXT 种子节点，复用现有搜索/面机制 | ~~远期~~ |
| ~~主动遗忘与置换~~ | ✅ 已实现：`ablation_active=3` + `check_proactive_pruning_candidates()` + `evaluate_proactive_pruning()`，C-Phase确定性部分触发 | ~~远期~~ |
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
      same_round INTEGER DEFAULT 0,    -- 同轮线标记：1=同轮（不贡献入线数），0=异轮
      trace_id TEXT,                   -- 运行 trace 身份，用于真实同轮判断
      round_seq INTEGER,               -- GP 工具执行轮序号，用于真实同轮判断
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (new_point_id) REFERENCES knowledge_nodes(node_id),
      FOREIGN KEY (basis_point_id) REFERENCES knowledge_nodes(node_id)
  )
  CREATE INDEX IF NOT EXISTS idx_rl_basis ON reasoning_lines(basis_point_id)
  CREATE INDEX IF NOT EXISTS idx_rl_new ON reasoning_lines(new_point_id)
  CREATE INDEX IF NOT EXISTS idx_rl_trace_round ON reasoning_lines(trace_id, round_seq)
  ```
- 新增方法 `create_reasoning_line(new_point_id, basis_point_id, reasoning, source, same_round, trace_id, round_seq)`
- 新增方法 `get_incoming_line_count(node_id) -> int`：`SELECT COUNT(*) FROM reasoning_lines WHERE basis_point_id = ? AND same_round = 0`
- 新增方法 `get_incoming_line_counts_batch(node_ids) -> dict`：批量版，避免 N+1
- 新增方法 `get_basis_set_for_node(node_id) -> set`：返回某新点连线指向的所有 basis_point_id 集合（碰撞检测用）
- 新增方法 `get_same_round_ids(node_ids, trace_id, round_seq, window_seconds=600) -> set`：优先按真实轮次身份判断同轮；无轮次信息时退回时间窗兼容逻辑

### Step 2：低摩擦 record_point / record_line + RecordLessonNodeTool 兼容

**文件**：`tools/node_tools.py`（class RecordLessonNodeTool）
- `record_point`：只负责记录轻量知识点（默认 LESSON），返回新点 ID
- `record_line`：只负责记录一条因果线，并按 trace_id + round_seq 自动标记 same_round
- `record_lesson_node`：保留 `reasoning_basis` 兼容旧调用；内部仍会写线，但 GP 默认优先使用 point/line 两步工具
- parameters 新增（对象数组，每条线带独立因果推理）：
  ```python
  "reasoning_basis": {
      "type": "array",
      "items": {
          "type": "object",
          "properties": {
              "basis_node_id": {"type": "string", "description": "基于哪个已有节点产生此经验"},
              "reasoning": {"type": "string", "description": "为什么基于这个特定节点？不同basis的reasoning必须不同"}
          },
          "required": ["basis_node_id", "reasoning"]
      },
      "description": "推理线（必填）：每条线回答一个不同的因果问题。至少2条线。"
  }
  ```
- required 列表加入 `"reasoning_basis"`
- execute() 签名加 `reasoning_basis: List[Dict[str, str]] = None`
- execute() 开头加 validateInput 校验：
  ```python
  if not reasoning_basis:
      return "Error: reasoning_basis 不能为空。记录 LESSON 必须声明基于哪些已有节点产生此经验，且每条线的reasoning必须针对该basis节点回答不同的因果角度。"
  ```
- execute() 解析 basis_entries 后，遍历调用 `self.vault.create_reasoning_line(node_id, bid, reasoning=line_reasoning, source="GP", same_round=sr)`
- 同轮检测：basis 中哪些是本轮刚创建的（`vault.get_same_round_ids`），标记 same_round=1
- 碰撞检测：写入前 `vault.find_collision_candidates(valid_basis, min_overlap=2)`，只提醒不阻止

### Step 3：修复 auto_mode 的工具暴露

**文件**：`auto_mode.py`
- `record_point` / `record_line` 不在 GP_BLOCKED_TOOLS 中，GP 默认可用
- auto 模式只按需解锁 `record_context_node` 创建结构锚点
- `record_lesson_node` 保留兼容但不再作为 auto 主引导入口

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

### Step 6：面两阶段组装（expand_surface） ✅

**文件**：`v4/surface.py`
- `expand_surface(seed_ids, context_budget, replace_ratio=0.6)` 方法：
  - **阶段一填充**：从种子点出发，沿 node_edges + reasoning_lines 遍历（优先队列，非标准 BFS），优先走高入线数方向。
    - reasoning_lines 方向约束 ✅：`_prefetch_neighbors(seed_ids, directional=True)` → `get_neighbor_map(node_ids, include_reverse_reasoning=False)`，填充阶段只走 new→old（踩稳基础），不反向跳到前沿新点
    - node_edges：双向走（RESOLVES/TRIGGERS/REQUIRES 是强因果边，RELATED_TO 是弱关联边）
  - **阶段二推进**：预算前 60% 用于填充，剩余用于推进。踢掉 fill 中高入线数节点（真替换，非追加），用前沿节点替换
  - 输出：点列表 + 角色标签（基础/探索）
  - ✅ 阈值自适应：`BASIS_INCOMING_PERCENTILE=75`（入线数分布 P75），`BASIS_INCOMING_FLOOR=1`（最低阈值）。`get_incoming_count_percentile()` 动态计算，随知识库规模变化
- **文件**：`tools/search_tool.py`
  - 搜索后处理调用 `expand_surface`，输出纯文本面状态，不暴露 fusion_score / W-L 数字 / 知识密度分级
  - 输出末尾：`[基础] N 个已验证节点 | [探索] M 个前沿节点 | [饱和] X区域`

### Step 7：虚点机制 ✅

**文件**：`v4/manager.py` + `tools/node_tools.py` + `tools/search_tool.py`
- knowledge_nodes 表新增标记：`is_virtual INTEGER DEFAULT 0`
- 虚点搜索可见性：搜索结果中 is_virtual=1 的节点被过滤，不直接出现
- 虚点不注入面，但面的输出末尾注入饱和信号：`[饱和] XXX 已有 N 个虚点 = 知识饱和`
- ✅ 虚点创建路径：碰撞检测后自动调用 `vault.ensure_virtual_point(area_hint, basis_overlap_ids)`（系统行为，非GP行为）。概念要求"系统会在该位置记录一个虚点"——碰撞=有人试图在此区域探索但发现重叠=饱和信号
  - 虚点 ID 由 area_hint 的 MD5 生成（同区域同 ID，稳定去重）
  - 已有虚点则递增 usage_count（饱和度计数）
  - 新虚点自动连向碰撞涉及的 basis 节点（RELATED_TO边，1-hop可见性）
  - GP继续写入也没关系——虚点只是额外的饱和标记

### Step 8：清理旧架构

- `search_tool.py`：圆锥凝实度摘要 → 替换为基础/探索/面状态；内部 fusion_score 仅保留给排序和 Arena 归因，不直接显示给 GP
- `knowledge_query.py get_digest()`：epistemic_status → 入线数 TOP
- `prompt_factory.py build_gp_prompt()`：knowledge_digest 注入面拓扑信息
- confidence_score 字段保留但不作为主要价值信号（向后兼容）

### Step 9：真理区分（RAG消融） ✅

- 消融触发条件：**简化版**——入线数≥5（设计要求三条件：入线数≥N + idle rounds≥3 + 面包含全部次级节点，后两者需 trace 数据支撑，MVP 跳过）
- 消融机制：knowledge_nodes 新增 `ablation_active INTEGER DEFAULT 0`（0=正常，1=消融观察中，2=已降级，3=主动修剪中）
- 面组装时跳过 ablation_active>0 的点
- 搜索结果中也隐藏（ablation_active>0 的节点被过滤）
- **评估标准**：消融观察≥5分钟后（`activated_at < now - 300`），C-Phase 比较 current_env_ratio vs baseline_env_ratio：
  - env_ratio 下降 ≥ 0.1 → 向后（必要跳板，ablation_active→0，恢复可见）
  - env_ratio 不变或上升 → 向前（LLM内部已有，ablation_active→2，降级）
  - 无 baseline 数据 → 默认向后（保守策略：宁可保留也不丢失跳板）
- baseline_env_ratio 在 activate_ablation 时记录到 ablation_baselines 表
- **评估信号语义**：env_ratio 测的是 Op 执行成功率（环境信号），不是 LLM 推理链是否断裂。这是**代理信号**——缺了跳板→GP 推理偏差→Op 执行失败→env_ratio 下降。信号链：消融隐藏节点 → GP 搜索缺跳板 → GP 推理偏差 → Op 执行失败 → env_ratio 下降。不是直接测 LLM 推理，而是测 LLM 推理的下游后果。
- 当前线数据为空（刚创建表），消融机制需线积累后自然激活

### Step 10：主动遗忘与置换 ✅

**文件**：`v4/manager.py` + `v4/c_phase.py`
- 概念：消融=验证必要性（缺了它行不行？），主动遗忘=诱导涌现（故意拿走，逼系统找新路）
- `ablation_active=3` 标记主动修剪（区别于1=消融观察，2=已降级）
- 触发条件（比消融严格得多）：
  - 入线数 ≥ 8（高度验证，惯性极强——最需要打破）
  - trust_tier = HUMAN 或 REFLECTION（高信任 = 惯性最强）
  - 1-hop 邻居数 ≥ 5（网络足够密，修剪不会导致断裂）
  - ablation_active = 0（未在消融观察中）
  - 排除 SEED_CTX_ 和 VIRT_ 节点
- 行为：跳过观察期，直接隐藏。5分钟后评估
- 评估（`evaluate_proactive_pruning`）：
  - 该区域有新节点涌现 → 修剪成功，旧节点永久降级(ablation_active→2)
  - env_ratio 下降 → 该区域依赖旧模型，恢复(ablation_active→0)
  - 无新节点且 env_ratio 稳定 → 继续观察
- C-Phase 确定性部分触发，零 LLM 开销

### Step 11：概念地图种子 ✅

**文件**：`v4/manager.py` + `v4/concept_seeds.yaml`
- 概念：领域知识的冷启动注入，让 LLM 第一次面对代码时拥有导航坐标系
- 实现：`_ensure_concept_seeds()` 在 `_ensure_schema()` 后自动执行
  - 检查是否已有 SEED_CTX_ 前缀节点（只注入一次）
  - 从 `concept_seeds.yaml` 读取种子，创建 CONTEXT 节点（trust_tier=HUMAN）
  - 种子间建立 RELATED_TO 边（概念地图骨架）
- 复用现有搜索/面机制，零新路径
- YAML 文件由人工维护 = 静态骨架，与菌丝网络的动态生长互补
- 当前种子：架构、基础设施、知识系统、已知陷阱、数据库
