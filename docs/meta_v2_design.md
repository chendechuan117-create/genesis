# 元信息系统 V2 设计

> 2026-04-22 · 基于 LLM 行为定律 + 点线面架构
>
> 核心命题：**当前 LESSON 模板是为数据库设计的，不是为 LLM 设计的。**
> 点线面用拓扑替代了索引，结构化分类字段失去存在理由。
> LLM 擅长说话，不擅长填表。

---

## 一、设计前提：LLM 不调 record_lesson_node 的根因

### 1.1 摩擦-激励不对齐

| 工具 | 必填参数 | 对当前任务价值 | GP 选择倾向 |
|------|---------|--------------|------------|
| `shell` | 1（命令） | 高 | ✅ |
| `read_file` | 1（路径） | 高 | ✅ |
| `record_lesson_node` | 8（node_id/title/verb/noun/context/steps/because/resolves） | 零 | ❌ |

8 个必填字段 = 8 个决策点。每个决策点都是 Instruction Attenuation 的衰减节点。
GP 选择低摩擦路径不是"不配合"，是 LLM 行为定律预测的必然结果。

### 1.2 线和点绑死

当前 `reasoning_basis` 是 `record_lesson_node` 的一个可选参数。
GP 必须先创建完整 LESSON 才能连线。

但线的真实产生时刻是：

```
GP搜索 → 命中旧节点 → "这个有用，因为Y" → 线应在此刻产生
                                              ↓
                                    但机制要求先填8字段创建LESSON
                                              ↓
                                    GP跳过，线永远不产生
```

### 1.3 LLM 定律逐条映射

| 定律 | 当前LESSON模板的表现 | V2应避免的 |
|------|---------------------|-----------|
| Instruction Attenuation (39%) | 8字段中后5个衰减为机械填写 | 减少必填字段 |
| Over-Helpfulness | trigger_verb/noun/context 编造分类 | 不要求分类 |
| Fragile Tool-Use Under Stress | 压力下选1参数shell而非8参数LESSON | 降低工具摩擦 |
| Premature Commitment | 搜索命中后被迫做完整知识沉淀决策 | 线和点解耦 |
| Context Rot | 结构化字段占token但信息密度低 | 自然语言content |
| Recovery > Initial Correctness | 要求首次填对8字段 | 支持迭代补充 |
| Mode Collapse | 唯一重动作(record_lesson_node)被跳过→跳过→习惯性跳过 | 多个轻动作 |

---

## 二、V2 架构：点·线·面

### 2.1 点（Point）

**定义**：知识原子。LLM 写，LLM 读。一句话标识 + 自然语言正文。

**新点与旧点**（point_line_surface.md L14-16）：
- **旧点** = vault 中已有的知识节点（搜索命中时看到的）
- **新点** = 本轮探索中产生的新知识（GP/C-Phase 写入的）
- **判断只留存于一轮**：新旧点的区分是动态的——本轮的新点在下一轮就是旧点
- V2 的 record_point 创建的都是新点，搜索命中的都是旧点

```
POINT = {
  id:        自动生成（title 的短hash，如 P_a3f2）
  title:     一句话描述（必填）
  content:   自然语言正文（必填）
  created_by: "GP" | "C" | "HUMAN"
  created_at: timestamp
  epistemic:  "BELIEF" → Arena验证 → "FACT"
}
```

**与当前 LESSON 的字段映射**：

| 旧字段 | V2去向 | 理由 |
|--------|--------|------|
| node_id (LESSON_XXX) | 自动生成 | LLM不擅长发明全局唯一标识符 |
| title | ✅ 保留 | LLM天然产出 |
| trigger_verb/noun/context | ❌ 删除 | 拓扑替代关键词索引；LLM编造分类 |
| action_steps | → content | 步骤是content的一部分，不需要拆成数组 |
| because_reason | → 线的`why` | "为什么有效"="基于什么推理"=线 |
| resolves | → RESOLVES边 | 已有边机制，不需要在点里重复 |
| prerequisites | → REQUIRES边 | 同上 |
| contradicts | → CONTRADICTS边 | 同上 |
| reasoning_basis | → 独立`record_line` | 线应解耦，推理时随手连 |
| confidence/arena | → 入线数（GP不可见） | 拓扑替代数字评分 |

**结果**：8 个必填 → 2 个必填（title + content）。

### 2.2 线（Line）

**定义**：推理链片段 / 判断依据。不是数字权重。

**核心设计**：线和点解耦。线是独立动作，不绑定在点的创建上。

**线的两种方向**（point_line_surface.md L25-26）：
- **新点 → 旧点**："我为什么觉得旧LESSON有用" — 搜索命中后连线
- **新点 → 新点**："新洞察基于什么想法/观察产生" — 本轮探索中产生的洞察之间的因果

```
LINE = {
  line_id:         自动生成
  new_point_id:    新点或当前洞察的标识（= from端，允许 INSIGHT_虚拟标记）
  basis_point_id:  被参考的旧点（= to端）
  reasoning:       "为什么觉得那个点有用/如何推导出此经验"（自然语言 = why）
  source:          "GP" | "C"  ← V2新增列
  trace_id:        来源trace
  round_seq:       轮次序号
  created_at:      timestamp
}
```

**线的两个概念**（已确认，point_line_surface.md）：

| 概念 | 可见性 | 用途 |
|------|--------|------|
| 因果（why字段） | GP可见 | 推理链记录："基于什么产生" |
| 入线数（basis_point_id的COUNT） | GP不可见 | 价值信号：被多少新点基于它产生 |
| 线相似度（推理链相似度） | 后台用 | 去重/换皮筛查：两条线的why相似 → 可能是换皮（待设计） |

**采集方式**：

```
# 方向1：新点→旧点（搜索命中后连线）
GP搜索 → 命中旧点P_abc → "这个有用因为Y"
  → record_line(to_id="P_abc", why="Y")   ← 2参数，摩擦≈shell
  → 继续任务                               ← 推理流不中断
  （from端=new_point_id 由系统自动填充：本轮已有record_point则用其ID，否则用INSIGHT虚拟标记）

# 方向2：新点→新点（本轮新洞察之间的因果）
GP发现A → 基于A发现B → record_line(to_id="P_A", why="B基于A的观察产生")
  ← 同样2参数，连线不中断推理
```

### 2.3 面（Surface）

**定义**：由点组合而成的拓扑网络。面是搜索的后处理层。

**关键原则**（point_line_surface.md L30, L56）：**面不需要因果关系，只需要知道"有什么"**。
- 点→面不经过线（面不需要因果关系）
- 面按推导链组合成网，但面本身不关心因果——它只呈现拓扑

**不变的扩散机制**：
- 种子点 = 搜索命中节点（top 8）
- BFS 沿**边**（RESOLVES/REQUIRES/TRIGGERS/RELATED_TO）扩散——边是面的扩散通道
- 60% 预算切换替换阶段（踢核心/旧，加前沿邻居）
- GP 始终看到知识前沿

**线与面的关系**：
- 线不是面的扩散通道——线记录因果，面呈现拓扑，两者独立
- 但线的存在**间接影响面**：线密集的区域 → 新点更多 → 面的节点更多 → 面更"厚"
- 面的空洞 = 无出边的方向（不是无线的方向）

**V2 的变化**：
- 面的扩散通道仍以边为主（与设计原则一致）
- 新增：面呈现时可标注线的密集度（"此区域推理活跃"），但不沿线扩散

**⚠️ 已决策**：保留 expand_surface 沿线+边扩散（manager.py:685-697）。
- 线比边更密集（每个新点至少1条线，但不一定有边），沿线扩散能发现边未覆盖的邻居
- "面不需要因果" = 面呈现时不暴露因果，而非扩散时不走因果路径
- 扩散通道优先级：lines（因果链）> 强边（RESOLVES/REQUIRES/TRIGGERS）> 弱边（RELATED_TO）

### 2.4 与圆锥模型的对比（point_line_surface.md L90-98）

| | 圆锥模型 | 点线面 V2 |
|---|---|---|
| 价值信号 | confidence 数字评分 | 入线数（拓扑） |
| 给 GP 看什么 | 凝实度摘要（数字） | 知识网络（拓扑） |
| 可调试性 | 黑盒，调参数看效果 | 可观测：没有入线 = 没人基于它推理过 |
| 去重方式 | 内容语义相似度（0.85 阈值） | 线相似度（推理链相似度） |
| GP 定位 | 看核心/高置信知识 | 始终在知识前沿 |
| 知识记录 | 8 字段表单（record_lesson_node） | 2 参数笔记（record_point）+ 2 参数连线（record_line） |
| 因果记录 | 绑在 reasoning_basis 里 | 独立线表，GP 实时连线 |

---

## 三、工具设计：为 LLM 舒适度优化

### 3.1 核心原则

> **工具的参数数量应与 LLM 对该动作的认知负荷匹配。**
> 记笔记 = 低负荷（2参数），填表单 = 高负荷（8参数）。

### 3.2 record_point（替代 record_lesson_node）

```json
{
  "name": "record_point",
  "description": "记录一个知识笔记。搜索知识库后有了新发现，或完成了一个有价值的操作，用它写下来。写的时候像记笔记一样自然就行。",
  "parameters": {
    "type": "object",
    "properties": {
      "title": {
        "type": "string",
        "description": "一句话描述这个知识，如'nginx配置typo导致启动失败'"
      },
      "content": {
        "type": "string",
        "description": "自然语言正文。写你实际做了什么、发现了什么、为什么这么做。不需要拆步骤或填分类。"
      },
      "resolves": {
        "type": "string",
        "description": "可选。此经验主要解决的具体报错或异常现象。"
      }
    },
    "required": ["title", "content"]
  }
}
```

**与 record_lesson_node 对比**：

| 维度 | record_lesson_node | record_point |
|------|-------------------|--------------|
| 必填参数 | 8 | 2 |
| 标识符 | 手动发明 LESSON_XXX | 自动生成 |
| 分类 | verb/noun/context 三选词 | 不需要 |
| 步骤 | 拆成数组 | 自然语言正文 |
| 因果 | 绑在reasoning_basis里 | 独立record_line |
| 认知负荷 | 高（每字段=决策点） | 低（写一句话+一段话） |

**内部处理**（LLM 不需要知道）：
- `id` = title 前20字符的短hash，如 `P_a3f2`
- `content` 存入 `node_contents` 表（实际表名复数）
- `resolves` 如果非空 → 自动创建 RESOLVES 边
- 语义去重：content 向量 ≥0.85 → 合并，0.65-0.85 → 自动建 RELATED_TO 边
- epistemic 默认 BELIEF

### 3.3 record_line（新增，独立于点）

```json
{
  "name": "record_line",
  "description": "画一条推理线：声明'我基于哪个已有知识产生了当前判断'。搜索知识库后觉得某个节点有用时，立即调用此工具连线——不需要先创建新节点，先连再说。示例：搜索命中 LESSON_NGINX_PORT 后，调用 record_line(to_id='LESSON_NGINX_PORT', why='同属nginx启动问题但根因不同')",
  "parameters": {
    "type": "object",
    "properties": {
      "to_id": {
        "type": "string",
        "description": "你基于的已有节点ID（搜索结果中的node_id），如 P_abc 或 LESSON_XXX"
      },
      "why": {
        "type": "string",
        "description": "为什么觉得那个节点有用/如何推导出当前判断。一两句话就行。"
      }
    },
    "required": ["to_id", "why"]
  }
}
```

**关键设计**：
- `new_point_id`（from端）不需要 GP 填——系统自动用当前轮次的"推理上下文"
  - 如果 GP 在同一轮次先调了 `record_point`，new_point_id = 新创建的点的 id
  - 如果 GP 还没创建点，new_point_id = 虚拟标记 `INSIGHT_{trace_id}_{seq}`，后续 record_point 时自动关联
- `basis_point_id`（to端）= GP 填的 `to_id` 参数
- `reasoning` = GP 填的 `why` 参数
- 2 个必填参数，和 `shell` 同级别摩擦
- **validateInput**（借鉴 CC）：如果 to_id 不存在于 knowledge_nodes，返回错误 + 建议修正

### 3.4 record_context_point（替代 record_context_node）

```json
{
  "name": "record_context_point",
  "description": "记录环境上下文信息，如配置状态、目录结构、API布局等。",
  "parameters": {
    "type": "object",
    "properties": {
      "title": {"type": "string", "description": "一句话描述"},
      "content": {"type": "string", "description": "自然语言正文"}
    },
    "required": ["title", "content"]
  }
}
```

内部：type 标记为 CONTEXT，其余同 record_point。

---

## 四、GP 行为流：V1 vs V2

### V1（当前）：GP 搜索命中旧节点后

```
搜索 → 命中 LESSON_NGINX_PORT → "这个有用"
  → 想连线？先填8字段创建LESSON → 太重，跳过
  → 继续执行 → 知识没写回 → 线=0
```

### V2：GP 搜索命中旧节点后

```
搜索 → 命中 P_abc → "这个有用，因为同属nginx启动问题但根因不同"
  → record_line(to="P_abc", why="同属nginx启动问题，但那个查端口这个查配置")
  ← 2参数，3秒完成，推理流不中断
  → 继续执行 → 发现配置typo → record_point(title="nginx配置typo", content="...")
  ← 2参数，记笔记一样
  → 系统自动把线和点关联
```

**关键差异**：V2 中线的采集发生在推理的自然节点，不是中断推理去填表单。

---

## 五、知识产出：GP 是主要产出源

### 5.1 核心决策：点由 GP 产出

V1 中知识产出源是 C-Phase 的 `_run_knowledge_extraction()`（单轮LLM提取0-10条LESSON）。
V2 中 **GP 是点的主要产出源**——GP 在执行过程中实时记录，不再依赖 C-Phase 事后提炼。

理由：
- GP 有第一手经验（搜索、执行、观察），C-Phase 只看摘要
- GP 实时记录 = 线自然产生（搜索命中→连线→记点）
- C-Phase 事后提炼 = 线必须事后补，因果链断裂
- 低摩擦工具（2参数）让 GP 记录不再是负担

### 5.2 C-Phase 的新角色：补全而非替代

C-Phase 不再是知识的主要产出源，而是**补全者**：
- **补全边**：GP 的 record_point 只带了 resolves（可选），C-Phase 从轨迹中补建 REQUIRES/TRIGGERS/CONTRADICTS 边
- **补全深层线**：GP 连了浅层因果（"这个有用因为Y"），C-Phase 可以连深层（"为什么Y成立"）
- **语义去重审核**：GP 写了两个相似的 point，C-Phase 判断是否合并
- **VOID 升格**：C-Phase 发现填补 VOID 的实证时，升格为 POINT 并删除原 VOID

### 5.3 `_run_knowledge_extraction()` 的改造

当前实现（loop.py `_run_knowledge_extraction`）：
- 压缩 GP 执行为摘要 → 单轮 LLM 调用 → 提取 0-10 条 LESSON → 经 RecordLessonNodeTool 写入

V2 改造：
- **不再由 C-Phase 创建点**——GP 已经在执行中创建了
- C-Phase 的单轮 LLM 调用改为**审核+补全**模式：
  1. 读取本轮 GP 创建的新点（source='GP'）
  2. 审核是否有重复/低质量点 → 标记或合并
  3. 从轨迹中补建边（RESOLVES/REQUIRES/TRIGGERS）
  4. 补深层线（source='C'）
- 产出上限：0-5 条补全操作（不是 0-10 条新点）

### 5.4 GP 和 C 的分工

| 动作 | GP（主要） | C（补全） |
|------|-----------|----------|
| record_line | ✅ 实时连线（推理副产品） | ✅ 事后补深层线 |
| record_point | ✅ 发现即记录（**主要产出源**） | ❌ 不再创建点 |
| 建边（RESOLVES等） | ❌ 不做 | ✅ 事后补建 |
| 语义去重 | 自动（向量≥0.85合并） | ✅ 审核+合并 |
| VOID 升格 | ❌ 不做 | ✅ 发现实证时升格 |

---

## 六、数据模型

### 6.1 points 表（替代 knowledge_nodes 的 LESSON/CONTEXT 行）

```sql
-- 复用现有 knowledge_nodes 表，type 值扩展
-- LESSON → POINT (type='POINT')
-- CONTEXT → POINT (type='CONTEXT')
-- 旧 LESSON_XXX ID 兼容保留

-- 变化：
-- 1. 新节点 ID 格式: P_{short_hash}
-- 2. trigger_verb/noun/context 字段不再填写（保留列，不删，向后兼容）
-- 3. because_reason 不再填写 → 走线
-- 4. action_steps 不再拆分 → 走 content
-- 5. reasoning_basis 不再填写 → 走 record_line
```

### 6.2 lines 表（已存在 reasoning_lines）

```sql
-- 现有 reasoning_lines 实际 schema（manager.py:295）:
--   line_id        TEXT PRIMARY KEY
--   new_point_id   TEXT NOT NULL      ← 新点（= from端）
--   basis_point_id TEXT NOT NULL      ← 被参考的旧点（= to端）
--   reasoning      TEXT NOT NULL      ← 因果说明（= why）
--   trace_id       TEXT               ← 来源trace
--   round_seq      INTEGER DEFAULT 0  ← 轮次序号
--   created_at     TIMESTAMP

-- V2 需新增的列：
ALTER TABLE reasoning_lines ADD COLUMN source TEXT DEFAULT 'C';
-- source: 'GP' | 'C'  ← 区分线的来源

-- V2 变化：
-- 1. GP 独立调用 record_line 写入（source='GP'），不再依赖 record_lesson_node
-- 2. new_point_id 允许虚拟标记（INSIGHT_{trace_id}_{seq}），后续 record_point 时关联
-- 3. 入线数 = COUNT(*) WHERE basis_point_id = X，GP不可见
-- 4. 现有7条线全为 C-Phase 产出（source='C'），新线将混合 GP+C
```

### 6.3 edges 表（实际名 node_edges，不变）

```sql
-- 现有 node_edges 实际 schema（manager.py:231）:
--   source_id  TEXT NOT NULL
--   target_id  TEXT NOT NULL
--   relation   TEXT NOT NULL    ← RESOLVES / REQUIRES / TRIGGERS / CONTRADICTS / RELATED_TO
--   weight     REAL DEFAULT 1.0
--   created_at TIMESTAMP
--   PRIMARY KEY (source_id, target_id, relation)
--   FOREIGN KEY (source_id) REFERENCES knowledge_nodes(node_id)
--   FOREIGN KEY (target_id) REFERENCES knowledge_nodes(node_id)

-- C-Phase 事后补建，GP 不直接操作
-- 注意：record_point 的 resolves 参数 → 自动创建 RESOLVES 边
--       需确保新 P_xxx 节点的外键约束满足（P_xxx 必须先存在于 knowledge_nodes）
```

### 6.4 面的扩散通道

```
面沿 lines + edges 双通道扩散（已决策保留）：
1. lines（reasoning_lines）— 因果链，最密集，能发现边未覆盖的邻居
2. 强边（RESOLVES/REQUIRES/TRIGGERS）— 结构性关系
3. 弱边（RELATED_TO）— 语义关联

面呈现时不暴露因果（why字段），只呈现拓扑。
```

---

## 七、迁移策略

### 7.1 向后兼容

- 旧 LESSON_XXX / CTX_XXX 节点 ID 全部保留，不重命名
- `record_point` 创建的新节点用 P_xxx 格式
- `record_line` 的 to_id 同时接受 P_xxx 和 LESSON_XXX
- 旧节点的 trigger_verb/noun/context 字段保留（不删列），新节点不填

### 7.2 渐进切换

| 阶段 | 动作 | 风险 |
|------|------|------|
| Phase A | 新增 record_point + record_line 工具，GP 可用 | 低（增量） |
| Phase A.1 | auto_mode.py gp_unblock_tools 改为 `["record_point", "record_line"]` | 低（配置） |
| Phase A.2 | loop.py 知识路径提醒改为 `record_line` + `record_point` | 低（文案） |
| Phase B | GP prompt 引导用 record_point 替代 record_lesson_node | 中（行为变化） |
| Phase C | record_lesson_node 降级为 C-Phase 专用 | 低（GP已不调） |
| Phase D | 旧 LESSON 节点的 trigger 字段不再用于搜索排序 | 中（搜索质量） |
| Phase E | 入线数替代 confidence 作为价值信号 | 高（需样本积累） |

### 7.3 不改的部分

- **搜索管线**（向量→LIKE→签名→精排）不改——这是找种子点的手段
- **Arena 机制**保留——入线数和 Arena 是两个维度（推导价值 vs 执行质量）
- **edges 表**不变——RESOLVES等边仍然由C-Phase建
- **expand_surface BFS**不变——只是扩散通道加了lines

---

## 八、验证标准

V2 成功的标志：

1. **GP 连线数 > 0**：record_line 被 GP 主动调用（当前=0）
2. **GP 记录点数 > 0**：record_point 被 GP 主动调用（当前 record_lesson_node GP调用=0）
3. **线的实时性**：GP 连线发生在搜索命中后1-2轮内（不是C-Phase事后补）
4. **入线数分布**：有入线数的节点 > 10%（当前=0%，因为线全来自C-Phase）
5. **工具摩擦对等**：record_point/record_line 的调用频率与 shell 同量级

---

## 九、开放问题

1. ~~**record_line 的虚拟标记生命周期**~~ — 已决策：INSIGHT_ 标记保留，不 GC。
   - INSIGHT_ 线对入线数有贡献（"有人觉得这节点有用"），GC 会丢信号
   - BFS 中 INSIGHT_ 节点是死胡同（knowledge_nodes 中不存在），无害
   - 防御：expand_surface 加 `WHERE new_point_id IN (SELECT node_id FROM knowledge_nodes)` 过滤，避免 JOIN 崩溃
   - 可选 housekeeping：>7天未关联的 INSIGHT_ 线清理
2. ~~**面扩散中 lines vs edges 的权重**~~ — 已决策：保留沿线+边扩散
3. **新节点签名推断质量** — 需 MVP 验证。
   - 旧节点：trigger_verb/noun/context 注入 metadata_signature → 签名维度丰富
   - 新节点：纯自然语言推断 → 可能维度覆盖率略低
   - freshness bonus（≤7d=+2.0）补偿短期偏见，但7天后归零
   - **如果验证发现差距**：record_point 加可选 `keywords` 参数，让 GP 补充关键标记词
   - **如果验证等价**：可完全关闭
4. ~~**C-Phase 是否仍用 record_lesson_node**~~ — 已决策：C-Phase 不再创建点，改为审核+补全角色
5. ~~**node_edges 外键约束**~~ — 伪问题：record_point 先建节点再建边，语义去重合并时返回实际 node_id，FK 自然满足
6. ~~**knowledge_nodes 表无 trigger_verb/noun/context 列**~~ — 已验证事实，不是问题
7. ~~**线相似度去重**~~ — 低优先级，MVP 不需要。线相似度是点去重的辅助信号（非独立机制），当前内容语义去重（≥0.85合并）已覆盖
8. ~~**面呈现中线标注格式**~~ — 不标注数字（违反"GP从拓扑感受价值"原则）。可选定性标签（"推理活跃"≥3入线），实现细节，不影响架构

---

## 十、代码验证记录

> 逐点对照代码实际，修正设计文档中的偏差。

### 10.1 数据模型验证

| 设计文档描述 | 代码实际 | 修正 |
|-------------|---------|------|
| edges 表 | 实际名 `node_edges`（manager.py:231） | ✅ 已修正 §6.3 |
| reasoning_lines 列名 from_node_id/to_node_id | 实际名 `new_point_id`/`basis_point_id`（manager.py:296-298） | ✅ 已修正 §6.2 |
| reasoning_lines 无 source 列 | 确认无 source 列，需 ALTER TABLE ADD | ✅ 已补充 |
| knowledge_nodes 有 trigger_verb/noun/context 列 | **不存在**——这些是 RecordLessonNodeTool 的参数，存入 metadata_signature JSON | ✅ 已补充 §10.3 |
| node_content 表名 | 实际名 `node_contents`（复数） | ✅ 已修正 §6.1 |

### 10.2 工具机制验证

| 设计点 | 代码实际 | 状态 |
|--------|---------|------|
| GP_BLOCKED_TOOLS 包含 record_lesson_node | ✅ loop.py:47-50 确认 | 设计正确 |
| gp_unblock_tools 解禁机制 | ✅ auto_mode.py:2539 解禁 record_lesson_node + record_context_node | 需同步解禁 record_point + record_line |
| record_lesson_node 有 validateInput | ✅ node_tools.py 中 reasoning_basis 为空时返回错误 | record_line 也应加 validateInput |
| expand_surface 已实现 | ✅ manager.py:643 BFS 扩散 | ⚠️ 沿 reasoning_lines + node_edges，与"面不需要因果"矛盾 |
| 面扩散 60% 预算切换 | ✅ manager.py:708 `context_budget * 0.6` | 设计正确 |

### 10.3 expand_surface 代码与设计原则的矛盾

**设计原则**（point_line_surface.md L30, L56）：面不需要因果关系，只需要知道"有什么"。

**代码实际**（manager.py:685-697）：面同时沿 reasoning_lines（因果链）和 node_edges（拓扑边）扩散。

**分析**：
- 线比边更密集（每个新点至少有1条线，但不一定有边），沿线扩散能发现更多邻居
- 面的"不需要因果"更准确的理解是：**面呈现时不暴露因果**，而非**扩散时不走因果路径**
- 建议：保留沿线扩散，但在面呈现给 GP 时不显示线的 why 内容

### 10.4 关键发现：trigger 字段不在表中

RecordLessonNodeTool 的 `trigger_verb`/`trigger_noun`/`trigger_context`/`action_steps`/`because_reason`/`prerequisites`/`resolves` 是**工具参数**，不是 knowledge_nodes 表的列。

它们的去向：
- `action_steps`/`because_reason` → 拼接为 `full_content` 存入 `node_contents` 表
- `trigger_verb`/`trigger_noun`/`trigger_context` → 存入 `metadata_signature` JSON（manager.py:978 `bind_environment_signature`）
- `resolves`/`prerequisites` → 存入 knowledge_nodes 的 `resolves`/`prerequisites` TEXT 列

V2 的 record_point 只需传 title + content + resolves(可选)，内部：
- title + content → knowledge_nodes.title + node_contents.full_content
- resolves → knowledge_nodes.resolves + 自动建 RESOLVES 边
- metadata_signature 仍由 `bind_environment_signature` 自动生成（不需要 GP 填 trigger 字段）

### 10.5 epistemic_status 状态

代码中 `epistemic_status` 列存在（manager.py:173），但 backfill 已被注释掉（L185: "backfill removed"），且 `create_node` 中该参数被标记为 "kept for API compat but ignored"（L973）。

→ V2 的 POINT 模型中 epistemic 字段可以保留列但暂不激活，等 Arena 信号足够后再启用。

---

## 十一、外部研究补充

### 11.1 "Less is More" 定律（arxiv 2411.15399）

**核心发现**：给 LLM 提供更少、更相关的工具，准确率显著提升。
- Llama3.1-8b 面对 46 个工具时选错工具；减到 19 个时成功完成
- 减少工具数量 → 减少 LLM 的决策空间 → 更准确的工具选择

**对 V2 的启示**：
- 当前 GP_BLOCKED_TOOLS 有 8 个工具（loop.py:47-50），解禁后 GP 看到 record_lesson_node + record_context_node
- V2 应只解禁 record_point + record_line（2个），不解禁 record_context_point（低频，C-Phase 可代劳）
- 更少的工具 = 更高的调用概率

### 11.2 工具设计最佳实践（Statsig/OpenAI 社区）

| 原则 | V2 对应 |
|------|--------|
| "Fewer knobs; clearer choices" | record_point 2必填 vs record_lesson_node 8必填 |
| "Name tools with intent" | record_line 名字直接表达动作（画线） |
| "Prefer natural identifiers over opaque ids" | record_line 的 to_id 用搜索结果中的节点ID（GP 已知） |
| "Keep outputs tight and helpful" | record_point 返回新节点ID + 去重结果，不返回内部细节 |
| "Ship a thin tool with one crisp example" | record_line description 含示例场景 |
| "Require a one-line reason before tool call" | record_line 的 why 参数 = 内置的理由要求 |

### 11.3 CC validateInput 模式（claude code yuanma 验证）

CC 的 `validateInput()` 在工具执行前校验，错误返回给模型重试：
- GrepTool: 校验 path 存在性
- WebSearchTool: 校验 query 非空
- 返回 `{ result: false, message: "具体错误" }` → 模型看到后重试

**V2 应用**：
- record_line: 如果 to_id 不存在于 knowledge_nodes → 返回 `[Recovery Hint] 节点 {to_id} 不存在。可用 search_knowledge_nodes 搜索正确ID。`
- record_point: 如果 content < 20 字符 → 返回 `内容太短，请补充更多细节。`
- 错误消息应**引导恢复**（KAMI: Recovery > Initial Correctness），不只报告失败

---

## §12 Directive 设计规范

Directive = 每轮 `/auto` 注入 GP prompt 的 `用户方向` 文本，决定 GP 本轮聚焦方向。

### 构造链

```
_get_auto_signals() → signals（DB 查询结果列表）
    ↓
_call_session_planner() → next_focus（LLM 判断）
    ↓ (planner 失败/未触发时)
_pick_focused_fallback() → round_focus（确定性解析）
    ↓ (consecutive_dry >= 3 时)
强制切换覆盖 → round_focus
```

### 设计原则

1. **描述任务，不嵌入 node_id**：Directive 应描述"验证什么知识/调查什么问题"，不嵌入 `LESSON_C_XXX` 等 node_id。Node_id 会导致 GP 定向搜索命中同一锥体 → 方向锁定。

2. **Signals 是列表，不是内容 dump**：`_get_auto_signals()` 只输出 `node_id: title`，不输出 `full_content`。详细内容由 GP 通过 `get_knowledge_node_content` 按需获取。Content_preview 中的 JSON 模板字段会被 fallback 解析器误捡为方向条目。

3. **去重**：已展示过的节点（`session_shown_nodes`）不再重复出现在 signals 中。展示过 = GP 已知 = 不需要再提醒。

4. **Planner 优先，fallback 兜底**：Planner 有 `round_log` 上下文，能判断是否该继续或切换。Fallback 是无状态的确定性解析器，不知道收敛状态。

5. **收敛检测覆盖 fallback**：当 `consecutive_dry >= 3`（连续多轮无持久产出），fallback 结果被强制切换覆盖。只覆盖 fallback，不覆盖 planner——planner 有足够上下文自行判断。

6. **Session 续跑状态隔离**：`last_planner_round` 和 `round_num` 是配对的 session 内部计数器。`round_num` 不恢复（新 session 从 1 开始），`last_planner_round` 也不恢复——否则差值永远为负，planner 永不触发。

### 反模式（已修复）

- ❌ `"优先验证并利用这条 C-Phase 新知识: LESSON_C_XXX: title"` — 嵌入 node_id + C-Phase 偏见
- ❌ signals 中包含 `content_preview[:500]` — JSON 碎片被 fallback 解析为方向条目
- ❌ LESSON_C_ section 无 `session_shown_nodes` 过滤 — 同一批节点每轮重复出现
- ❌ `last_planner_round` 从旧 session 恢复 — planner 永不触发
- ❌ fallback 无视 `consecutive_dry` — 产出性收敛（每轮 +新节点但方向不变）无法打破
