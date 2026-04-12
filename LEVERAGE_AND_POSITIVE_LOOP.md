# 杠杆思维与正循环：如何让 Genesis 越用越智能

> 2026-04-07 · 源自对话推导，非泛泛设想
>
> 核心问题：当前元信息只能"不犯同样的错"，如何升级为"主动找到更好的路"？

---

## 一、问题定义

### 1.1 现状：元信息 = 防御性记忆

Genesis 的元信息体系：

| 层 | 数据源 | 作用 | 局限 |
|---|---|---|---|
| 声明性 | NodeVault (1,464 LESSON) | "上次踩了这个坑" | 只记错误，不记效率 |
| 程序性 | Trace 网络 (14,249 实体, 22,682 关系) | "上次做了什么" | 只记事实，不记好坏 |
| 原始数据 | traces.db (32,070 tool calls, 2,950 sessions) | 每次工具调用的耗时/token | 有数据，无提炼 |

**覆盖面缺口（实测数据）**：

```
traces.db 知道：
  shell     → 18,720 次 / 1,127 sessions / 平均 2.3s
  web_search → 770 次 / 94 sessions / 平均 8.7s
  trace_query → 53 次 / 32 sessions / 平均 8ms  ← 几乎没人用

traces.db 不知道：
  "用 shell grep 做代码审查需要 15 轮，用专用工具只需 1 轮"
  "做 X 类任务时，工具 Y 效率最高"
  "这个 session 的效率和同类 session 比如何"
```

1,464 个 LESSON 中，~134 个涉及工具/方法，但内容是"这个工具有个坑"，不是"这个方法比那个快 10 倍"。

**一句话：Genesis 知道自己做过什么，不知道自己做得好不好，更不知道有没有更好的做法。**

### 1.2 目标："越用越智能"的定义

不是"犯过的错不再犯"（防御），而是：

> **每一次使用，都让 Genesis 更接近"用最短路径解决问题"的能力。**

"最短路径"= 杠杆解。找到一个方法，用极小代价产出极大效果。

---

## 二、推导过程（排除的方案及原因）

### 2.1 工具评分 ❌ → 自证悖论

初始想法：给每个工具一个"杠杆分"，高分工具优先使用。

**为什么不行**：如果 LLM 已经知道哪个工具更好，它就会用那个工具——不需要评分。如果它不知道，评分从何而来？系统给自己打分，本质上是在自己的圈里打转。

### 2.2 费力感信号（prediction error） ❌ → 鸡生蛋

改进想法：不评分，而是检测"预期 vs 实际"的效率差距。比如"这轮花了 45,000 token，同类任务历史均值 8,000"。

**为什么不行**：
1. "同类任务"的基线从自己的历史来——如果一直在降级模式下工作，降级就是基线，检测不到异常
2. Genesis 已经有类似信号（consecutive_dry, token_efficiency_degradation），但仍不做杠杆思维
3. **信号存在 ≠ 正确响应**——当前对信号的响应是"重试/换话题/放弃"，不是"审查自己的方法"

### 2.3 方案权衡（enumerate → compare → pick） ❌ → 回声室

再改进：让 GP 在执行前列出所有方案，比较后选最优。

**为什么不行**：还是同一个 LLM 在做判断。如果它能列出更好的方案并选中它，它一开始就会那么做。让它"列出方案"只是把同一个认知过程拆成了显式步骤，不增加新信息。

**根本原因**：LLM 会顺着当前路径走——跟人对话时顺着人的偏见（sycophancy），自己跑时顺着自己的偏见（echo chamber）。我（Cascade）在这次对话中被 Meadows 的"反馈回路"概念带偏，就是活生生的例子。

### 2.4 自我反省 ❌ → 问题从"人+LLM 回声"变成"LLM 自己的回声"

让 GP 反省自己？Auto 模式的 Session Planner 已经在做。但：

> 你让它反省自己，它只会在自己的框架里打转。问题从人跟 LLM 的回声，变成 LLM 自己的回声。

自我反省的极限 ≈ 歌德尔不完备：系统不能发现自己的盲区。

---

## 三、核心洞察

### 3.1 元信息是杠杆的载体，不是反馈才提升的

关键区分：

- ❌ 杠杆 = 检测到低效 → 修复（反馈驱动，被动）
- ✅ 杠杆 = 从已知信息中发现"有没有更短的路"（元信息驱动，主动）

类比：走路的人会考虑其他交通工具，不是因为某个信号告诉他"你走得太慢了"，而是因为他**知道有其他选项**，并且**会权衡利弊**。

Genesis 缺的不是信号，是**权衡**。但权衡不能由同一个 LLM 做（2.3 已排除）。

### 3.2 打破回声需要第二视角

**实证**：这次对话中，打破我的 Meadows 回声的不是任何信号或自我反省，而是用户从外部指出"你也犯了这个错误"。

用户能做到这一点，因为：
1. 看到了相同的元信息（我做了什么）
2. 但从不同的视角审视（不在我的执行循环里）
3. 问了一个我不会问自己的问题（"你为什么不修 GitNexus？"）

### 3.3 "大胆假设"必须有地基

第二视角不能凭空假设——如果它假设"删掉硬盘最省事"，就完蛋了。

**"大胆假设"= 基于元信息的假设。** 元信息是来时路，假设是"这条路上有没有捷径"。假设的素材来自真实数据，不来自幻想。

---

## 四、当前的缺口

要实现"第二视角基于元信息找捷径"，需要元信息具备"方法效率"维度。当前缺这个。

### 4.1 有的

- 每次工具调用的名称、耗时、token 消耗（traces.db spans 表）
- 每个 session 的总轮数、总 token（traces.db traces 表）
- 工具被哪些 session 使用过、使用了多少次（entity_occurrences 表）
- 实体间的 CO_OCCURS / DIAGNOSED_BY 关系

### 4.2 缺的

- **任务类型标签**：无法区分"代码审查 session"和"网络调试 session"
- **方法效率对比**：无"同类任务中，方法 A vs 方法 B 的效率差异"
- **路径模式识别**：无"高效 session 的共同工具使用模式 vs 低效 session 的模式"
- **工具适用场景**："search_knowledge_nodes 在什么场景下比 shell+sqlite3 更高效"

### 4.3 元信息的正循环应该是什么样

```
Session 执行（产出 trace 数据）
    ↓
C-Phase 并发：
  ├─ Knowledge Extraction（声明性知识：LESSON）   ← 已有
  ├─ Trace Pipeline（程序性知识：实体/关系）       ← 已有
  └─ Challenger Review（方法效率知识：路径审查）   ← 新增
    ↓
下次执行时，GP 搜索知识 → Knowledge Map 展示 METHOD_REVIEW
    ↓
GP 自主决定是否采纳建议
    ↓
新 session 的 trace 数据验证（或否定）建议
    ↓
Challenger 在新 session 的 C-Phase 再审查 → 加固或修正
    ↓
正循环
```

---

## 五、Challenger 设计方案

> 状态：架构已定，prompt 待打磨

### 5.1 定位

| | Knowledge Extraction（已有） | Challenger（新增） |
|---|---|---|
| **问的问题** | "这次执行中学到了什么？" | "这次执行的路径是最短的吗？" |
| **产出类型** | LESSON（事实/教训） | METHOD_REVIEW（方法效率建议） |
| **价值** | 防御性（不犯同样的错） | 进攻性（找到更好的路） |

两者互补，不替代。C-Phase 负责知识提炼，Challenger 负责路径审查。

### 5.2 架构

```
C-Phase（后台 asyncio.create_task，不阻塞用户）
    │
    ├─ Knowledge Arena（确定性，零 LLM）
    ├─ Trace Pipeline（确定性，零 LLM）
    │
    └─ asyncio.gather:
        ├─ _run_knowledge_extraction()    ← 已有
        └─ _run_challenger_review()       ← 新增
```

- 与 Knowledge Extraction 完全并发，墙钟时间不增加
- 输入共享（`_build_reflection_summary` + 额外效率指标）
- 输出独立写入 NodeVault

### 5.3 输入数据

Challenger 需要看到的数据（防止泛泛而谈的关键）：

| 数据 | 来源 | 作用 |
|---|---|---|
| **工具调用分布** | traces.db spans 表 | "shell × 12, read_file × 3, search_knowledge_nodes × 0" → 具体数字防空话 |
| **总轮数 + 总 token** | traces.db traces 表 | 效率的量化基准 |
| **重试/失败模式** | `_op_tool_outcomes` | "shell 连续失败 4 次后换了 read_file" → 低效模式识别 |
| **GP 可用工具完整列表** | ToolRegistry | 只能从实际存在的工具中建议，防编造 |
| **已有 Tool Preference Map** | prompt_factory | "以下已是已知规则，不要重复" → 防复述 |
| **最近相关 METHOD_REVIEW** | NodeVault | 防重复建议 |
| **用户请求 + GP 最终回复** | g_messages | 理解任务上下文 |

其中**工具调用分布**和**可用工具列表**是核心——没有这两个，Challenger 无法做有地基的对比。

### 5.4 Prompt（草案，待打磨）

> ⚠️ 以下为初稿。Genesis 历史上 prompt 问题多次（C-Phase 30 轮循环、auto 模式禁令、模板填充），
> 此 prompt 需要在实际运行中迭代验证。

**已识别的 prompt 风险及对策**：

| 风险 | 表现 | 对策 |
|---|---|---|
| 讨好（sycophancy） | "执行得很好" | 明确 PASS 是合法输出，不需要夸奖 |
| 复述已有规则 | 重复 Tool Preference Map | 输入中包含已有规则，prompt 要求"不要重复" |
| 泛泛建议 | "应该提高效率" | 要求具体到工具名 + 数字 |
| 编造工具 | "应该用 XYZ 工具" | 输入中包含可用工具列表，prompt 要求"只从列表中选" |

```
System: 你是路径审查者。你的唯一任务是审查执行路径的效率。

User:
以下是一次任务执行的完整数据。

[任务] {user_request}
[GP回复] {gp_final_response_snippet}

[工具调用分布]
{tool_call_histogram}  // e.g. shell: 12次, read_file: 3次, search_knowledge_nodes: 0次

[效率指标]
总轮数: {rounds}, 总 token: {total_tokens}

[失败/重试模式]
{failure_patterns}  // e.g. shell 连续失败 4 次

[GP 可用工具列表]
{available_tools_with_descriptions}

[已有效率规则（不要重复这些）]
{existing_tool_preference_rules}
{existing_method_reviews}

---

审查要求：
1. 这个执行路径有没有明显低效？具体到工具名和次数。
2. 可用工具列表中，有没有更适合的工具没被使用？
3. 如果你来做同样的任务，具体会怎么做？

输出格式：
- 如果路径已足够高效，只输出 "PASS"
- 如果有建议，输出 JSON:
  {"pattern":"任务模式简述",
   "inefficiency":"具体低效描述（含数字）",
   "suggestion":"具体替代方案（含工具名）",
   "expected_improvement":"预期改善（如：从12轮→2轮）"}
- 不要泛泛而谈。没有数字支撑的建议 = 无效建议。
```

### 5.5 输出处理

**PASS** → 不写入任何东西。零噪音。

**有建议** → 写入 NodeVault 为 LESSON 节点，额外标记：
- `source: challenger`（区分于 C-Phase extraction 产出的 `source: reflection`）
- `type: LESSON`（复用现有类型，不新增）
- `tags: ["method_review", "{task_pattern}"]`
- 经过 RecordLessonNodeTool 的语义去重（≥0.85 合并，≥0.65 建边）

### 5.6 正循环闭合

```
Session N:
  GP 用 shell grep 做代码搜索，花了 12 轮
  → Challenger: "trace_query recall 可以 1 轮完成" → 写入 METHOD_REVIEW

Session N+1:
  GP 搜索知识时在 Knowledge Map 看到 METHOD_REVIEW
  → GP 决定试试 trace_query → 花了 2 轮完成
  → Challenger: "GP 采纳了上次建议，12轮→2轮，建议有效" → PASS（或加固）

Session N+2:
  GP 遇到类似任务 → 自然使用 trace_query（已内化为习惯）
  → Challenger: PASS
```

关键：**Challenger 不强制 GP 改变**。它只产出知识，GP 通过 Knowledge Map 自然发现。
采纳与否由 GP 决定。正循环靠**知识的自然流动**驱动，不靠指令。

### 5.7 边界（防虚无主义/完美主义）

1. **只审查已完成的 session** — 不干预正在执行的 GP
2. **PASS 是一等公民** — 不是每个 session 都需要优化。强制找问题 = 噪音
3. **建议必须有数字** — prompt 明确"没有数字支撑的建议 = 无效"
4. **产出是知识，不是指令** — GP 自主决定是否采纳
5. **不回溯质疑任务本身** — Challenger 审查"怎么做"，不审查"该不该做"

### 5.8 成本

| 组件 | Token / session | 说明 |
|---|---|---|
| Knowledge Extraction（已有） | ~800 | 不变 |
| Challenger Review（新增） | ~800 | 与 Extraction 并发，不增加墙钟时间 |
| C-Phase 总 LLM 成本 | ~1,600 | GP 本身 5 万~100 万 token，1,600 可忽略 |

### 5.9 待打磨

- [ ] Prompt 实际运行验证：PASS 率是否合理（太低 = 讨好，太高 = 无发现）
- [ ] METHOD_REVIEW 在 Knowledge Map 中的展示方式
- [ ] 是否需要 SKIP 条件（如 session 只有 1 轮工具调用，无需审查）
- [ ] 长期：METHOD_REVIEW 积累后，能否做 pre-execution 路径预判

---

## 六、元信息 ROI 实验设计

> 2026-04-08 · 目标：用数据推导出最优搜索预算公式，而非拍脑袋

### 6.1 核心思路

给 GP 随机搜索预算（1~5），每次搜索时采集 novelty 数据，跨 session 积累后推导经验公式。

**前提条件**：vault 中的知识质量必须达到基线标准。如果 C-Phase 产出以垃圾为主，实验测的是"搜垃圾的 ROI"而非"元信息的 ROI"。

### 6.2 采集 schema

```sql
-- 每次搜索记一行
CREATE TABLE IF NOT EXISTS search_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    round_id INTEGER DEFAULT 0,        -- auto 模式的轮次，chat 为 0
    search_seq INTEGER NOT NULL,       -- 本轮第几次搜索
    budget INTEGER NOT NULL,           -- 本轮随机分配的预算
    query_text TEXT,                   -- 搜索 query
    result_count INTEGER,              -- 返回节点数
    new_node_count INTEGER,            -- 上下文中未出现的节点数
    new_node_ids TEXT,                 -- JSON 列表
    avg_novelty REAL,                  -- 新节点与已有上下文的平均向量距离
    avg_confidence REAL,               -- 返回节点的平均置信度
    cone_density TEXT,                 -- 搜索时的凝实度判定
    preloaded_count INTEGER,           -- knowledge routing 预加载的节点数
    vault_size INTEGER,                -- 当前 vault 总节点数
    model TEXT,                        -- LLM 模型
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- session/round 结束后回填
CREATE TABLE IF NOT EXISTS search_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    round_id INTEGER DEFAULT 0,
    budget INTEGER,
    searches_used INTEGER,             -- 实际搜索次数（可能 < budget）
    nodes_used_count INTEGER,          -- 搜到的节点中被 GP 实际使用的
    nodes_used_ratio REAL,             -- 使用率
    task_success INTEGER,              -- 0/1 或评分
    total_tool_calls INTEGER,
    total_tokens INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.3 需要控制的混淆变量

| 变量 | 为什么重要 | 采集方式 |
|---|---|---|
| knowledge routing 质量 | 搜索价值是 routing 之上的增量 | preloaded_count |
| 预算改变搜索行为 | budget=1 时 query 可能更精准 | 对比不同 budget 下的 per-search novelty |
| vault 质量 | 垃圾 vault → 搜索无价值（伪结论） | avg_confidence, 按质量分层分析 |
| 圆锥凝实度 | 高凝实 topic 搜索边际价值低 | cone_density |
| 任务难度 | 难任务搜多但也失败多 | cone_density 作代理 |
| 跨轮依赖 | Auto 模式各轮不独立 | session_id + round_id 分组 |
| Novelty ≠ 价值 | 向量远可能是噪音 | 区分 "搜到且用" vs "搜到未用" |

### 6.4 预期产出

30-50 session 后可分析：
- **边际 novelty 曲线**：`avg_novelty(search_seq)` 拐点 = 搜索有效上限
- **预算-使用率关系**：budget 越大 → nodes_used_ratio 是否下降
- **凝实度交互**：高凝实 topic 最优 budget < 低凝实
- **约束效应**：budget=1 时 per-search novelty 是否 > budget=5

最终公式形如：`optimal_budget = clip(base - α×cone_density + β×task_novelty, 1, max)`

### 6.5 前置条件 ⚠️

在启动实验前必须确认：
- [ ] C-Phase 产出的知识质量达到基线（非垃圾为主）
- [ ] SearchKnowledgeNodesTool 已注册
- [ ] search 工具内置预算机制和 novelty 采集逻辑
- [ ] vault 中的垃圾节点已清理或标记

---

## 附录：关键对话片段

> **用户**："genesis是不是缺乏一个追求杠杆解的能力？"
>
> **用户**："你也犯了这个错误。在这次对话里，gitnexus多次出问题，你不也是没想着解决。"
>
> **用户**："这是不是回到了鸡生蛋还是蛋生鸡？你的解法更像是给工具评分，本质上还是在自己的圈里打转。"
>
> **用户**："元信息是杠杆的最好载体。杠杆不是反馈才提升的。Meadows 之于 LLM，更像是提升注意力。"
>
> **用户**："如果LLM知道哪个选项比较好，它就不会选择其他选项。元信息作为起点跟终点的连线，杠杆解应该是，有没有缩短起点跟终点的法子？"
>
> **用户**："现在的元信息，只能说是，不犯同样的错。"
