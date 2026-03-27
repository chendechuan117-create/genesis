# Provider 429 运行时附录

## 样本表

| 样本 | 日志位置 | provider / URL | 相邻唯一标记 | 是否出现重试迹象 | 是否出现切换 provider/failover 迹象 | 是否出现后续成功（如 200 OK） | 是否最终中断/报错退出 |
|---|---:|---|---|---|---|---|---|
| S1 | `runtime/genesis.log:5889-5893` | `aixj` / `https://aixj.vip/v1/chat/completions` | `USAGE_LIMIT_EXCEEDED` + `DAILY_LIMIT_EXCEEDED` | 未见同 provider 429 后退避重试；更像直接走下一 provider | 明确有：`Switching Provider: aixj -> deepseek`，随后 `Failover Attempt: deepseek` | 有，紧跟 `https://api.deepseek.com/v1/chat/completions "HTTP/1.1 200 OK"` | 该样本链路未中断，后续继续进入 G-Process。**限定注：此处 `200 OK` 仅能证明 failover 后替代 provider 上的该次请求成功返回，且流程继续推进；不能单独推出原 provider 已恢复稳定、原目标任务已完成，或两条服务路径已等价。** |
| S2 | `runtime/genesis.log:6891-6893`（并参考 `6905-6925`） | `aixj` / `https://aixj.vip/v1/chat/completions` | 同窗口内多次 `aixj 429` 与 `deepseek 200 OK` 交替出现 | 未见 429 专门 backoff 文本；表现为后续再次请求仍命中 aixj 429 | 有，但该段未打印显式 `Switching Provider`；从 `aixj 429` 后立刻 `deepseek 200 OK` 看，运行时疑似经通用 failover 兜底 | 有，多次 `deepseek 200 OK`，流程继续到 Op/G 往返。**限定注：这里的“成功”应降级理解为 fallback success / 替代路径请求成功，不等于该大流程中的任务验收已通过，也不等于原 aixj 路径恢复稳定或与 deepseek 已证服务等价。** | 未立即退出；但同一大流程后续出现 `Op-Process reached max iterations.`，非直接 429 致命退出证据 |
| S3 | `runtime/genesis.log:7070-7072`（并参考 `7080-7081`） | `aixj` / `https://aixj.vip/v1/chat/completions` | 位于 `Multi-G blackboard injected into G context` 之后 | 未见同 provider 429 后的专门重试/退避 | 有迹象：`aixj 429` 后紧跟 `deepseek 200 OK` | 有，`deepseek 200 OK`，且后续继续 `G-Process dispatched via tool call`、进入 `Op-Process`。**限定注：这最多说明替代路径上的请求成功并带来后续流程推进；若缺少任务验收证据与等价性证据，不能把该样本上升表述为“任务完成”“原路径稳定”或“服务等价”。** | 该样本链路未中断 |

## 静态对照

### 1) 显式 429 专门处理
- `docs/CASCADE_CONTEXT.md`：未见 429 / Too Many Requests / quota 专门处理描述。
- `genesis/core/provider.py`：未见 `429`、`Too Many Requests`、`rate limit`、`quota` 的专门分支；可直接看到的显式重试只覆盖：
  - `400`（特定 `skip_content_type` 情况）`provider.py:251-258, 483-501`
  - `502/503/504` `provider.py:259-266, 502-508`
  - 网络/超时异常 `provider.py:270-279, 512-520`
- `genesis/core/provider_manager.py`：未见显式 `429` 条件判断。

### 2) 通用异常路径可能间接兜底
- `genesis/core/provider.py:267-269, 509-511`
  - 对未命中特判的 HTTP 状态统一抛出 `Exception(f"API Error ({status}) ...")`。
- `genesis/core/provider_manager.py:190-214`
  - 捕获 provider 异常后，除 `400` / `invalid_request_error` 外，会进入通用 failover 路径。
  - 注释写明“仅对 5xx / 网络 / 超时等服务端故障”，但代码层面未见只允许这些类型的硬判断；因此 429 抛出的通用异常在运行时看起来也会落入 failover。
- `docs/CASCADE_CONTEXT.md:153-154`
  - 只写了通用“failover 后每 60s 尝试恢复首选 provider”“流式/非流式均 3 次，5xx 可重试”；未写 429 专门策略。

### 3) 未见证据
- 未见 429 专门 backoff / 指数退避文本。
- 未见 429 后按 `Retry-After` 或 quota 类型做差异化处理的文本。
- 在所抽样本附近未见 trace id。

## 结论
**未见专门处理，但运行时疑似被通用路径间接兜底**。

依据仅限本次附录补证：
- 静态上未见 429 专门分支；
- 运行时多处出现 `aixj 429` 后紧接 `deepseek 200 OK`，至少一处同时伴随明确 `Switching Provider` / `Failover Attempt` 文本；
- 但同 provider 的重试/backoff 证据仍不清晰，因此不能上升为“有专门处理”。

**修订说明：本附录中的 `200 OK`、`流程继续`、`切换成功` 等样本事实，仅可支持 `request success` 或 `fallback success` 层面的判断；除非另有任务验收证据、原 provider 恢复稳定证据、以及关键属性等价证据，否则不能单独推出 `task completion`、`provider recovery` 或 `service equivalence`。尤其是 failover 后的 `200 OK`，仅能证明替代路径上的请求成功，不能单独证明原目标完成、原 provider 稳定或服务等价。**

## 风险
- 429 若来自长期 quota / daily limit，用通用 failover 虽可短时续跑，但不能解决根因；若备选 provider 不可用，仍可能持续失败。
- 因缺少 429 专门 backoff / `Retry-After` 处理，可能造成高频无效请求与日志噪声。
- `provider_manager.py` 注释与代码行为之间存在边界不够清晰之处：注释说 failover 仅针对 5xx/网络/超时，但运行时样本显示 429 也可能被通用异常路径带入 failover。
