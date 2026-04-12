# 元信息架构反思 — 2026-04-08 讨论记录

## 背景

C-Phase 产出的 LESSON 质量极低（57% 从未使用），vault 中充斥 "用内置工具做文件操作" 之类的垃圾 meta-lesson。需要从根本上重新思考元信息的录入机制。

---

## 讨论路径与纠偏

### 1. C-Phase 的本质认知

**结论**：C-Phase 不是独立组件，是 GP 换皮（异步后置的 prompt，同一个 LLM/provider）。不应该做架构拆分（确定性层+LLM层+后处理层），那是过度工程化。

### 2. "公式 + LLM 各司其职" 的方向

**提出**：确定性公式管"该不该记"（新颖度、覆盖度），LLM 管"怎么表达"（理解+结构化）。

**纠偏**：
- 公式太简陋（只有向量去重 + 路径检测 + 空话检测），只抓表面特征
- 公式用脏数据做判断（vault 57% 是垃圾，垃圾当"已有知识"阻止好知识进入）
- 只管入口不管淘汰，治标不治本

### 3. 元信息生命周期管理

**提出**：完整的创建→入库→发现→使用→验证→淘汰流程，质量门下沉到 vault.create_node。

**纠偏**：把简单问题复杂化了。

### 4. "笔记" 视角 / RAG 视角

**提出**：
- 元信息就是笔记，写得差是因为输入差
- 或者转向 "读取时推理"（存自然语言摘要，GP 搜索时推理）

**纠偏**：本质上就是传统 RAG / 上下文压缩，不是新路径。

### 5. 核心问题的重新定义

> "LLM 在训练时已知的所有信息，都将成为噪音"

C-Phase 需要做的是**精确录入**，但 LLM 的训练倾向（完备主义、帮助性、自由发挥）在这个场景下全部变成干扰。常规 prompt 手段（"宁缺毋滥"）打不过训练权重。

**真正需要的**：一种高效的录入语言/途径，让 AI 在已有规则内规划，最大程度遏制训练噪音。

### 6. "tool calling 作为受限语言" 的方向

**提出**：把知识录入变成 tool calling（schema 天然约束输出空间），而非自由文本生成。

- 确定性代码决定**有什么可以记**（根据执行结果生成候选工具集）
- Schema 决定**能怎么记**（枚举字段、限长字段，训练噪音无处泄漏）
- LLM 只做**理解性填空**（root_cause 等需要推理的字段）

---

## MemPalace 参考

> 来源：github.com/milla-jovovich/mempalace (2026-04)

### AAAK 压缩格式

30x token 压缩，AI 原生可读，无需解码器。核心思路：结构化英文缩写。

```
原始 (~1000 tokens):
"Priya manages Driftwood team: Kai (backend, 3 years), Soren (frontend)..."

AAAK (~120 tokens):
TEAM: PRI(lead) | KAI(backend,3yr) SOR(frontend) MAY(infra) LEO(junior,new)
PROJ: DRIFTWOOD(saas.analytics) | SPRINT: auth.migration→clerk
DECISION: KAI.rec:clerk>auth0(pricing+dx) | ★★★★
```

**启发**：这就是一种"高效语言"。不是自然语言（太自由），不是严格 JSON（LLM 容易出错），而是**带结构的速记**。LLM 天然能读写这种格式。

### 空间组织 (Wing → Room → Hall)

- **Wing**: 项目/领域（相当于 Genesis 的 task domain）
- **Room**: 子话题（auth, deploy, debug...）
- **Hall**: 记忆类型走廊
  - `hall_facts` — 已锁定的决策
  - `hall_events` — 会话和里程碑
  - `hall_discoveries` — 突破性发现
  - `hall_preferences` — 习惯和偏好
  - `hall_advice` — 建议

**启发**：光靠结构就提升 34% 检索准确率。NodeVault 的组织方式（类型+标签）是平面的，不是空间的。

### 分层加载 (L0-L3)

- L0 + L1 = 170 tokens（启动时加载）
- L2, L3 按需加载

**启发**：不是把所有知识塞进 prompt，而是分层。启动时只加载"身份+当前项目状态"，深层知识按需检索。

### 时间知识图谱

```python
kg.add_triple("Kai", "works_on", "Orion", valid_from="2025-06-01")
kg.invalidate("Kai", "works_on", "Orion", ended="2026-03-01")
```

**启发**：每个 fact 有 validity window。Invalidation 标记结束日期而不删除。矛盾检测。这解决了 NodeVault 缺少的淘汰/过期机制。

---

## 思考结论

### 1. Genesis 的速记格式：DISCOVERY → PATTERN 两层

不直接套 AAAK（那是人/团队信息的压缩），而是针对 Genesis 的执行知识设计两层：

**DISCOVERY**（单次观察，C 录入）：
```
DISC: nginx.port.conflict
DESC: port.80.bound(apache2) → nginx.startup_fail
EVIDENCE: span:s_042 | tool:shell
TAGS: nginx,port,conflict,apache
```

**PATTERN**（多次验证的规律，代码自动提升）：
```
PAT: nginx.port.conflict
IF: start(nginx) + port.bound
THEN: lsof(-i,:80) → kill|change_port
BECAUSE: port.preoccupied(common:apache)
EVIDENCE: disc_001,disc_047,disc_089 (3 instances)
CONF: 0.85 | SINCE: 2026-03
```

核心：**C 只写 DISCOVERY（分类+压缩），PATTERN 从重复 DISCOVERY 中自动浮现。**
- DISCOVERY 是观察，不需要因果推理 → LLM 噪音低
- PATTERN 是规律，需要多次验证 → 不再是单次猜测

### 2. 录入层重做：三阶段流水线

```
阶段1（代码，零 LLM）：
  _op_tool_outcomes → TOOL_BEHAVIOR 候选
  g_messages outputs → ENV_FACT 候选
  失败→成功序列 → APPROACH 候选
  错误模式 → ERROR_PATTERN 候选

阶段2（C = GP 换皮，tool calling）：
  record_discovery(
    category: enum[TOOL_BEHAVIOR, ENV_FACT, APPROACH, ERROR_PATTERN],
    subject: str,        # dot notation, max 3 levels
    description: str,    # AAAK 速记, max 30 tokens
    evidence_span: str,  # 指向 trace span
    tags: list[str],     # max 5
  )
  → Schema 就是约束，训练噪音无处泄漏

阶段3（代码，零 LLM）：
  同 subject DISCOVERY 出现 N 次 → 提升为 PATTERN
  提升阈值可调（频率、一致性、证据强度）
```

### 3. 空间组织：dot notation 隐含层次

不做显式 Wing/Room 表结构。DISCOVERY subject 的 dot notation 本身就是空间地址：
- `nginx.port.conflict` → 前缀 `nginx.` 过滤即可
- Knowledge Map 按 subject 前缀分组 → 自然形成层级视图
- 如果检索精度不够，未来再升级为显式结构

### 4. 分层加载

| 层 | 内容 | Token | 加载时机 |
|---|---|---|---|
| L0 | System prompt（身份、规则、工具列表） | ~固定 | 每轮 |
| L1 | AAAK 压缩知识摘要（wing 密度 + 最近发现 + VOID） | ~200 | 每轮 |
| L2 | SearchKnowledgeNodesTool 检索结果 | 按需 | GP 主动搜索 |
| L3 | 完整 node_content | 按需 | GP 请求具体节点 |

L1 示例：
```
[知识概览]
infra.nginx: 5pat,3disc | HIGH | recent:port.conflict(2d)
infra.docker: 2pat,1disc | LOW  | void:overlay.routing
code.python: 3pat,0disc  | MED  | recent:venv.path(5d)
```

**SearchKnowledgeNodesTool = L2 加载机制**，不是可选功能。

### 5. 时间维度：读时衰减

```python
def effective_confidence(node) -> float:
    if node.trust_tier == "HUMAN": return node.confidence_score
    days_idle = (now - max(last_verified_at, updated_at)).days
    half_life = {"CONTEXT": 30, "DISCOVERY": 90, "PATTERN": 180}.get(node.type, 120)
    return node.confidence_score * 0.5 ** (days_idle / half_life)
```

- 无 schema 变更，对现有 3050 节点立即生效
- `effective_confidence < 0.2` → 搜索排除（软淘汰，不删除，可复活）
- 矛盾检测：新 DISCOVERY 同 subject 不同内容 → 降旧节点 confidence

---

## 方向决定

**保留图层（边、Arena、圆锥、VOID），重做录入层（从"提取"到"分类+压缩"）。**

实施优先级：
1. C-Phase 录入层改造（阶段1信号提取 + 阶段2 tool calling DISCOVERY）
2. 读时衰减函数（effective_confidence）
3. L1 压缩知识摘要替代当前 Knowledge Map 注入
4. SearchKnowledgeNodesTool 注册（L2 加载机制）
5. PATTERN 自动提升逻辑（阶段3）
