# Provider Failover 表述污染抽检报告

## 判尺来源
依据 `docs/provider_failover_service_equivalence_lesson.md`，本次抽检将以下表述视为高风险污染模式：

1. **把 failover success 表述成原目标完成**：替代 provider 跑通，只能先认定为“降级完成”或“替代路径成功”，不能直接上升为“原目标完成”。
2. **把 200 OK 表述成任务完成**：HTTP 200 只证明该请求成功返回，不等于当前任务、验证、交付已经完成。
3. **把替代 provider 成功表述成服务等价 / 原路径稳定**：如 `aixj -> deepseek` 成功，只能证明 fallback/failover 链路可用，不能据此推出原 provider 已恢复、替代服务已等价、原路径已稳定。

## 抽检范围与方法
- 优先抽检高风险载体：`docs/`、`runtime/`、运行产物落地文本。
- 关键词定点检索：`failover`、`fallback`、`200 OK`、`完成`、`稳定`、`等价`、`deepseek`、`aixj`、`provider`。
- 仅抽检 5 个样本，用于确认污染是否真实存在及主要载体。

## 抽检样本

### 样本 1
- **文件路径**：`docs/provider_failover_service_equivalence_lesson.md`
- **命中原句**：
  - `核心规则：如果结果是通过 failover/fallback 才得到，即使最终 200 OK，也只能先表述为“降级完成”或“替代路径成功”；除非关键属性等价已被确认，否则不能表述为“原目标完成”或“原路径稳定”。`
  - `例如本地可见过 aixj -> deepseek 后成功；这只能证明 fallback success，不能自动推出两者在能力、策略、配额、输出约束或外部契约上已服务等价。`
- **判定**：未命中
- **属于哪类模式**：N/A（这是判尺与纠偏文本，不是污染）
- **是否需要修正**：否

### 样本 2
- **文件路径**：`docs/provider_anomaly_429_runtime_appendix.md`
- **命中原句**：
  - `有，紧跟 https://api.deepseek.com/v1/chat/completions "HTTP/1.1 200 OK" | 该样本链路未中断，后续继续进入 G-Process`
  - `有，多次 deepseek 200 OK，流程继续到 Op/G 往返`
- **判定**：轻度命中
- **属于哪类模式**：容易把 **200 OK / failover 后继续运行** 近似表述为“任务已完成”或“链路已充分闭环”
- **说明**：该文档整体较克制，没有直接写“原目标完成”或“服务等价”，但多处把 `deepseek 200 OK` 与“流程继续”并列，容易被后续引用时误读为“事情已经完成”。
- **是否需要修正**：建议修正，补一句“仅说明替代路径继续推进，不代表任务完成或服务等价”。

### 样本 3
- **文件路径**：`runtime/autopilot.log`
- **命中原句**：
  - `12:26:08 [WARNING] ⚠️ Switching Provider: aixj -> deepseek`
  - `12:26:08 [INFO] 🔄 Failover Attempt: deepseek`
  - `12:26:08 [INFO] HTTP Request: POST https://api.deepseek.com/v1/chat/completions "HTTP/1.1 200 OK"`
  - `12:26:51 [INFO] ✅ Provider recovered: back to aixj`
- **判定**：中度命中
- **属于哪类模式**：把 **替代 provider 成功 / 切回首选 provider** 表述成 **原路径稳定或 provider 已健康**
- **说明**：日志中的 `Provider recovered` 只基于切回行为和一次后续请求，不足以支撑“原路径稳定”的强结论；同时 failover 后的 `200 OK` 也只证明该次请求返回成功。
- **是否需要修正**：建议修正日志话术，至少在对外引用时改写为“切回首选 provider / 观察到恢复迹象”，避免直接宣称 recovered。

### 样本 4
- **文件路径**：`runtime/genesis.log`
- **命中原句**：
  - `2026-03-25 08:42:21 [INFO] httpx: HTTP Request: POST https://aixj.vip/v1/chat/completions "HTTP/1.1 429 Too Many Requests"`
  - `2026-03-25 08:42:21 [INFO] httpx: HTTP Request: POST https://api.deepseek.com/v1/chat/completions "HTTP/1.1 200 OK"`
  - `2026-03-25 09:07:20 [INFO] genesis.core.provider_manager: ✅ Provider recovered: back to aixj`
- **判定**：中度命中
- **属于哪类模式**：
  - 把 **failover 后 200 OK** 误读为 **任务完成**；
  - 把 **重新切回 aixj** 误读为 **原路径稳定**。
- **说明**：这是运行时高频模式：`aixj 429` 后立刻 `deepseek 200 OK`，随后又出现 `Provider recovered`。从证据上更稳妥的说法应是“fallback success + 首选 provider 恢复迹象”，而不是“服务恢复稳定”。
- **是否需要修正**：建议修正，尤其是沉淀成报告或 LESSON 时应避免直接引用这些词作为结论。

### 样本 5
- **文件路径**：`docs/provider_anomaly_layered_decision_card.md`
- **命中原句**：
  - `在关键结果仍依赖失稳 provider 时宣告“已验证完成/已交付完成”`
  - `默认降级为最小可交付物，而非强行完成原任务`
- **判定**：未命中
- **属于哪类模式**：N/A（这是抑制污染的治理文本）
- **是否需要修正**：否

## 简短结论
- **是否已观察到历史表述污染**：是，已观察到真实存在，但当前更明显集中在**运行日志和附录式归纳文本**，不主要出现在治理性文档本身。
- **最常见的是哪一类**：最常见的是 **把 failover 后的 200 OK / 流程继续推进，当成更强的“任务完成”或“恢复稳定”信号**。其次是把切回首选 provider 的日志文案写得过强，如 `Provider recovered`。
- **下一步更适合什么**：更适合先做 **知识质量清洗**，尤其是统一历史文档/日志引用口径；继续新增 LESSON 的边际收益低于先清洗已存在的高风险表述。

## 不确定性
- 本次仅做 5 个样本抽检，能确认污染存在，但不能量化全仓占比。
- 运行日志中的“污染”有一部分属于**日志命名偏强**，未必等于作者主观判断错误；但它会显著影响后续总结和引用。
- 未扩大扫描到更多对话快照、外部导出材料和更深层运行产物，因此实际污染面可能大于本次观察结果。
