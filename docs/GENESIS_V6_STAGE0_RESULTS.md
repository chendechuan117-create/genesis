# Genesis V6 Stage 0 实测结果

> 结论先行：PLS 痕迹中存在可学习信号，但当前只足以支持 **signature intuition shadow mode**。不支持直接训练/接入完整 V6 小模型，更不支持 hard gate。

---

## 一、执行内容

本轮只做只读实验：

1. 创建并运行 `genesis/v6/audit_pls_learnability.py`。
2. 创建并运行 `genesis/v6/baseline_pls_predictability.py`。
3. 不修改 `V4Loop`、`SurfaceExpander`、`NodeVault`、C-Phase 或任何运行时决策逻辑。
4. 不训练模型，不写权重，不创建数据库表。

---

## 二、Stage 0 审计结果

命令：

```bash
python3 genesis/v6/audit_pls_learnability.py
```

审计决策：

```text
PROCEED_TO_BASELINE_EXPERIMENT
```

关键结果：

| 指标 | 结果 | 判断 |
|---|---:|---|
| NodeVault 节点数 | 857 | 可用 |
| 有 embedding 节点 | 840 / 857 = 98.0% | 很好 |
| 有可解析 signature 节点 | 850 / 857 = 99.2% | 很好 |
| usage feedback 节点 | 525 / 857 = 61.3% | 可用但不稠密 |
| embedding 维度 | 512 | 与 BGE-small-zh 对齐 |
| traces 数量 | 6686 | 充足 |
| tool call spans | 42947 | 充足 |
| 非空 tool label | 41738 / 42947 = 97.2% | 很好 |
| error tool spans | 0 | 失败感知不可验证 |
| 可训练单元估算 | 3978 | 超过最低门槛 |

初步判断：

- **Point 层质量很好**：NodeVault 的 embedding 与 signature 覆盖率足够高。
- **Line 层足够大但失败信号缺失**：trace/tool 数据量足够，但 `spans.error` 没有工具失败样本。
- **Surface 接入仍不可做**：审计只证明“可进入 baseline”，不证明可以影响运行时。

---

## 三、Baseline 可预测性结果

命令：

```bash
python3 genesis/v6/baseline_pls_predictability.py
```

实验决策：

```text
PROCEED_TO_SHADOW_DESIGN
```

### 3.1 Signature 预测

总体：

| 指标 | 结果 |
|---|---:|
| signature samples | 849 |
| train/test | 680 / 169 |
| evaluated fields | 9 |
| fields with top-1 gain | 5 |
| fields with top-k gain | 2 |
| avg top-1 gain | +13.6% |
| avg top-k gain | +2.7% |

最强信号：

| 字段 | frequency@1 | NB@1 | gain@1 | 解释 |
|---|---:|---:|---:|---|
| `error_kind` | 34.7% | 76.0% | +41.3% | 明显可学 |
| `framework` | 34.5% | 72.6% | +38.1% | 明显可学 |
| `task_kind` | 49.4% | 68.2% | +18.8% | 可学 |
| `runtime` | 60.4% | 77.7% | +17.3% | 可学 |
| `target_kind` | 43.1% | 56.9% | +13.9% | 可学 |

弱或不应优先建模的字段：

| 字段 | 问题 |
|---|---|
| `validation_status` | `validated` 占比过高，频率基线已接近 94% |
| `environment_scope` | `local` 占比过高，频率基线已超过 82% |
| `language` | top-1 低于频率基线 |
| `os_family` | top-k 低于频率基线 |

结论：

- PLS 文本与 signature 之间存在明显可学习结构。
- 第一阶段不应训练“39 维全输出脑”，而应先做 **选择性 signature prior**。
- 候选目标应限制为：`error_kind`、`framework`、`task_kind`、`runtime`、`target_kind`。

### 3.2 Tool 预测

总体：

| 指标 | 结果 |
|---|---:|
| tool samples | 3128 |
| train/test | 2503 / 625 |
| top-1 gain | +1.0% |
| top-k gain | -2.7% |

结论：

- 当前 tool 预测不值得作为 V6 小模型第一目标。
- tool 序列更像执行策略/流程习惯，不是单纯由用户输入决定。
- 后续如果研究 tool prior，应使用 trace step context，而不是只用 user input。

---

## 四、客观结论

当前证据支持：

1. **继续 V6，但缩小目标**
   - 做 signature intuition，不做完整行为脑。

2. **进入 Shadow Mode 设计**
   - 只记录预测，不影响 Surface、工具选择或 prompt。

3. **不进入运行时接管**
   - 现在还不能 soft rerank，更不能 hard gate。

4. **不以 tool prediction 为第一突破口**
   - tool 线 baseline 弱，暂时搁置。

5. **不做 failure-aware learning**
   - 因为 `error_tool_spans=0`，真实工具失败标签缺失。

---

## 五、下一步：Signature Shadow Mode

下一阶段最小目标：

> 对每次输入预测 `error_kind/framework/task_kind/runtime/target_kind` 的 top-k prior，记录到独立 JSONL；任务结束后离线对比 C-Phase 产出的 signature 与 NodeVault 新节点 signature。

最小设计：

- 新脚本或模块只做预测与日志。
- 日志放在 `runtime/v6_shadow_predictions.jsonl`。
- 不写 NodeVault。
- 不改 Surface 排序。
- 不进入 prompt。
- 不启动常驻进程。

每条 shadow 记录至少包含：

```json
{
  "trace_id": "...",
  "user_input_preview": "...",
  "predictions": {
    "task_kind": [["debug", 0.62], ["audit", 0.21]],
    "runtime": [["python", 0.73], ["node", 0.14]]
  },
  "baseline": {
    "task_kind": [["debug", 0.36], ["configure", 0.18]]
  },
  "created_at": "..."
}
```

通过门槛：

- Shadow top-3 命中率稳定高于频率 baseline。
- 高置信错误率可控。
- 不出现 critical miss。
- 预测能解释为实际 signature prior，而不是只复述高频标签。

---

## 六、暂缓事项

以下事项暂缓：

- NumPy MLP。
- `SurfaceExpander` rerank。
- `V4Loop` 接入。
- hard gate。
- tool prior。
- failure-aware prior。
- 权重持久化。

---

## 七、当前决策

当前 V6 的正确下一步不是“小模型实现”，而是：

```text
Signature Shadow Mode
```

如果 Shadow Mode 继续证明有效，再考虑最小化 soft rerank；如果 Shadow Mode 无法稳定超过 baseline，则 V6 停在审计/分析层，不进入系统复杂度扩张。
