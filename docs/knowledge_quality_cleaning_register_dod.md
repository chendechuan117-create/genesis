# Docs Knowledge Cleaning Register / DoD

## 目的
用一页极简登记，固化本轮及前几轮 docs 知识清洗现状：哪些高风险表述已清洗，哪些仅作抽检证据保留，哪些仍是待处理边界源；并给出本轮可宣告闭环的最小完成定义（DoD）。

## 清洗登记

| 文件路径 | 当前状态 | 风险类型 | 允许表述边界 / 限定语摘要 | 备注 |
|---|---|---|---|---|
| `docs/provider_anomaly_429_runtime_appendix.md` | 已清洗 | 把 `200 OK` / `流程继续` / failover 后成功，误抬升为任务完成、原 provider 恢复稳定、服务等价 | 文内已追加限定：`200 OK` 仅证明该次请求成功返回；failover success 仅证明替代路径请求成功/流程继续，不能单独推出 `task completion`、`provider recovery`、`service equivalence` | 文件存在，已见多处限定注与统一修订说明 |
| `docs/log_reference_downgraded_claims_card.md` | 已清洗 | 日志引用时把局部成功信号直接写成强结论 | 明确要求：`200 OK` 仅说明该次请求返回；`failover success` 仅说明替代路径成功；`Provider recovered` 需降级为恢复迹象；`流程继续` 不等于验证通过 | 文件存在；属治理规范卡 |
| `docs/lesson_provider_anomaly_minimal_offline_routing_candidate.md` | 已清洗 | LESSON 候选中把一次成功样本、切回首选或流程继续写成“恢复稳定/已完成” | 文内已追加限定：恢复稳定不能仅由一次 `200 OK`、一次 failover success、一次切回首选 provider 或“流程继续”判定；本地 `200 OK` 样本也不能单独推出问题已解决、任务已完成、服务等价 | 文件存在；属优先清洗的下游复述链 |
| `docs/provider_failover_service_equivalence_lesson.md` | 已清洗 | 把 fallback success 混同于 task completion / service equivalence | 已明确四层状态：`provider health` / `fallback success` / `task completion` / `service equivalence`；failover 后即使 `200 OK` 也只能先落在降级完成或替代路径成功 | 文件存在；可作为判尺来源 |
| `docs/provider_failover_equivalence_contamination_spotcheck.md` | 保留样本 | 抽检报告内保留高风险原句，用于证明污染真实存在 | 允许保留命中原句，但必须把其定位为抽检证据，不可被再次摘要成结论；后续引用时应回到判尺或已清洗文本 | 文件存在；本轮按“抽检样本/保留高风险原句用于证据展示，暂不清洗”登记 |
| `docs/provider_anomaly_layered_decision_card.md` | 待处理边界源 | 决策卡总体是治理文本，但仍是后续引用的重要边界源，需要继续确认是否补充与本轮清洗登记/例外的互链 | 当前可用边界：关键结果仍依赖失稳 provider 时，不得宣告已验证完成/已交付完成；默认降级为最小可交付物，而非强行完成原任务 | 文件存在；本轮登记为“待处理边界源”，不是高风险污染样本 |

## DoD（本轮 docs 知识清洗闭环的最小完成定义）
- [x] 高风险入口已标记：至少覆盖 appendix / lesson / lesson-like card / 规范卡 / spotcheck / decision card 这几类入口。
- [x] 对已清洗文档，限制语已落文：`200 OK`、failover success、切回首选 provider、流程继续等，只能支撑局部请求成功、替代路径成功或恢复迹象，不能单独推出任务完成、稳定恢复、服务等价。
- [x] 对未清洗但需保留的文本，已登记例外：如 `docs/provider_failover_equivalence_contamination_spotcheck.md` 作为抽检样本，允许保留高风险原句用于证据展示。
- [x] 原始日志未改：`runtime/` 下日志只作为证据源，不纳入本轮 docs 清洗写入。
- [x] `genesis/` 代码未改：本轮仅做 docs 治理登记，不修改实现逻辑。
- [x] 后续引用可追溯：后续若引用“已清洗/保留样本/待处理边界源”结论，应能回溯到本登记与对应源文件。
- [x] 若发现目标文件不存在，已如实登记而不猜测。当前本登记覆盖的 6 个目标文件均已核验存在，无缺失项。
