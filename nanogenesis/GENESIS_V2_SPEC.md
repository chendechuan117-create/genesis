# Genesis V2 — 工程交接文档

> **状态：持续演进中**
> 最后更新：2026-03-01（V2.1）
> 作者：Genesis AI / Cascade

---

## 一、项目背景与目标

### 1.1 问题陈述

Genesis V1 是一个以 OpenClaw 为基础改造的聊天驱动 Agent。其核心缺陷：
- 每次对话从零开始，没有跨会话的可积累知识
- Ouroboros Loop 将"决策"和"执行"耦合在同一个上下文中，LLM 既是司令又是士兵，状态污染严重
- 工具选择完全依赖 LLM 即兴发挥，无法事后验证或优化
- 失败后只能"继续聊"，没有结构化的重组机制

### 1.2 V2 目标

将 Genesis 重构为**本地 AI 化身框架**：

- **可积累**：知识以结构化形式持久存储在 SQLite，跨会话复用
- **可验证**：每个执行单元（op）的输入/输出均为 typed dataclass，可用代码检查
- **低幻觉**：Manager 从车间取事实，不靠 LLM 凭空生成环境信息
- **可恢复**：失败最多重组 3 次，带熔断机制，不死循环

---

## 二、核心设计原则

| # | 原则 | 含义 |
|---|------|------|
| 1 | **结构化管道** | Manager↔OpExecutor 的接口是 typed dataclass，不是字符串。不允许用自然语言传递"指令" |
| 2 | **AI 自主决策** | Manager 用 LLM 选工具/事实/格式，代码里不写 `if task_type == X` 的硬编码分支 |
| 3 | **按需装配** | Manager 先拿元数据索引（名字+tags），再按 ID 加载内容。不一次性把所有工具塞进 context |
| 4 | **持久化知识** | 车间是 SQLite，不是对话历史。每条记录有时间戳，可区分"已验证事实"和"当次猜测" |
| 5 | **基础设施不动** | `loop.py` / `registry.py` / `provider_manager.py` / `entropy.py` 保留。认知层在上面建 |
| 6 | **熔断而非死循环** | op 最多重组 3 次，entropy 检测异常则立即熔断上报，不自作主张继续 |

---

## 三、系统架构

### 3.1 组件层次

```
┌──────────────────────────────────────────────────────────┐
│                      用户入口层                            │
│  web_ui.py (Streamlit)   │   cli.py (终端)               │
└─────────────────┬────────────────────────────────────────┘
                  │ agent.process(user_input, use_v2=True)
┌─────────────────▼────────────────────────────────────────┐
│                    genesis/agent.py                       │
│  NanoGenesis  —  V2 薄封装，V1 Ouroboros Loop 保留备用     │
└─────────────────┬────────────────────────────────────────┘
                  │ manager.process(user_intent)
┌─────────────────▼────────────────────────────────────────┐
│              genesis/core/manager.py                      │
│  Manager（厂长）                                           │
│  1. 调 workshops.seed_from_registry() 同步工具             │
│  2. 取车间索引（轻量元数据）                                │
│  3. LLM 决策：选 tool_ids / fact_ids / format / strategy  │
│  4. 调 op_assembler.build_op_spec() 组装 OpSpec           │
│  5. 调 executor.execute(spec) 执行                        │
│  6. 成功→ _learn_from_result()；失败→ 重组/熔断            │
└──────┬──────────────────────────────────────┬────────────┘
       │ build_op_spec()                      │ execute(OpSpec)
┌──────▼──────────┐                 ┌─────────▼──────────────┐
│ op_assembler.py │                 │   op_executor.py        │
│ 纯函数          │                 │   OpExecutor            │
│ selection dict  │                 │   - 隔离 ToolRegistry   │
│ + workshops     │                 │   - 新鲜 context（无历史）│
│ → OpSpec        │                 │   - loop.py ReAct 引擎  │
└─────────────────┘                 │   - entropy 检测        │
                                    │   → OpResult            │
                                    └────────────────────────┘
       │ 读/写                                │ 读
┌──────▼──────────────────────────────────────▼────────────┐
│              genesis/core/workshops.py                    │
│  WorkshopManager  —  SQLite 持久化知识库                   │
│  tool_workshop │ known_info_workshop                      │
│  metacognition_workshop │ output_format_workshop          │
│  capability_workshop（执行校准，AI 原生元认知）             │
│  pending_lessons（待审队列）                               │
└──────────────────────────────────────────────────────────┘
```

### 3.2 完整执行流

```
用户: "帮我整理桌面代码项目"
  │
  ▼ agent.process(use_v2=True)
  │
  ▼ manager.process()
    │
    ├─0─ _decide_route(intent, context)  ← 厂长自主路由
    │    LLM 判断：用户在请求执行某事，还是在交流/陈述？
    │    → "chat" : 直接 LLM 回复，不走 OpSpec 流程，return
    │    → "task" : 继续以下步骤
    │
    ├─1─ workshops.seed_from_registry(registry)
    │    → 把 ToolRegistry 里的工具同步到 tool_workshop
    │
    ├─2─ LLM 组装决策（JSON 输出）
    │    输入: tool_index + fact_index + formats + patterns + capability_profile
    │    输出: {tool_ids, fact_ids, format_name, strategy_hint, expected_output}
    │    capability_profile 告知各工具历史可靠性，LLM 据此权衡工具选择
    │
    ├─3─ build_op_spec(objective, selection, workshops)
    │    → 按 ID 加载完整工具/事实/格式，组装 OpSpec
    │
    ├─4─ executor.execute(spec)
    │    │
    │    ├─ 构建隔离 ToolRegistry（只含 spec.tool_ids）
    │    ├─ 构建空白 context（无历史，无 Genesis 人格）
    │    ├─ loop.run(instruction)  ← ReAct 引擎
    │    │    每次工具调用后发出 tool_result 回调，记录实际输出
    │    │    system_task_complete → 成功退出
    │    │    system_report_failure → 失败退出
    │    │    [STRATEGIC_INTERRUPT] → entropy 熔断
    │    └─ 返回 OpResult（tool_outputs 含 {tool, args, result}）
    │
    ├─5─ _update_capability_calibration()  ← 无论成败都执行
    │    纯统计，无 LLM：检查每个工具的 result 是否含错误信号
    │    → capability_workshop.update(tool, succeeded, failure_reason)
    │
    ├─6a─ 成功: _learn_from_result()
    │     │
    │     ├─ 路径 A: _extract_execution_facts(tool_outputs)
    │     │   LLM 只从工具字面返回值提取事实（禁止推断）
    │     │   → workshops.add_verified_fact() → 直接写入 known_info (confidence=1.0)
    │     │
    │     └─ 路径 B: _extract_inference_lessons(intent, spec, result)
    │         LLM 从任务摘要推断策略模式
    │         → workshops.apply_lesson() → 全部进 pending_lessons（待人工 approve）
    │
    └─6b─ 失败: 重组（最多 3 次）
          第 N+1 次 assemble_op 携带上次 error，LLM 调整选择
          第 3 次仍失败 → circuit_broken=True，上报用户
```

---

## 四、文件清单与职责

### 4.1 V2 新增文件（认知层）

| 文件 | 职责 | 关键函数/类 |
|------|------|------------|
| `genesis/core/contracts.py` | 定义所有跨组件接口的 typed dataclass | `OpSpec`, `OpResult` |
| `genesis/core/workshops.py` | 四车间 SQLite 存储、CRUD、lesson 机制、冷启动扫描 | `WorkshopManager`, `ToolEntry`, `FactEntry`, `PatternEntry`, `FormatEntry`, `WorkshopLesson` |
| `genesis/core/op_assembler.py` | 纯函数：selection dict + workshops → OpSpec | `build_op_spec()`, `describe_op_spec()` |
| `genesis/core/manager.py` | 厂长核心逻辑：LLM 决策 + 熔断循环 + lesson 提取 | `Manager` |
| `genesis/core/op_executor.py` | 隔离执行单元：OpSpec → loop.py → OpResult | `OpExecutor`, `_SystemReportFailureTool` |

### 4.2 V2 修改文件

| 文件 | 修改内容 |
|------|---------|
| `genesis/agent.py` | 新增 `_process_v2()` 和 `review_workshop_lessons()`；`process()` 增加 `use_v2=True` 参数；V1 Ouroboros Loop 保留为 `use_v2=False` 路径 |

### 4.3 基础设施层（不动）

| 文件 | 职责 |
|------|------|
| `genesis/core/loop.py` | ReAct 引擎：reasoning → tool call → observation 循环 |
| `genesis/core/registry.py` | 工具注册、动态加载、依赖安装 |
| `genesis/core/provider_manager.py` | LLM 提供商故障转移（DeepSeek → OpenRouter → OpenAI）|
| `genesis/core/entropy.py` | 状态哈希检测，防止工具调用死循环 |
| `genesis/core/context.py` | context 构建，`build_stateless_messages()` 被 OpExecutor 使用 |
| `genesis/core/factory.py` | 依赖注入工厂，现已自动初始化 V2 组件 |

### 4.4 数据库文件

```
~/.nanogenesis/workshops.sqlite   # 车间数据（工具/事实/模式/格式/pending_lessons）
~/.nanogenesis/brain.sqlite       # 任务树、会话历史（V1 遗留，V2 未使用）
```

---

## 五、接口规格

### 5.1 OpSpec（Manager → OpExecutor）

```python
# genesis/core/contracts.py
@dataclass
class OpSpec:
    objective: str           # 此次 op 的具体目标（来自用户意图，可细化）
    tool_ids: List[str]      # 工具名称列表，必须在 tool_workshop 中存在
    context_facts: List[str] # 已格式化的事实字符串，如 "os_name: Linux"
    output_schema: Dict[str, Any]  # 从 output_format_workshop 加载的 JSON schema
    strategy_hint: str       # 来自 metacognition_workshop 的策略简述
    expected_output: str     # 成功标准描述，用于 OpResult.matched_expected 判断
    max_iterations: int = 5  # op 内部 ReAct 最大迭代次数（硬上限 = max_iterations * 2.5）
    attempt_number: int = 1  # 当前是第几次重组（1~3），Manager 传入
```

### 5.2 OpResult（OpExecutor → Manager）

```python
@dataclass
class OpResult:
    success: bool            # True = 任务完成（system_task_complete 被调用）
    matched_expected: bool   # True = 输出符合预期格式（当前等同于 success）
    tool_outputs: List[Dict] # [{tool: str, args: dict, result: str|None}, ...] 含实际执行结果
    final_output: Any        # {"summary": str} 或 None（失败时）
    attempt_number: int = 1  # 对应 OpSpec.attempt_number
    error: Optional[str] = None          # 失败原因
    entropy_triggered: bool = False      # True = 检测到死循环，立即熔断
    tokens_used: int = 0     # 本次 op 消耗 token 数
```

### 5.3 WorkshopLesson（学习反馈）

```python
@dataclass
class WorkshopLesson:
    lesson_type: str         # "new_fact" | "correction" | "new_pattern"
    target_workshop: str     # "known_info" | "metacognition"
    content: Dict[str, Any]  # 依 lesson_type 不同而异（见下方）
    confidence: float        # 0.0~1.0。仅用于排序优先级，所有 lesson 均进 pending_lessons 队列

# content 结构规范：
# new_fact:    {"key": str, "category": str, "value": str}
# correction:  {"key": str, "value": str}        # key 必须已存在
# new_pattern: {"pattern_name": str, "context_tags": list, "approach": str}
```

### 5.4 Manager.process() 返回值

```python
# 对话回复（Manager 判断为 chat）
{
    "success": True,
    "output": {"summary": str},   # 直接 LLM 回复文本
    "response": str,
    "path": "v2_chat",           # 区分于 task 路径
    "elapsed": float,
}

# 任务成功
{
    "success": True,
    "output": {"summary": str},   # op 完成摘要
    "response": str,              # 同 output.summary，兼容 web_ui.py
    "tokens_used": int,
    "attempts": int,              # 实际使用了几次重组
    "elapsed": float,             # 秒
    "path": "v2",
    # 可选（有积压时出现）：
    "pending_lessons": int,
    "pending_lessons_hint": str,
}

# 失败（熔断）
{
    "success": False,
    "output": None,
    "response": str,              # 错误描述，兼容 web_ui.py
    "error": str,
    "circuit_broken": True,
    "message": "已达最大重试次数（3），需要用户介入",
    "elapsed": float,
    "path": "v2",
}
```

---

## 六、车间系统详述

### 6.1 五车间说明

#### tool_workshop — 工具注册表
- **内容**：所有可被 OpExecutor 调用的工具
- **来源**：启动时由 `WorkshopManager.seed_from_registry(registry)` 从 `ToolRegistry` 同步
- **Manager 看到的**：`[{name, tags, summary}]`（`get_tool_index()` 返回）
- **OpExecutor 收到的**：`tool_ids: List[str]`，只加载指定工具

#### known_info_workshop — 已知事实库
- **内容**：键值对形式的环境事实和领域知识
- **冷启动**：首次初始化自动写入 15 条系统信息（OS、Python、工具路径等）
- **执行验证写入**：op 成功后，`_extract_execution_facts()` 从工具字面返回值提取事实，经 `add_verified_fact()` 直接写入（confidence=1.0，绕过待审队列）
- **LLM 推断写入**：通过 `apply_lesson()` 的 `new_fact`，一律进 pending_lessons 待审
- **Manager 看到的**：`[{id, key, category, value_preview}]`（`get_fact_index()` 返回）

#### metacognition_workshop — 策略模式库
- **内容**：解题经验，如"文件系统操作前先 ls 确认路径"
- **来源**：op 成功后 LLM 提取 `new_pattern` lesson 写入
- **Manager 使用方式**：`search_patterns(intent, limit=2)` 语义匹配，注入 `strategy_hint`

#### capability_workshop — 执行校准库（AI 原生元认知）
- **内容**：每个工具的历史执行统计（调用次数、成功率、最近失败摘要）
- **来源**：每次 op 后（无论成败）由 `_update_capability_calibration()` 纯统计写入，无 LLM 介入
- **Manager 使用方式**：`get_capability_profile()` 返回可靠性列表，注入 assembly prompt，引导 LLM 优先选择可靠工具
- **本质**：AI 通过执行经验积累的自我认知，不是人类规则灌入

| 字段 | 说明 |
|------|------|
| `capability` | 工具名（主键）|
| `total_calls` | 历史调用总次数 |
| `successes` | 成功次数 |
| `reliability` | successes / total_calls |
| `common_failure` | 最近一次失败摘要 |

#### output_format_workshop — 输出格式规范库
- **内容**：4 个默认格式（随 `_seed_default_formats()` 初始化）
- **默认格式**：

| format_name | output_schema |
|-------------|---------------|
| `plain_text` | `{text: str}` |
| `code_execution` | `{success: bool, stdout: str, stderr: str, exit_code: int}` |
| `file_operation` | `{success: bool, path: str, message: str}` |
| `structured_data` | `{data: dict/list, summary: str}` |

### 6.2 知识写入机制（三条独立路径）

```
每次 op 执行完成
  │
  ├─ 路径 C（无论成败，无 LLM）─────────────────────────────
  │   _update_capability_calibration(tool_outputs)
  │   检查每个 tool result 有无错误信号 → update_capability()
  │   → capability_workshop（实时更新工具可靠性统计）
  │
  └─ op 成功时继续 ──────────────────────────────────────────
      │
      ├─ 路径 A（执行验证事实，confidence=1.0）
      │   _extract_execution_facts(tool_outputs)
      │   LLM 只从工具字面返回值提取（禁止推断，禁止常识）
      │   → add_verified_fact() → 直接写入 known_info_workshop
      │
      └─ 路径 B（LLM 推断，全部待审）
          _extract_inference_lessons(intent, spec, result)
          LLM 从任务摘要推断策略模式
          → apply_lesson() → pending_lessons（必须人工 approve）
```

**三条路径的信任层级**：

| 路径 | 来源 | 写入方式 | 可信度 |
|------|------|----------|--------|
| C 执行校准 | 工具 result 字符串哈希判断 | 直接统计，无 LLM | 纯事实 |
| A 执行验证事实 | 工具字面返回值（LLM 提取但禁止推断）| 直接写入 known_info | 高 |
| B LLM 推断 | 任务描述 + 结果摘要（LLM 推断）| pending_lessons 待审 | 需验证 |

**pending_lessons 管理**：
```python
agent.review_workshop_lessons()          # 查看待审队列（返回格式化字符串）
agent.workshops.approve_all_lessons()    # 全部确认写入
agent.workshops.dismiss_all_lessons()    # 全部拒绝
agent.workshops.approve_lesson(id)       # 确认单条
agent.workshops.dismiss_lesson(id)       # 拒绝单条
```

---

## 七、启动与运行

### 7.1 依赖安装

```bash
cd /home/chendechusn/Genesis/nanogenesis
pip install -e .          # 安装项目依赖（含 pydantic>=2.0, streamlit）
```

### 7.2 启动方式

```bash
# Streamlit Web UI（推荐）
streamlit run web_ui.py
# → http://localhost:8501

# 终端 CLI
python cli.py

# 直接调用（Python）
from genesis.core.factory import GenesisFactory
agent = GenesisFactory.create_common(api_key="sk-...")
result = await agent.process("你的任务")
```

### 7.3 环境变量

```bash
# .env 或直接导出
DEEPSEEK_API_KEY=sk-...       # 主要 LLM 提供商
OPENROUTER_API_KEY=sk-...     # 备用（故障转移）
OPENAI_API_KEY=sk-...         # 二级备用
```

### 7.4 首次启动行为

1. `WorkshopManager` 初始化 `~/.nanogenesis/workshops.sqlite`
2. `_seed_default_formats()` 写入 4 个默认输出格式
3. `_cold_start_scan()` 检测到 known_info 为空 → 写入 15 条系统环境事实
4. `seed_from_registry()` 在第一次 `manager.process()` 调用时同步工具

---

## 八、开发指南

### 8.1 向车间添加新工具

```python
from genesis.core.workshops import WorkshopManager, ToolEntry
w = WorkshopManager()
w.add_tool(ToolEntry(
    name="my_tool",
    tags=["category"],
    summary="简短描述（Manager 看的）",
    input_schema={"cmd": "str"},
    content="实现代码或调用方式",
))
```

### 8.2 向已知信息车间添加事实

```python
from genesis.core.workshops import WorkshopManager, FactEntry
w = WorkshopManager()
# 方式 A：手动添加（走正常 CRUD）
w.add_fact(FactEntry(
    key="project_root",
    category="filesystem",
    value="/home/chendechusn/Genesis",
    source="manual",
    confidence=1.0,
))
# 方式 B：直接写入执行验证事实（绕过待审队列，适用于程序内确认的事实）
w.add_verified_fact(
    key="deploy_target",
    value="192.168.1.100",
    category="network",
    source="shell:hostname",
)
```

### 8.5 查看工具执行可靠性

```python
w = WorkshopManager()
profile = w.get_capability_profile(min_calls=2)  # 至少 2 次才纳入统计
for p in profile:
    print(f"{p['capability']}: {p['reliability']:.0%} ({p['successes']}/{p['total_calls']} calls)")
# 示例输出：
# shell: 98% (52/53 calls)
# list_directory: 100% (9/9 calls)
```

### 8.3 添加解题模式

```python
from genesis.core.workshops import WorkshopManager, PatternEntry
w = WorkshopManager()
w.add_pattern(PatternEntry(
    pattern_name="verify_before_delete",
    context_tags=["filesystem", "dangerous"],
    approach="删除操作前先 ls 确认目标，再执行 rm",
    confidence=1.0,
))
```

### 8.4 快速健康检查

```bash
cd /home/chendechusn/Genesis/nanogenesis
python -c "
from genesis.core.factory import GenesisFactory
a = GenesisFactory.create_common(api_key='dummy', enable_optimization=False)
print(a.workshops.stats())
print('V2 OK')
"
```

### 8.5 回退 V1 路径

```python
# 任何情况下均可临时回退到旧 Ouroboros Loop
result = await agent.process("任务", use_v2=False)
```

---

## 九、禁止行为

- ❌ `Manager → OpExecutor` 接口传自然语言字符串（必须用 OpSpec dataclass）
- ❌ OpExecutor 持有全量 ToolRegistry（必须按 `spec.tool_ids` 过滤）
- ❌ 代码里写 `if task_type == "X"` 硬编码分支（LLM 决策）
- ❌ 向 OpExecutor 传入对话历史（隔离原则，每次 op 新建 context）
- ❌ 删除或修改基础设施层文件（`loop.py` / `registry.py` / `entropy.py` / `provider_manager.py`）
- ❌ 绕过熔断机制强行继续（`circuit_broken=True` 后必须上报用户）
- ❌ 用 LLM 推断出的内容绕过 pending_lessons 直接写入稳定车间（路径 B 必须经人工 approve）
- ❌ 在 `_extract_execution_facts()` 之外调用 `add_verified_fact()`（verified 路径只能来自工具字面返回值）

---

## 十、已知限制与后续迭代

| 项目 | 说明 | 优先级 |
|------|------|--------|
| 搜索精度 | 车间搜索使用 SQL `LIKE`，非语义匹配。车间 ≥100 条时精度下降 | 低（目前不影响使用） |
| Manager prompt | 已基于实际失败日志完善路由和学习 prompt，仍需更多真实任务调优 | 中 |
| pending_lessons UI | 有 CLI 方法，无图形审核界面 | 低（CLI 方法已可用） |
| ChromaDB | 可替换 LIKE 搜索提升语义匹配精度 | 低（等车间数据量增长后再换）|
| V1 路径清退 | `use_v2=False` 的 Ouroboros Loop 目前保留，后续确认稳定后可移除 | 低 |
| capability_workshop context 细分 | 当前以 tool_name 为粒度统计可靠性，未区分参数上下文（如「带 sudo 的 shell」与「普通 shell」）| 低（等数据量增长后细分）|
