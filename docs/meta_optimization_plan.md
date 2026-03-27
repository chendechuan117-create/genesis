# Genesis 元信息优化计划书（数据驱动修正版）

> 初版：2026-03-25（"神经系统"隐喻版，已废弃）
> 修正版：2026-03-26（基于 KB 诊断数据，故障驱动）
> 状态：Phase A/B/C 已完成

---

## 方向修正记录

初版计划基于"神经系统"隐喻设计优化方向。经过 KB 诊断后发现：隐喻驱动架构是错的，应该由**实际故障**驱动。

### 关键诊断数据（2026-03-26）

| 指标 | 数值 | 判断 |
|---|---|---|
| 总节点（清理前） | 1328 | — |
| VOID 节点 | 394 (30%) | 🔴 全部零升格，黑洞 |
| FERMENTED 假设 | 69 | 🔴 零使用率，废品 |
| Arena 胜率 | 98.5% | 🟡 信号太弱 |
| 节点使用率 | 40% | 🟡 60% 从未使用 |
| LESSON 使用率 | 60.7% | 🟢 核心价值来源 |
| Persona 分化 | 全部 ~97% | 🟡 无差异 |

### 废弃的方向
- ~~Phase 1: 图谱边激活~~（边不是瓶颈，60%节点搜都搜不到）
- ~~Phase 3: 领域感知新鲜度~~（所有节点都在7天内，freshness=fresh，改了没区别）
- ~~Phase 4: fusion 自适应~~（Arena 98.5% 胜率，信号全是噪音）

---

## Phase A：VOID 分离 ✅ 已完成 (2026-03-26)

**问题**：394 个 VOID 存在 knowledge_nodes 里，占 30% 搜索空间，0 个被升格。
**方案**：VOID 从"知识"变为"任务"——搬到独立的 `void_tasks` 表。

### 实际改动
1. **manager.py**: 新增 `void_tasks` 表 + 7 个 CRUD 方法（add/get_open/get_recent/resolve/stale/exists/stats）
2. **loop.py `_auto_record_voids()`**: 从 `create_node()` 改为 `add_void_task()`，去掉向量去重（不再需要）
3. **manager.py `get_digest()`**: VOID 板块从 knowledge_nodes 改读 void_tasks
4. **loop.py C-Process prompt**: 简化 VOID 升格指令（C 只需写 LESSON，VOID 状态管理由基础设施层处理）
5. **数据迁移**: 394 个 VOID 迁移到 void_tasks + 从 knowledge_nodes/node_contents/node_edges 清除

### 效果
- knowledge_nodes: 1328 → 934（-30%）
- 搜索空间纯净化：只有真正的知识参与搜索排序

---

## Phase B：知识膨胀治理 ✅ 已完成 (2026-03-26)

### 实际改动
1. 清理 69 个 FERMENTED 假设节点 + 相关边
2. 关闭拾荒器 `ENABLE_SCAVENGER=False`（Autopilot 上位替代）
3. 关闭假设引擎 `ENABLE_HYPOTHESIS=False`
4. 清理 191 个未使用 ENTITY/EVENT/ACTION/TOOL 节点 + 相关边
5. 锁死 C-Process：移除 `create_graph_node`/`record_tool_node` 工具，更新 prompt
6. 搜索 ntype enum 只保留 ALL/LESSON/ASSET/CONTEXT/EPISODE

### 效果
- KB: 934 → 674 节点（累计瘦身 49%）
- C-Process 将来只能创建 LESSON/ASSET/CONTEXT，无法再产生废弃类型

---

## Phase C：Arena 信号修复 + 效用驱动检索 ✅ 已完成 (2026-03-26)

**问题诊断**：Arena 信号链有三个断点：
1. Op 自报 STATUS（LLM 乐观偏差 → 98.5% SUCCESS）
2. 全体连坐（所有 active_nodes 同赏同罚）
3. 无反事实（分不清“帮了忙”还是“搭便车”）

**设计理念**（MemRL + 自证悖论分析）：
- 环境信号（工具 exit code / Error 前缀）做客观门槛，不信任 LLM 自报
- C 作为交叉验证者（而非自证者），未来可做逻节点归因（远期）
- 效用信号（战绩）必须成为检索主轴，而非配角

### 实际改动
1. **loop.py `_classify_tool_result()`**: 新增静态方法，从工具返回值提取客观成功/失败信号
   - `Error:` 前缀 → 失败
   - `[TIMEOUT]` → 失败
   - shell 退出码 != 0 → 失败
   - 其余 → 成功
2. **loop.py `_compute_env_success()`**: 计算 Op 工具调用客观成功率
3. **loop.py `_run_c_phase()`**: Arena 判定从 Op 自报 STATUS 改为 env_success_ratio
   - ≥ 0.7 → boost（环境确认成功）
   - ≤ 0.3 → decay（环境确认失败）
   - 中间 / 无信号 → 中性（只记 usage_count）
4. **manager.py**: Arena FLOOR 从 0.4 降为 0.15（低相关节点拿最小信用）
5. **node_tools.py**: fusion_score 权重重新分配
   - metric(UCB战绩) 从 20% → 35%（主信号）
   - rerank(相关度) 从 35% → 30%（门槛）
   - trust(来源可信度) 从 25% → 15%
   - 无 reranker 时：metric = 50%（缺相关度精排时靠实战记录）

---

## Phase D：远期精细化

### D.1 C-Process 逻节点归因（Phase C 的下一步）
- 环境信号做门槛（已完成），C 做精细分配（待做）
- C 作为交叉验证者评估每个 active_node 的实际贡献
- 需新增 arena_attribute 工具，并将 Arena 更新移到 C 完成之后

### D.2 其他观察项
- Daemon 优先级调度（只剩边缘发现+蒸馏+验证+GC）
- 签名冷启动种子

### 理论框架（MemRL 启发）

Genesis 元信息系统的维度升级方向：从“相似度驱动检索”转向“效用驱动检索”。

- **MemRL (2026/01)**: Intent-Experience-Utility 三元组，Q-value 驱动检索
- **Genesis 对应**: signature=Intent, LESSON=Experience, metric_score=Utility
- **关键断点**: Arena 信号质量决定了 Q-value 能否收敛
- **自证悖论防御**: 环境信号(客观) + C(交叉验证) — 不信任 LLM 自报

---

## 执行纪律

1. **一次只做一个 Phase**
2. **红线**：不改现有 API 返回结构（只追加），每个改动可通过开关回退
3. **验证**：每个 Phase 结束跑 Autopilot ≥5 任务确认无回归

---

## 进度追踪

| Phase | 状态 | 日期 | 改动文件 | 备注 |
|---|---|---|---|---|
| A - VOID 分离 | ✅ 完成 | 2026-03-26 | manager.py, loop.py | 394节点迁移到void_tasks，KB瘦身30% |
| B - 膨胀治理 | ✅ 完成 | 2026-03-26 | background_daemon.py, loop.py, node_tools.py | 拾荒+假设关闭, 191 ENTITY/EVENT/ACTION/TOOL 清理, C锁死 |
| C - Arena+效用检索 | ✅ 完成 | 2026-03-26 | loop.py, manager.py, node_tools.py | 环境信号替代自报, FLOOR 0.15, metric 35% |
| D - 远期精细化 | 🔲 待定 | | | C归因, Daemon调度 |
