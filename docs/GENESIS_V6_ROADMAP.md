# GENESIS_V6_ROADMAP.md — 经验升华与连续参数化阻尼场

> 基调：PLS（点线面）符号库已被榨干。V6 并非推翻重建，而是将离散的、造成 Context 腐烂的“固态文本痕迹”，升华为连续的、不占用运行 Context 的“气态直觉阻尼场（神经网络权重）”。

---

## 一、 理论基础：信息相变与概率弯曲

在 V4 架构中，经验以离散的 Markdown `LESSON` 节点形式存储于 NodeVault 中，并在运行时拼凑进 Surface。由于符号的离散性，点库会单向无尽熵增，且 Context SNR（信噪比）随着运行次数增多快速坍塌。

V6 引入一个**外置的、可进行梯度更新的参数化小模型（MLP/Policy）**。它不存一个汉字，只存浮点数权重 $W$：
1. **输入 (State $s$)**：当前任务的 Embedding，以及当前微观执行状态的特征向量。
2. **输出 (Action Priors $P(a|s)$)**：一个 $N$ 维的概率分布向量，预测在当前状态下，调用哪些具体工具或激活哪些知识元信息的概率最大（势能最高）。
3. **空间弯曲**：小模型在运行时隐式地弯曲 Yogg 的概率空间。不合时宜的信息其概率在小模型输出中直接为 0，物理上被 100% 屏蔽，上下文保持绝对纯净。
4. **自然淘汰**：利用 L2 正则化（Weight Decay）实现自然的“蒸发”与“消融”，低频未验证节点自动淡出，长尾黄金经验依然在底层参数空间中隐式保留。

---

## 二、 阶段一：PLS 存量痕迹审计与数据编译

将 NodeVault 中的 400+ 个离散 Points 与 Traces 中的 Lines 熔炼为可供小模型进行梯度下降的 `[State_Vector, Target_Action_Logits]` 规范化训练集。

### 2.1 提取失败物理摩擦（Negative Signals）
从 `knowledge_nodes` 中筛选出 `usage_fail_count > 0` 且 `trust_tier != 'HUMAN'` 的节点。
* **State 映射**：提取任务 Title、Resolves 及 metadata 中的 `observed_environment_scope`，由本地 BGE-small-zh 编译为 $512$ 维向量（BAAI/bge-small-zh-v1.5 物理维度为 512，而其 base 版本为 768）。
* **Action 映射**：提取其 signature 中导致失败的具体 Action/Tool（例如 `shell`, `subprocess` 等）。

### 2.2 提取成功实证轨迹（Positive Signals）
读取本地 `runtime/traces.db` 中的执行成功的完整路径（从 Round 1 的先验规划到 Round N 的物理成功终点序列），作为正向奖励元组。

### 2.3 编译编译器
新建文件 `@/home/chendechusn/Genesis/Genesis/genesis/v6/dataset_compiler.py`，实现数据管道：
```python
# 拟实现之数据结构
import numpy as np

def compile_pls_bedrock_to_dataset(vault, traces_db) -> tuple[np.ndarray, np.ndarray]:
    """
    读取 sqlite 痕迹，转换为小脑训练的 [X_state, Y_target] 矩阵。
    X_state.shape = (N, 512)
    Y_target.shape = (N, 39)  # 39维对应元信息维度或 Action Vocabulary
    """
    pass
```

---

## 三、 阶段二：手搓参数化小脑 (Continuous Parameter Space)

在本地实现一个完全不依赖外部庞大框架（如 PyTorch）、基于 NumPy 的轻量参数化 Policy 模型。

### 3.1 网络结构设计
新建文件 `@/home/chendechusn/Genesis/Genesis/genesis/v6/brain.py`：
* **Input Layer**: $512$ 维（State Feature Vector）。
* **Hidden Layer**: $128$ 维（ReLU 激活）。
* **Output Layer**: $39$ 维（映射 39 维元信息 Signature 激活偏好，或 12+ 物理工具 Vocabulary 激活权重）。
* **参数量**：$512 \times 128 + 128 \times 39 \approx 70,000$ 个浮点数。运行内存占有 `< 5MB`，在 CPU 上前向推理时间 `< 1ms`。

### 3.2 引入物理半衰期 (Weight Decay)
在反向传播中显式织入 L2 正则化：
$$W_{t+1} = (1 - \eta \lambda) W_t - \eta \frac{\partial L}{\partial W}$$
确保长期未被激活和验证的连接权重自发向 0 衰减，废旧节点自发“消融”。

---

## 四、 阶段三：无感织入与闭环纠偏

将小模型无缝作为“概率门控”织入 `V4Loop` 执行主时序中，不改变 G/Op 核心架构，不增加任何多余的 LLM 串行时延。

```
                    【V6 连续参数化纠偏动力学时序】

V4Loop.start_round()
   │
   ├─► [1. 编码 State] ──► 任务/上下文文本 ──► BGE ──► s_vector (512)
   ├─► [2. 脑部前向]   ──► brain.forward(s_vector) ──► 39维 logits
   │                                                      │ (硬阈值过滤)
   ├─► [3. Surface 过滤] ◄────────────────────────────────┘
   │      └─► 仅拉起 logits > threshold 的 LESSON/PATTERN 节点
   │
   ├─► [4. 沙箱实证]   ──► 正常进行重型 ReAct 循环 ──► 物理反馈轨迹 Line_actual
   │
   └─► [5. C-Phase]    ──► 差分计算 Loss = Distance(Round_1_draft, Line_actual)
          └─► brain.backward(loss) ──► 瞬时更新 $W$ 矩阵
```

### 4.1 隐式空间弯曲 (Inference Gating)
在 `@/home/chendechusn/Genesis/Genesis/genesis/v4/loop.py:531-648` 拼凑 Surface 之前：
1. 拦截任务 BGE Embedding，通过 `brain.py` 得到 39 维激活概率分布。
2. 在 `surface.py` BFS 扩散时，仅允许扩散至对应维度概率大于阈值（如 $0.1$）的知识节点，将不合时宜的节点在进入上下文前 100% 屏蔽。

### 4.2 差分误差回传 (Loss Backprop)
在 C-Phase 阶段：
1. **无感直觉**：ReAct 的 `Round 1` 即为系统无物理阻力时的概率直觉。
2. **实证轨迹**：随着物理报错、工具重试，产生最终成功的轨迹 `Round N`。
3. **Loss 计算**：计算 `Round 1` 到 `Round N` 之间的编辑距离或物理重试次数作为 Loss。
4. **梯度下降**：在 C-Phase 结束时，在本地瞬间调用 `brain.backward(loss)`，将本次摩擦力信息反向传播进参数矩阵 $W$。

---

## 五、 客观物理成本与局限 (Engineering Costs & Limits)

* **网络时延成本**：**0 增加**。所有计算在宿主机 CPU 上本地瞬时（<50ms）完成。
* **内存/计算成本**：**极低**。内存占用 <5MB，Yoga 8G 笔记本完全无感知。
* **开发复杂度**：**高**。需要手搓完备的 NumPy 前向/反向传播逻辑，且必须维护一套严格的工具/元信息 Vocabulary 映射词表。
* **物理瓶颈**：由于使用远端闭源 API，无法真正改写最后一层 Logits。小模型输出的概率阻尼最终仍需翻译为一两句“高浓度行动指南 Prompt”输入给 LLM。
