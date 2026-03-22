# Multi-G 认知基准测试：参考答案

> 基于 Genesis 实际源码的 grounded 答案。每题给出：关键维度、根因分析、解决方案，以及 Genesis 现有代码中已实现的相关机制。

---

## Q1: 网络延迟诊断

### 关键维度

1. **代理路径**：SOCKS5 代理的 DNS 解析 / 连接建立 / 数据转发开销
2. **HTTP 客户端配置**：`trust_env` 设置决定是否绕道代理
3. **连接复用**：是否利用了 TCP 连接池（持久连接 vs 每次新建）
4. **API 端点地理位置**：国内 API（DeepSeek）不需要代理，墙外 API（Discord）需要

### 可能的根因

**最可能的根因：httpx 的 `trust_env=True` 导致国内 API 请求绕道 SOCKS5 代理。**

当 `trust_env=True` 时，httpx 会自动读取系统环境变量 `http_proxy` / `https_proxy`，即使目标是无需翻墙的国内 API（如 DeepSeek `api.deepseek.com`），也会强制走 SOCKS5 代理。代理的 DNS 解析和中转增加约 5-11 秒延迟。

其他可能原因：
- **代理本身不稳定**：SOCKS5 代理服务器间歇性丢包或 DNS 解析慢
- **连接未复用**：每次请求都建立新 TCP+TLS 连接（3-way handshake + TLS handshake ≈ 200-500ms，经代理翻倍）
- **Discord API 限流**：Discord 网关的 rate limiting（429 状态码），但日志中会有记录

### 排查步骤

1. **对比直连 vs 代理延迟**：
   ```bash
   # 直连 DeepSeek（不经代理）
   time curl -s https://api.deepseek.com/v1/models -H "Authorization: Bearer $API_KEY"
   # 经代理
   time curl -x socks5h://proxy:port -s https://api.deepseek.com/v1/models -H "Authorization: Bearer $API_KEY"
   ```
2. **检查 httpx 客户端的 `trust_env` 设置**
3. **查看 systemd 日志中 LLM 调用耗时**：`journalctl --user -u genesis-v4 | grep "duration"`
4. **检查代理健康**：`curl -x socks5h://proxy:port https://httpbin.org/ip`

### Genesis 已有的解决方案

Genesis 已经在 `provider.py:52` 中设置了 `trust_env=False`：

```python
self._http_client = httpx.AsyncClient(timeout=timeout, trust_env=False)
```

这强制 httpx 绕过系统代理环境变量，国内 API 直连。同时在 `config.py:178` 的 `_apply_proxies()` 中注入代理到系统环境变量（供其他需要翻墙的组件使用），并留下了注释说明这一权衡。

此外，httpx 客户端通过 `_get_http_client()` 实现了**延迟初始化的持久连接池**，复用 TCP 连接，避免重复握手开销。

---

## Q2: 知识库搜索性能

### 关键维度

1. **向量搜索复杂度**：内存中的矩阵乘法 vs SQLite 全表扫描
2. **Embedding 模型推理开销**：每次搜索都要编码查询文本
3. **SQLite LIKE 查询**：模糊匹配的 O(N) 全表扫描
4. **Reranker 精排**：Cross-Encoder 的 O(K) 推理开销
5. **图遍历**：Graph Walk 对每个搜索结果做 1-hop 邻居查询

### 瓶颈分析

**瓶颈 #1（最大）：每次搜索触发 Embedding 模型推理。**
`VectorEngine.search()` 每次调用 `self._model.encode(query)` 对查询文本做一次前向推理。即使 `bge-small-zh-v1.5` 很小（~33M 参数），在 CPU 上单次推理仍需 30-80ms。搜索频率高时这是主要瓶颈。

**瓶颈 #2：Cross-Encoder Reranker 精排。**
`VectorEngine.rerank()` 对每个候选节点调用 `CrossEncoder.predict()`，这是 O(K) 次模型推理（K 为候选数，当前上限 40）。Cross-Encoder 比 Bi-Encoder 慢 10-100 倍。

**瓶颈 #3：SQLite LIKE 查询。**
`SearchKnowledgeNodesTool.execute()` 中对每个关键词做 4 个 LIKE 匹配（title, tags, node_id, resolves），每个 LIKE 都是全表扫描。500 节点 × 4 字段 × N 关键词 = O(2000N) 次字符串匹配。

**瓶颈 #4：Graph Walk N+1 查询。**
对每个搜索结果节点，分别做 `get_related_nodes(nid, "out")` 和 `get_related_nodes(nid, "in")` 两次 SQL 查询。10 个结果 = 20 次额外 SQL。

### 优化方案

| 层级 | 措施 | 预期收益 |
|------|------|---------|
| **向量搜索** | 查询向量 LRU 缓存（相同/相似查询不重复编码） | 高频重复查询延迟 -90% |
| **向量搜索** | 矩阵运算已用 `np.argpartition`（O(N) vs O(NlogN) 排序），这已经是最优 | 已实现 |
| **Reranker** | 降级策略：节点数 < 阈值时跳过精排 | 简单查询延迟 -50% |
| **SQLite** | 为 title/tags/resolves 建 FTS5 全文索引替代 LIKE | 关键词匹配从 O(N) 降到 O(logN) |
| **SQLite** | 为 node_edges 的 source_id/target_id 建索引 | 图遍历查询加速 |
| **Graph Walk** | 批量查询代替逐节点查询（WHERE source_id IN (...)） | 20 次查询 → 2 次 |
| **整体** | 增量同步已实现 `sync_vector_matrix_incremental()` | 跨进程向量同步已解决 |

### Genesis 已有的优化

- `VectorEngine` 使用**预归一化矩阵** + **点积代替余弦相似度**（`vector_engine.py:80-82`）
- `np.argpartition` 代替完整排序（`vector_engine.py:118`）
- 内存矩阵 + 增量同步（`manager.py:83-114`），避免每次从 SQLite 读向量
- 批量预取 prerequisite 节点签名（`node_tools.py:261-270`），减少 N+1 查询
- Reranker 异步延迟加载（`vector_engine.py:36-48`），不阻塞启动
- `add_to_matrix_batch` 批量添加（`vector_engine.py:180-202`），一次 vstack 代替逐条 O(N²) 拷贝
- `_normalize_metadata_signature_cached` 使用 LRU 缓存（`manager.py:275`）

---

## Q3: 多 LLM Provider 容错

### 关键维度

1. **Failover 策略**：主备切换的触发条件和回退顺序
2. **超时管理**：区分"请求超时"和"推理超时"
3. **SSE 流式解析**：流中断的断点续传和数据完整性
4. **JSON 修复**：LLM 输出的非法 JSON 的容错解析
5. **Recovery（探活）**：主 provider 恢复后自动切回

### 设计方案（Genesis 已实现）

#### 1. 分层 Provider 架构

```
ProviderRouter（实现 LLMProvider 接口，对上层透明）
├── Core Pool:    deepseek → gemini（主备，用于 G/Op/C）
├── Consumable Pool: groq → siliconflow → dashscope → ...（免费池，用于后台守护进程）
└── MockLLMProvider（兜底）
```

**关键设计**：`ProviderRouter` 自身实现 `LLMProvider` 接口，上层（Agent/Loop）完全不感知 failover 细节。

#### 2. Failover 触发与顺序

- **触发条件**：`httpx.ConnectError`、`httpx.TimeoutException`、`httpx.NetworkError`、HTTP 5xx 状态码
- **不触发 failover 的异常**：`WallClockTimeoutError`（推理超时，不是 provider 故障——可能是推理模型思考过久）
- **顺序**：按 `failover_order = ['deepseek', 'gemini']` 线性尝试
- **Recovery 探活**：failover 后每 60 秒用 `max_tokens=1` 的 ping 请求探测主 provider，成功则自动切回

#### 3. 三层超时体系

| 层级 | 配置 | 默认值 | 作用 |
|------|------|--------|------|
| `connect_timeout` | httpx 连接超时 | 30s | 快速发现网络不通 |
| `request_timeout` | httpx 请求超时 | 180s | 防止单次请求无限等待 |
| `wall_clock_timeout` | `asyncio.wait_for` 外层包裹 | 300s | 防止推理模型（如 DeepSeek-R1）思考过久 |

#### 4. SSE 流式解析容错

- 逐行解析 `data: ` 前缀的 SSE 事件，跳过空行和非 data 行
- `[DONE]` 信号正常终止
- 流中断时 5xx 状态码触发重试（最多 3 次，指数退避）
- **重试时重置所有累积器**（`full_content`, `tool_call_chunks` 等），防止部分流残留导致内容重复
- Reasoning content（`<thinking>` 链）和正文内容分离收集

#### 5. JSON 修复（3 层回退）

```
原始 JSON → json.loads()
   ↓ 失败
转义修复（\n, \r, \t）→ json.loads()
   ↓ 失败
标记为 __json_decode_error__（保留原始文本，不丢弃）
```

流式路径和非流式路径的修复逻辑保持一致。

### 关键代码位置

- `provider_manager.py:31-246`：ProviderRouter，failover + recovery 逻辑
- `provider.py:106-115`：三层超时 + WallClockTimeoutError 区分
- `provider.py:219-228`：流式重试时重置累积器
- `provider.py:310-335`：流式工具调用 JSON 修复
- `provider_manager.py:131-151`：Recovery 探活机制

---

## Q4: Agent 知识质量控制

### 关键维度

1. **去重**：写入前检测语义相似的已有节点
2. **淘汰**：低置信度 + 长期未使用的节点自动清理
3. **验证**：定期用实际测试校验知识的有效性
4. **置信度演化**：基于实战结果动态调整（非静态标签）
5. **矛盾检测**：同一领域的节点是否给出冲突建议

### Genesis 已实现的完整质量控制体系

#### 1. 写入时去重（LESSON 语义去重）

`RecordLessonNodeTool.execute()` 在创建新 LESSON 前：
- 向量搜索 top-3 相似的已有 LESSON（阈值 0.75）
- **相似度 ≥ 0.85**：合并到已有节点（覆写内容 + 提升置信度 +0.1），不创建新节点
- **0.65 ~ 0.85**：创建新节点，但建立 `RELATED_TO` 边（标记为"近亲"）
- **< 0.65**：正常创建全新节点

#### 2. 知识竞技场（Knowledge Arena）

实战结果驱动的置信度演化：
- **任务成功**：`record_usage_outcome(nodes, success=True)` → `usage_success_count++` + `confidence_score += 0.1`
- **任务失败**：`record_usage_outcome(nodes, success=False)` → `usage_fail_count++` + 贝叶斯衰减
- **贝叶斯衰减**：惩罚力度随历史战绩自动减轻（`penalty / (1 + success_ratio * log(usage_count))`）。久经考验的知识天然抗衰减（Long-Term Potentiation）
- **Trust Tier 地板保护**：高信任节点的 confidence 永远不会被连坐打到 GC 线以下

#### 3. UCB 探索 vs 利用（搜索排序）

`SearchKnowledgeNodesTool._metric_score()` 使用 UCB（Upper Confidence Bound）公式：
```
exploitation = success_rate
exploration = sqrt(2 * ln(N+1) / (n+1))
score = exploitation + 0.15 * exploration
```
- 未测试节点获得探索加成（≈ 0.7），鼓励尝试
- 经过考验的好节点 > 0.8
- 失败多的节点 < 0.4

#### 4. 垃圾回收（GC）

`NodeVault.purge_forgotten_knowledge()`：
- 清理条件：`confidence_score < 0.5` AND `usage_count = 0` AND `created_at < 7天前`
- 排除对话记忆节点（MEM_CONV）
- 物理删除：节点本体 + 内容 + 边 + 版本历史 + 向量矩阵中的行

#### 5. 出生证系统（Trust Tier）

每个节点携带不可伪造的来源水印：
```
HUMAN (4) > REFLECTION (3) > FERMENTED (2) > SCAVENGED (1) > CONVERSATION (0)
```
- 影响初始 confidence_score（HUMAN=0.85, SCAVENGED=0.35）
- 影响搜索排序中的 trust_score（tier_bonus 加权）
- TOOL 节点执行需要最低信任等级（REFLECTION 以上）

#### 6. 版本链（Version Chain）

`_snapshot_if_exists()` 在节点被覆写前自动快照到 `node_versions` 表：
- 每节点保留最近 5 个版本（`VERSION_KEEP_LIMIT`）
- 超限自动 GC
- 支持通过 `get_node_versions()` 回溯编辑历史

#### 7. 后台验证守护进程（Verifier）

`genesis/v4/verifier.py`：定期扫描旧的 LESSON 和 CONTEXT 节点，用 LLM 生成测试场景，更新 confidence_score 和 validation_status。

#### 8. 后台发酵守护进程（Fermentor）

`genesis/v4/fermentor.py`：扫描现有 LESSON 并生成假设性 EPISODE 节点，定向填补知识空白。

---

## Q5: 从单 Agent 到多视角分析

### 关键维度

1. **多样性来源**：不同视角如何真正产生差异
2. **信息共享 vs 隔离**：多个视角是否看同一份数据
3. **合并策略**：如何将多个结论收敛为行动方案
4. **成本控制**：简单任务不应付出多视角成本
5. **与现有架构的兼容性**

### Genesis 已实现的 Multi-G 架构

#### 核心原则：多样性来自不同解读，而非不同输入

> **反面教材**：给每个 persona 限制搜索不同类型节点 → 传统的多 agent 分治法，破坏了核心设计。
>
> **正确做法**：所有透镜搜索 ALL 类型，看到相同结果，差异来自基于 MBTI 认知功能栈的不同 **interpretation**。

#### 架构：G 主脑 + 透镜子程序

```
G（主脑，保留现有全部能力）
├── 阶段 1：infer_signature → 判断是否启用 Multi-G
├── 阶段 2：dispatch_to_lens（并行 spawn 3 个透镜子程序）
│   ├── Lens-ISTJ：搜 NodeVault → 写黑板（证据型 或 假设型）
│   ├── Lens-INTP：搜 NodeVault → 写黑板
│   └── Lens-ENFP：搜 NodeVault → 写黑板
├── 阶段 3：G 读黑板 → 确定性坍缩 → 综合判断
├── 阶段 4：dispatch_to_op（现有流程不变）
└── 阶段 5：C-Process 捕获信息空洞
```

透镜是 G 的"感官"（对称于 Op 是 G 的"手脚"）。

#### 差异化机制：MBTI 认知框架

每种人格有 4 句话的 `cognitive_frame`（认知模式、关注点、结论倾向、质疑维度）：

| 人格 | 认知模式 | 关注什么 | 质疑什么 |
|------|---------|---------|---------|
| **ISTJ** (Si-Te) | 与历史经验对照 | 搜索结果中与过去成功/失败相似的模式 | 是否有前车之鉴？是否忽略了历史教训？ |
| **INTP** (Ti-Ne) | 解构到底层机制 | 能解释根因的线索 | 是否真正触及了根因？还是在症状层面打转？ |
| **ENFP** (Ne-Fi) | 发散联想 | 意外发现和非显而易见的关联 | 是否被思维定式限制？是否有替代路径？ |
| **INTJ** (Ni-Te) | 全局系统审视 | 架构决策、涟漪效应 | 是否只是局部最优？会否引入技术债？ |
| **ISTP** (Ti-Se) | 最小实验优先 | 具体命令、可立即执行的操作 | 是否过度分析而不是直接测试？ |
| **ISFJ** (Si-Fe) | 边界条件和细节 | 异常处理、回退方案、容错 | 边界条件是否被覆盖？失败的回退策略？ |

所有透镜的搜索调用 `search_knowledge_nodes` 不限制 `ntype`，搜索 ALL 类型——看到相同的搜索结果，但产出不同的理解。

#### 黑板双轨制 + 确定性坍缩

**黑板接受两类条目**：
- **证据支撑型** `(framework, evidence_node_ids, verification_action)`：有 NodeVault 节点背书
- **纯假设型** `(framework, reasoning_chain, suggested_search_directions)`：无证据但有推理链

**确定性坍缩（零 LLM 判断）**：
```python
# 证据型评分
score = Σ(node.confidence × TIER_WEIGHT[node.trust_tier])
      + specificity_bonus      # 验证动作具体性
      + exclusive_node_bonus   # 独占节点加分（别的透镜没引用）
      + ntype_coverage_bonus   # ntype 覆盖广度加分

# 假设型评分
score = BASE_HYPOTHESIS_WEIGHT + chain_length_bonus  # 基础分更低，但不为零
```

多样性加分是关键：奖励的是**输出多样性**（不同透镜引用了不同节点、覆盖了不同类型），而非限制输入。

#### 成本控制：自适应激活

- **签名映射**：`PERSONA_ACTIVATION_MAP` 根据 `task_kind` 自动选择最相关的 3 个人格
- **用户开关**：`/deep` 强制启用，`/quick` 强制跳过
- **任务门槛**：只有 `debug/refactor/build/optimize/design/test/deploy/configure` 等复杂 task_kind 才自动启用
- **自然衰竭**：连续 10 秒无新黑板条目 → 透镜自动停止

#### 信息空洞闭环

透镜搜索未命中 → 记录 search void → 注入 C-Process prompt → C 提取高价值空洞 → 写入 VOID 标签节点 → Fermentor 优先拾荒 VOID 节点 → 下次循环透镜搜到更多 → **闭环**。

### 关键代码位置

- `blackboard.py`：黑板数据结构 + 双轨制 + 确定性坍缩
- `loop.py:1074-1116`：Multi-G 激活判断 + 人格选择
- `loop.py:119-126`：透镜阶段编排
- `loop.py:239-253`：黑板坍缩结果注入 G 上下文
- `manager.py:1156-1254`：PERSONA_ACTIVATION_MAP + PERSONA_LENS_PROFILES（认知框架）
- `manager.py:1319-1375`：`build_lens_prompt()`（透镜提示词）
- `loop.py:987-999`：信息空洞注入 C-Process

---

## 评分维度建议

| 维度 | 权重 | 说明 |
|------|------|------|
| **根因定位** | 30% | 是否准确定位到最关键的瓶颈/问题 |
| **架构理解** | 25% | 对 G/Op/C 三阶段、双层 NodeVault、子程序模型的理解深度 |
| **方案完整性** | 25% | 解决方案是否覆盖了关键边界条件（退化、兜底、成本） |
| **工程可行性** | 20% | 方案是否可在现有架构上实施，改动量是否合理 |
