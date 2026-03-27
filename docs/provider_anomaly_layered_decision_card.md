# Provider 异常分层判定表 / 决策卡

## 目的

在外部 provider 异常出现时，先区分：
1. **代码内自动处理层**：已有 retry / failover / 连接恢复机制先消化；
2. **人工只读诊断层**：当自动机制未闭环时，只做证据核验、状态说明、最小诊断；
3. **禁止宣告完成 / 禁止高风险写入层**：关键结果仍受失稳 provider 影响时，不得误报完成、不得继续高风险写入。

本卡用于验证：当前缺口是否主要在**行为层 SOP**，而不是重复实现已有 provider 自动机制。

---

## 三层边界

### A. 代码内自动处理层
适用：源码已明确覆盖、应先由系统自动吸收的异常。

已见机制：
- `genesis/core/provider.py`
  - 普通请求与流式请求均有 `retries = 5`。
  - `502/503/504` 会自动重试。
  - `httpx.ConnectError` / `TimeoutException` / `NetworkError` / `RemoteProtocolError` 会自动重试。
  - 记录 retry / timeout / error 统计。
  - `WallClockTimeoutError` 被定义为“**非 provider 故障，不应触发 failover**”。
- `genesis/core/provider_manager.py`
  - `ProviderRouter.chat()` 对当前 provider 失败后，会对后续 provider 做 **dynamic failover**。
  - 注释明确：failover 仅面向 **5xx / 网络 / 超时等服务端故障**。
  - 对首选 provider 有定期 recovery probe，恢复后自动切回。
  - `400` 被视为客户端格式错误，**不通过换 provider 解决**，直接上抛。

结论：凡属于上述已编码吸收范围，优先认定为“自动处理层”，不应把 SOP 写成新的 retry/failover 替代实现。

### B. 人工只读诊断层
适用：
- 自动 retry / failover 后仍未形成稳定结果；
- 错误语义未明；
- 存在间歇成功、部分成功、日志互相冲突；
- 需要对外给出最小、保守、只读结论。

允许动作：
- 读取日志、源码、配置说明；
- 说明“当前轮次受 provider 不稳定影响”；
- 输出最小诊断摘要、重试建议、人工最小命令、待恢复后回写草稿。

禁止动作：
- 将单次故障扩写为系统性结论；
- 在关键结果仍依赖失稳 provider 时宣告“已验证完成/已交付完成”；
- 为了闭环继续扩大写入面。

### C. 禁止宣告完成 / 禁止高风险写入层
触发：
- 关键验证结果仍依赖当前失稳 provider；
- 已出现连续失败、跨时段复现、部分成功但整体不可判定；
- 无法区分是 provider 配额、上游故障、网络、还是本地配置问题。

此层要求：
- 不宣告 PASS / FAIL / SAFE-TO-WRITE / 已完成；
- 不做不可回滚修改、批量写入、对外确定性结论；
- 默认降级为最小可交付物，而非强行完成原任务。

---

## 异常分类与分层处置表

| 异常类 | 最可能含义 | 先处理层 | G 在回复时禁止做什么 | 默认降级产物最小字段 |
|---|---|---|---|---|
| **429** | 更可能是配额/限流/上游拥塞，而非本地业务逻辑已修复；现有源码中未见针对 429 的专门自动重试或 failover 判定 | **人工只读诊断层** 起步；若关键结果受阻，立即进入 **禁止宣告完成层** | 禁止把 429 说成 5xx；禁止把单次限流写成“系统坏了”；禁止在依赖该 provider 的情况下宣告验证完成 | `status`、`observed_error`、`impact_scope`、`next_retry_hint` |
| **5xx（尤其 502/503/504）** | 上游服务瞬态错误或代理层异常；源码已内建自动重试，失败后路由器还会做 failover | 先走 **代码内自动处理层**；若多轮后仍失败，再转 **人工只读诊断层** | 禁止无视已有 retry/failover，直接把 SOP 写成重复机制；禁止在自动处理未稳定前宣告已完成 | `status`、`observed_error`、`auto_handled`、`next_observation` |
| **连接失败** | 网络抖动、远端连接问题、协议层异常；源码已纳入 `ConnectError/NetworkError/RemoteProtocolError` 自动重试范围 | 先走 **代码内自动处理层**；重试耗尽后转 **人工只读诊断层** | 禁止把连接失败直接等同于 provider 永久不可用；禁止跳过“是否已自动重试/切换 provider”的核验 | `status`、`observed_error`、`attempts_seen`、`manual_check_hint` |
| **超时** | 可能是网络超时、上游响应过慢、或整体 wall-clock 超时；其中 `WallClockTimeoutError` 在源码中被明确标注为**不触发 failover** | 网络/请求超时先走 **代码内自动处理层**；若是 **WallClockTimeoutError** 或重试后仍不稳，则转 **人工只读诊断层**，关键任务进入 **禁止宣告完成层** | 禁止把所有超时都说成 provider 已宕机；禁止忽略“wall clock 超时不等于 provider 故障”这一边界；禁止在关键超时未复验时宣告通过 | `status`、`timeout_kind`、`observed_error`、`retry_or_wait_hint` |
| **间歇性成功 / 部分成功** | provider 或链路抖动；存在成功片段，但整体结果一致性不足，不能当成完整验证通过 | **人工只读诊断层** 起步；若关键结论仍不可判定，则进入 **禁止宣告完成层** | 禁止拿一次成功覆盖多次失败；禁止把部分成功包装成全量完成；禁止补写高风险结果来“凑闭环” | `status`、`evidence_mix`、`confidence`、`pending_step` |

---

## 快速判定规则

1. **先问：源码是否已自动处理？**
   - 若属于 `502/503/504`、连接失败、网络异常、请求超时等，默认先承认已有 retry / failover 在工作。
   - 不要把行为层文档写成“新增重试机制”的重复物。

2. **再问：自动处理后是否已形成稳定证据？**
   - 若没有，进入人工只读诊断层。
   - 输出最小诊断，不扩大结论。

3. **最后问：关键结果是否仍依赖失稳 provider？**
   - 若是，进入禁止宣告完成/禁止高风险写入层。
   - 只能交付最小降级产物，不交付“完成态”。

---

## 对 candidate 的核验结论

### 1. 现有 candidate 是否补到了空白？
**是，基本补到了行为层空白。**

原因：
- candidate 重点在“外部 provider 异常时先校正证据口径，再做最小离线分流”。
- 它约束的是 **回复行为、完成态宣告、风险写入边界、默认降级产物**。
- 这些内容在 `provider.py` / `provider_manager.py` 中没有以 SOP 形式出现；源码主要负责自动重试、切换、探活，不负责“G 对外怎么保守表述”。

### 2. 哪些内容与已有机制重叠？
有重叠，但主要是**边界承接**，不是完全重复：
- candidate 把 `429/5xx/网络失败/超时` 统称为触发条件，这与源码异常类型有交叉。
- 其中 **5xx、连接失败、超时** 与源码现有 retry / failover 机制直接重叠，不能再被表述成“缺了自动处理”。
- candidate 中“最小离线分流”若被误读成“绕过代码自动机制”，就会与现有实现重复；因此需要本卡补上“三层边界”，明确先后顺序。

### 3. 还缺的最小下一步是什么？
**最小下一步**：把该决策卡与 candidate 建立显式互链或在 candidate 中补一行引用，注明：
- `5xx/连接失败/部分超时` 先由源码自动处理；
- candidate 补的是自动处理失败后的**行为层 SOP**；
- `429`、`间歇性成功/部分成功` 更适合直接落入人工只读诊断与禁止完成宣告边界。

如果当前只允许最小推进，则**先新增本卡即可**，不必改 `.py`。

---

## 证据摘录

- `docs/lesson_provider_anomaly_minimal_offline_routing_candidate.md`
  - 已强调：不要误写未证实错误码；不要宣称“已完成验证/已完成交付”；provider 失稳时禁止高风险写入；默认只交付最小离线分流产物。
- `genesis/core/provider.py`
  - 普通/流式调用均 `retries = 5`。
  - `502/503/504` 自动重试。
  - `ConnectError/TimeoutException/NetworkError/RemoteProtocolError` 自动重试。
  - `WallClockTimeoutError` 注释：非 provider 故障，不应触发 failover。
- `genesis/core/provider_manager.py`
  - `ProviderRouter.chat()` 注释与实现都表明：对 5xx / 网络 / 超时等做 dynamic failover。
  - 首选 provider 有 recovery probe，恢复后切回。
  - `400` 直接上抛，不通过换 provider 解决。
- `docs/CASCADE_CONTEXT.md`
  - 将 `core/provider.py` 标为 httpx LLM 调用，`core/provider_manager.py` 标为 Failover 路由 + FreePoolManager，说明这两处本就承担自动处理职责。
