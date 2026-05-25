# Knowledge Governance Layer（知识管家层）

> 目标：停止逐点打补丁，把 Genesis 的知识风险统一收束到“信号生命周期 + 治理动作门”。
> 状态：设计草案，先做 report-first，不自动改写知识。

> 防漂移：Knowledge Governance 不是主线，只是清洁杠杆。它服务于 Genesis 自我概念模型和 V6 每用户小模型的训练数据质量；如果某个治理动作不能提高未来路线先验、轨迹可蒸馏性、点线面复用、标签洁净度或减少重复探索，就不要做。

---

## 一、为什么需要这一层

Yogg 5/21-23 的深挖暴露出的问题看似很多：

- Evidence Assessor 污染 Arena
- Arena 集体归因
- CONTRADICTS 只标记不消解
- ENV_FACT 旧环境事实冒充当前事实
- node cleanup 过去会自动硬删
- trust_tier 出生证不演化
- witness chain 缺失
- 经济成本只统计不决策
- 技能/EPISODE 资产孤儿化

这些不是互不相关的 bug。共同病灶是：

> Genesis 有很多信号生产者，但没有统一的信号生命周期，也没有统一的知识状态变更入口。

于是每个子系统都在局部解释自己的信号：

| 子系统 | 信号 | 原问题 |
|---|---|---|
| Arena | 工具成功率 → usage_success/fail | 全局归因，所有 active nodes 连坐 |
| Evidence Assessor | trace 文本匹配 | 曾经被动写 Arena 计数 |
| CONTRADICTS | node_edges 矛盾边 | 标记存在，但没有收束流程 |
| ENV_FACT | DISCOVERY 环境事实 | 无再验证/过期判断 |
| node cleanup | 未使用 + 超龄 | 过去可直接硬删 |
| topology audit | 拓扑异常 | 只打日志，不进入统一队列 |

更上层解不是继续给每个信号单独补逻辑，而是增加一层：

> Knowledge Governance Layer = 统一解释信号、排队风险、限定动作权限的知识管家。

---

## 二、设计原则

### 1. Report-first，不自动改写

第一版只聚合报告，不做自动动作。

禁止第一版执行：

- 自动删除节点
- 自动降权
- 自动升格
- 自动失效
- 自动改 `last_verified_at`
- 自动改 `usage_success_count` / `usage_fail_count`

第一版只输出：

- 什么信号出现了
- 风险属于哪类
- 需要什么验证
- 哪些项应进入人工/后续自动化候选队列

### 2. Signal ≠ Action

信号只是观察，不等于可以行动。

例子：

- `CONTRADICTS` 边 = 有矛盾标记，不等于旧节点已被证伪。
- ENV_FACT cwd mismatch = 当前 runtime 不一致候选，不等于节点应立即失效。
- Arena fail = 环境失败，不等于某个节点导致失败。
- cleanup candidate = 删除候选，不等于可以删除。

### 3. 统一动作门

以后如果要真正改知识，必须通过统一动作门：

```python
propose_action(...)
apply_action(...)
```

动作必须包含：

- target
- action
- reason
- evidence
- dry_run preview
- human/apply gate

### 4. 不回到圆锥模型

治理层不是新的全局分数系统。

它不引入：

- 综合健康分
- 节点价值总分
- 自动融合评分
- “神经系统”隐喻

PLS 仍然用拓扑表达价值。治理层只处理：

> 信号是否可信、是否过期、是否允许触发状态变化。

---

## 三、信号分类

第一版治理层只收束已经存在的信号。

| signal_type | 来源 | 含义 | 第一版动作 |
|---|---|---|---|
| `deletion_candidate` | `node_cleanup`, `purge_forgotten_knowledge` | 可能可清理 | report only |
| `contradiction_marker` | `node_edges.CONTRADICTS` | 有矛盾标记 | report only |
| `env_fact_freshness` | `DISCOVERY/ENV_FACT` | 环境事实可能过期或冲突 | report only |
| `arena_collective_attribution` | C-Phase Arena | 集体归因风险 | report only |
| `passive_evidence_candidate` | Evidence Assessor | 被动强化/削弱候选 | report only |
| `topology_anomaly` | topology audit | 孤儿边/虚点/结构异常 | report only |
| `cost_signal` | token/duration/cost_estimate | 成本统计 | report only |

---

## 四、统一状态词汇

治理层不改变节点类型，只给风险项打状态。

```text
observed              已观察到信号
candidate             可能需要处理
needs_verification    需要验证
needs_resolution      需要收束
stale_candidate       疑似过期
mismatch_candidate    疑似与当前状态冲突
quarantined_candidate 隔离候选
resolved              已解决
ignored               明确忽略
```

这些状态第一版只存在于报告里，不落库。

---

## 五、治理队列

统一报告输出虚拟队列：

```python
{
  "dry_run": True,
  "governance_mode": "report_only",
  "queues": {
    "needs_verification": [],
    "needs_resolution": [],
    "needs_attribution_audit": [],
    "blocked_from_auto_delete": [],
    "needs_human_review": []
  }
}
```

### needs_verification

适合放入：

- unverified ENV_FACT
- stale ENV_FACT
- runtime mismatch candidate
- Evidence Assessor reinforce/weaken candidate

### needs_resolution

适合放入：

- stale + both_active CONTRADICTS
- orphan CONTRADICTS
- unresolved contradiction pairs

### needs_attribution_audit

适合放入：

- Arena 成功轮次里只被 preloaded 但无 opened/basis/tool evidence 的节点
- Arena 失败轮次里被集体扣分但无实际关联证据的节点

### blocked_from_auto_delete

适合放入：

- cleanup would_delete candidates
- purge_forgotten_knowledge candidates

第一版只列队，不执行。

---

## 六、第一版聚合器

建议新增：

```text
genesis/v4/knowledge_governance.py
```

核心函数：

```python
def build_governance_report(vault, *, limit=20) -> dict:
    ...
```

第一版聚合现有 dry-run 报告：

```python
{
  "contradictions": vault.contradiction_audit_report(...),
  "env_facts": vault.env_fact_freshness_report(...),
  "node_cleanup": node_cleanup.cleanup(dry_run=True),
  "forgotten_gc": vault.purge_forgotten_knowledge(dry_run=True),
}
```

然后生成统一摘要：

```python
{
  "dry_run": True,
  "governance_mode": "report_only",
  "risk_summary": {
    "data_loss_risk_candidates": 0,
    "signal_pollution_candidates": 0,
    "stale_anchor_candidates": 0,
    "unresolved_contradiction_candidates": 0,
    "credit_assignment_risk": "not_audited_yet"
  },
  "queues": {...},
  "raw_reports": {...}
}
```

---

## 七、和现有修复的关系

已完成的低层修复不是浪费，它们是治理层输入。

| 已完成修复 | 在治理层中的角色 |
|---|---|
| Evidence Assessor dry-run | `passive_evidence_candidate` 输入 |
| node cleanup dry-run | `deletion_candidate` 输入 |
| `contradiction_audit_report()` | `needs_resolution` 输入 |
| `env_fact_freshness_report()` | `needs_verification` 输入 |
| ShellTool cwd metadata | ENV_FACT / runtime mismatch 的证据来源 |

---

## 八、不做什么

第一版明确不做：

- 不新增节点类型
- 不改 PLS 拓扑消费机制
- 不替代 Arena
- 不把 CONTRADICTS 自动变成证伪
- 不把 ENV_FACT mismatch 自动变成失效
- 不把 cleanup candidate 自动删除
- 不做统一分数
- 不做成本优化策略
- 不做技能自动加载

---

## 九、后续演进

### Phase 1：文档与只读聚合器

- 本文档定边界
- 新增 `build_governance_report()`
- daemon/auto report 只输出摘要

### Phase 2：治理队列落表

如果 report-first 稳定，再考虑表：

```text
governance_actions
```

字段：

- action_id
- target_id
- signal_type
- proposed_action
- reason
- evidence_json
- status
- created_at
- resolved_at

### Phase 3：受控 apply

只允许显式 apply：

- human confirmed
- tests passed
- evidence refs complete
- dry_run preview reviewed

默认仍禁止 destructive actions。

---

## 十、一句话总结

Knowledge Governance Layer 不是新的智能体，也不是新的评分系统。

它是 Genesis 知识状态变化前的一道统一动作门：

> 所有信号先进入报告和队列；只有经过证据、边界和权限检查，才允许改变知识。
