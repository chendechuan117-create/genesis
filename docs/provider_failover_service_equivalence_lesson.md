# Provider Failover 与服务等价边界 LESSON

需明确区分四层状态：`provider health`（某 provider 是否健康）、`fallback success`（是否已切到替代 provider 并拿到结果）、`task completion`（当前轮任务是否产出可交付结果）、`service equivalence`（替代路径是否满足原目标的关键属性）。

**核心规则：如果结果是通过 failover/fallback 才得到，即使最终 200 OK，也只能先表述为“降级完成”或“替代路径成功”；除非关键属性等价已被确认，否则不能表述为“原目标完成”或“原路径稳定”。**

例如本地可见过 `aixj -> deepseek` 后成功；这只能证明 fallback success，不能自动推出两者在能力、策略、配额、输出约束或外部契约上已服务等价。未证等价时，应保守落在降级完成边界。