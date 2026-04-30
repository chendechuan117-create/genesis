# 点线面 — 工程实施记录

> 本文档是 `point_line_surface.md` 的实施附录，记录表结构、工具接口、实现状态和兼容字段。
> 权威概念定义在主文档，这里不重复。

---

## 当前代码现状（2026-04-28 更新）

### 已实现

| 组件 | 文件 | 状态 |
|---|---|---|
| reasoning_lines 表 + same_round/trace_id/round_seq | `v4/manager.py` | ✅ 入线数查询排除同轮线 |
| 低摩擦 point/line 工具 + 旧工具兼容 | `tools/node_tools.py` | ✅ record_point / record_line 为 GP 主入口 |
| auto_mode 工具暴露 | `auto_mode.py` | ✅ record_point / record_line 默认可见 |
| 入线数 + 角色标签 | `tools/search_tool.py` | ✅ 只显示基础/探索，不显示数字 |
| 碰撞检测 | `tools/node_tools.py` | ✅ find_collision_candidates，覆盖 record_lesson_node + record_line |
| 饱和标记（原虚点） | `v4/manager.py` + `search_tool.py` | ✅ is_virtual + 搜索过滤 + 饱和信号注入面 |
| 面两阶段组装 | `v4/surface.py` | ✅ 真替换（非追加），directional reasoning_lines |
| 旧架构清理 | `prompt_factory.py` + `search_tool.py` + `knowledge_query.py` | ✅ GP 可见数字评分→基础/探索/面状态 |
| 必要性消融 | `v4/manager.py` + `c_phase.py` + 全通道过滤 | ✅ ablation_active + 7通道过滤 |
| PLS 遗留机制修复（11项） | 多文件 | ✅ 入线数替代 confidence/win_rate |

### C-Phase 园丁模式

| C 的职责 | 机制 | 点线面角色 |
|---|---|---|
| Arena 成败反馈 | 环境信号→活跃节点胜率更新 | 互补信号 |
| Persona 学习 | Multi-G 人格胜率 | 独立系统 |
| Trace Pipeline | 执行流实体提取 | 独立系统 |
| 消融触发 | 入线数≥5→隐藏节点 | 必要性消融 |
| 矛盾检测 | LLM→CONTRADICTS边 | GP搜索可见 |
| 关联发现 | LLM→RELATED_TO边 | 面BFS跨锥体连接 |

### 未实现 / 远期

| 缺口 | 说明 | 优先级 |
|---|---|---|
| 线语义去重 | 2×2矩阵需推理链语义比较，当前碰撞检测=basis集合重叠=MVP | 远期 |
| 消融触发条件 | 设计要求三条件（入线数+idle rounds+面包含次级），实现只用了入线数≥5 | 低 |

### 实验性机制

| 机制 | 文件 | 说明 |
|---|---|---|
| 主动遗忘与置换 | `v4/manager.py` + `v4/c_phase.py` | ablation_active=3，触发条件极严格（入线≥8+HUMAN/REFLECTION+邻居≥5），实际几乎不触发。不属于 PLS 核心，属于高级维护策略。 |

### 冷启动

| 机制 | 文件 | 说明 |
|---|---|---|
| 概念地图种子 | `v4/concept_seeds.yaml` + `v4/manager.py` | `_ensure_concept_seeds()` 首次部署时注入 CONTEXT 种子节点，之后不再执行。不是 PLS 本体，是 bootstrap。 |

---

## 原稿差异与当前裁决

本节记录从原始概念草稿到当前实现的演化，避免把历史概念误读为当前 PLS 本体。

### 虚点 → 饱和标记

原稿设定：碰撞后由 LLM 判断重复并选择不写，系统再记录虚点。

当前实现：碰撞检测发现同一区域反复重叠后，系统创建/递增饱和标记（`is_virtual`）。这不是"该区域绝对无新知识"的判决，而是拓扑密度信号：该区域路径重叠频繁，继续探索的边际收益可能下降。

当前裁决：以"饱和标记"为主术语，"虚点"仅作为实现兼容名保留。

### 殊途同归

原稿 2×2 矩阵中包含：线不同、内容相似 = 殊途同归，代表独立推理路径收敛到相似结论。

当前实现未显式建模该信号。现有碰撞检测只用 basis 集合重叠做 MVP，无法区分"换皮重复"与"独立路径收敛"。

当前裁决：殊途同归保留为远期拓扑模式，不进入当前 PLS 核心三信号。未来可通过线语义比较、`RELATED_TO` 强化，或新增收敛关系表达。

### 园丁不种树

原稿原则：园丁修图，不种树。点的价值来自后续 GP 的跨轮引用；维护者直接生成的节点天然 0 入线，容易成为拓扑死点。

当前系统仍保留部分 C-Phase/反思型知识写入能力，属于兼容/遗留层，不是 PLS 本体。若 C 生成节点，它必须等待后续 GP 通过 reasoning_lines 重新引用，才真正进入 PLS 拓扑价值系统。

当前裁决：PLS 核心中，GP/探索者产生点和线；维护层负责加边、打标、消融、记录反馈。C 生成节点不得被视为已获得拓扑价值。

---

## 保留兼容（不删除）

| 字段 | 原因 |
|---|---|
| confidence_score | Arena/Evidence Assessor 内部使用，GP 不可见 |
| epistemic_status | schema 保留但 create_node 忽略，待清理 |
| IF/THEN/BECAUSE 模板 | LESSON 内容结构，与点线面不矛盾 |

---

## 表结构

### reasoning_lines

```sql
CREATE TABLE IF NOT EXISTS reasoning_lines (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    new_point_id TEXT NOT NULL,
    basis_point_id TEXT NOT NULL,
    reasoning TEXT,
    source TEXT DEFAULT 'GP',
    same_round INTEGER DEFAULT 0,
    trace_id TEXT,
    round_seq INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (new_point_id) REFERENCES knowledge_nodes(node_id),
    FOREIGN KEY (basis_point_id) REFERENCES knowledge_nodes(node_id)
)
CREATE INDEX IF NOT EXISTS idx_rl_basis ON reasoning_lines(basis_point_id)
CREATE INDEX IF NOT EXISTS idx_rl_new ON reasoning_lines(new_point_id)
CREATE INDEX IF NOT EXISTS idx_rl_trace_round ON reasoning_lines(trace_id, round_seq)
```

### knowledge_nodes 扩展字段

- `is_virtual INTEGER DEFAULT 0` — 饱和标记
- `ablation_active INTEGER DEFAULT 0` — 0=正常, 1=消融观察, 2=已降级, 3=主动修剪

---

## 工具接口

### record_point

写入轻量知识点（默认 LESSON），返回新点 ID。

### record_line

写入一条因果线，自动标记 same_round。连线后触发碰撞检测。

### record_lesson_node（兼容）

保留 `reasoning_basis` 兼容旧调用，内部仍写线，但 GP 默认优先使用 point/line 两步工具。

---

## 关键方法

| 方法 | 文件 | 用途 |
|---|---|---|
| `get_incoming_line_count` | `v4/manager.py` | 单节点入线数 |
| `get_incoming_line_counts_batch` | `v4/manager.py` | 批量入线数（避免 N+1） |
| `get_incoming_count_percentile` | `v4/manager.py` | 自适应阈值（P75） |
| `get_same_round_ids` | `v4/manager.py` | 同轮检测 |
| `find_collision_candidates` | `v4/manager.py` | 碰撞检测 |
| `ensure_virtual_point` | `v4/manager.py` | 饱和标记创建/递增 |
| `get_virtual_saturation` | `v4/manager.py` | 饱和信号查询 |
| `expand_surface` | `v4/surface.py` | 面两阶段组装 |
| `check_ablation_candidates` | `v4/manager.py` | 消融候选 |
| `activate_ablation / deactivate_ablation` | `v4/manager.py` | 消融激活/评估 |
| `check_proactive_pruning_candidates` | `v4/manager.py` | 主动修剪候选（实验性） |
| `activate_proactive_pruning / evaluate_proactive_pruning` | `v4/manager.py` | 主动修剪（实验性） |

---

## 消融全通道过滤

消融节点从所有 GP 可见通道统一隐藏：

- ✅ `search_tool.py`：搜索结果后处理过滤
- ✅ `v4/surface.py`：面组装 BFS 候选集排除
- ✅ `knowledge_query.get_digest()`：认知目录 SQL
- ✅ `knowledge_query.generate_map()`：知识地图 SQL
- ✅ `knowledge_query.generate_l1_digest()`：L1 摘要 SQL
- ✅ `auto_mode.py`：螺旋拓荒 session 信号
- ✅ `trace_query_tool.py`：recall 模式跨层引用

不需要过滤的后台通道：`c_phase.py`、`arena_mixin.py`、`network_health.py`、`node_cleanup.py`

---

## PLS 遗留机制修复记录（2026-04-22~28）

| # | 冲突点 | 文件 | 修复 |
|---|--------|------|------|
| 1 | 外部注意力控制 | `auto_mode.py` | 放宽阈值(5→8/2→3/3→4) + PLS 语言 |
| 2 | 数字泄露 q/sim/W/L | `loop.py` | 基础/探索拓扑角色标签 |
| 3 | fusion_score 数字路由 | `search_tool.py` | _topo_value 替代 _metric_score |
| 4 | conf*weight 坍缩 | `blackboard.py` | 入线数替代 eff_conf |
| 5 | win_rate 消融 | `manager.py` | 入线数+CONTRADICTS 替代 win_rate |
| 6 | 反思遗漏 record_point/line | `c_phase.py` | 加入提取和跳过列表 |
| 7 | ⚠️陷阱+eff_conf 排序 | `knowledge_query.py` | 入线数排序+矛盾标记 |
| 8 | node_id 字符串匹配 | `surface.py` | tags 匹配 |
| 9 | get_all_titles 废弃 | `manager.py` | 标记 DEPRECATED |
| 10 | eff_conf<0.2 预过滤 | `search_tool.py` | PLS 类型豁免 |
| 11 | VOID ORDER BY RANDOM() | `auto_mode.py` | created_at DESC 稳定分页 |
| — | network_health win_rate | `network_health.py` | CONTRADICTS 边替代 win_rate |
| — | manager 日志 KeyError | `manager.py` | has_contradiction 替代 win_rate |
