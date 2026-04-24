# 点线面与 Genesis 各部件适应分析

> 基于 point_line_surface.md 纲领，逐部件分析冲击与改造路径

---

## 1. search_tool.py（搜索工具）

### 现状
向量粗排 → LIKE匹配 → 签名门控 → Cross-Encoder精排 → 分数融合 → Graph Walk → 凝实度摘要

### 冲击
- **凝实度摘要** → 被 `expand_surface` 替代
- **fusion_score 数字** → 面的拓扑呈现替代，但搜索排序本身仍需分数
- **confidence 显示** → GP不再看到数字，看到网络拓扑

### 改造路径
- 搜索排序逻辑（向量+LIKE+签名+精排）**不改**——这是"找种子点"的手段
- 搜索结果输出：去掉凝实度摘要，返回种子点ID列表给 `expand_surface`
- `fusion_score` 内部仍可用于排序，但不暴露给GP

### 注意
- `_record_search_void()` 搜索未命中记录VOID → 保留，面也需要空洞信息

---

## 2. knowledge_query.py（Knowledge Map / L1 Digest）

### 现状
`get_digest()` 按类型计数 + 战绩Top节点 + 未使用节点 + VOID缺口

### 冲击
- L1 Digest 是分类+数字的呈现方式 → 面替代后变成面的入口
- `build_reliability_profile()` 数字评分（confidence×6.0 + freshness + tier_bonus）→ 入线数替代

### 改造路径
- L1 Digest → 面的摘要呈现："provider面: 3锚区2空洞, 超时面: 2锚区1空洞"
- `get_digest()` 被 `build_gp_prompt()` 的 `knowledge_map` 参数使用 → 改了digest就改了GP的system prompt

### 注意
- 这是GP每次请求都看到的，改了直接影响GP行为
- `build_reliability_profile()` 被 search_tool.py 调用用于排序，不能直接删

---

## 3. arena_mixin.py（Arena置信度）

### 现状
`effective_confidence()` = 使用战绩(0.5~0.9) + 验证来源梯度 + tier基础值

### 冲击
**最大的冲突点**。Arena的整个设计哲学是"质量信号来自使用战绩"——这是数字评分。点线面说"数字不靠谱，入线数才是价值信号"。

### 两个维度不矛盾
- **Arena** = 这个知识**用起来**成不成功（执行信号）
- **入线数** = 这个知识**被参考**来产生新知识的次数（推导信号）
- 两者共存：Arena管执行质量，入线数管推导价值

### 改造路径
- `effective_confidence()` 被5+处调用（knowledge_query.py、loop.py、blackboard.py等），不能直接删
- 短期：保留Arena，GP呈现中不再显示confidence数字
- 中期：入线数作为补充价值信号，与Arena共存
- 长期：根据MVP样本决定Arena是否降级

### 注意
- Arena的boost/decay机制（任务成功→boost，失败→decay）仍然有用于执行质量判断
- 不应让GP看到confidence数字，但后台仍可用

---

## 4. node_tools.py（RecordLessonNodeTool）

### 现状
写LESSON时自动语义去重（0.85→merge, 0.65→relate），tags硬编码"auto_managed"

### 冲击
- 语义去重（内容相似度0.85阈值）→ 未来补充线相似度去重
- 写LESSON时不记录线 → 需要新增线的采集

### 改造路径
- RecordLessonNodeTool 是线的**自然接入点**——写LESSON时顺便采线
- 线的采集方式未定（提示词/工具），但无论哪种，最终都通过此工具或类似工具写入线表
- `RESOLVES` 边（强边，2-hop遍历用）→ 这是现有的"推导链"雏形，但不是LLM判断的线

### 注意
- 线表独立于edges表，RESOLVES边不等于线
- tags硬编码"auto_managed"问题仍需解决（如果线需要自定义tags）

---

## 5. prompt_factory.py（GP System Prompt）

### 现状
`[L1 Knowledge]` 块注入knowledge_map，显示"eff越高越可信"

### 冲击
- "eff 越高越可信" → 面替代后不再有eff数字
- L1 Knowledge块 → 变成面的呈现

### 改造路径
- `[L1 Knowledge]` → `[知识地形]` 或类似，展示面的拓扑而非数字
- 去掉所有数字评分的呈现（eff、confidence、density）
- 保留面的拓扑信息：锚区、边界、空洞

### 注意
- 这是GP每次请求都看到的system prompt，改了直接改变GP行为
- 需要MVP验证面的呈现格式对GP行为的影响

---

## 6. loop.py（知识路由层）

### 现状
`_apply_knowledge_routing()` 游标+话题漂移检测，注入上轮活跃节点

### 冲击
- 路由层注入的是具体节点，面注入的是拓扑网络
- 两者可能重叠：路由注入的节点应该是面的种子点之一

### 改造路径
- 路由层（搜索前预加载）→ 提供种子点给面
- 面（搜索后处理）→ 从种子点扩散
- 时序：路由先跑 → 面后跑，不冲突

### 注意
- `_apply_knowledge_routing()` 注入的节点ID列表可以作为面的种子点来源之一

---

## 7. background_daemon.py（守护进程）

### 现状
GC/Node Cleanup用confidence decay清理未使用节点

### 冲击
- confidence decay → 入线数替代：没有入线的节点优先清理

### 改造路径
- 短期：保留confidence decay，入线数作为补充清理信号
- 中期：入线数=0且confidence低的节点优先清理
- 长期：根据MVP样本决定是否完全切换到入线数

### 注意
- 入线数需要样本积累，初期不能只用入线数
- 守护进程是独立进程，改了清理逻辑要确保不影响主循环

---

## 改造优先级

| 优先级 | 部件 | 改动 | 风险 |
|---|---|---|---|
| P0 | 新建线表 | 独立表存储线的因果+数量 | 低（新增，不改现有） |
| P0 | expand_surface | BFS扩散+摸石头过河 | 中（替代凝实度摘要） |
| P1 | search_tool.py | 输出去掉凝实度，返回种子点 | 中（GP看到的内容变化） |
| P1 | prompt_factory.py | L1 Knowledge → 知识地形 | 高（直接影响GP行为） |
| P2 | node_tools.py | 线采集接入 | 低（增量改动） |
| P2 | knowledge_query.py | digest格式改面 | 中（被多处调用） |
| P3 | arena_mixin.py | confidence呈现降级 | 高（5+处调用） |
| P3 | background_daemon.py | 清理逻辑改入线数 | 低（独立进程） |

---

## 关键约束

1. **Arena不能直接删**——`effective_confidence()` 被5+处调用，入线数和Arena是两个维度，共存
2. **搜索排序不需要改**——搜索是找种子点，面是搜索后的呈现层
3. **RecordLessonNodeTool是线的自然接入点**——写LESSON时顺便采线
4. **L1 Digest → 面的呈现**——这是GP每次都看到的，改了直接改变GP行为
5. **守护进程清理逻辑**——confidence decay → 入线数，需要过渡期
6. **线表独立于edges表**——线和面是独立平台，方便后续调整可见性策略
