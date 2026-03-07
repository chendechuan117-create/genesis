# Genesis V2 — 工程交接文档

> **状态：持续演进中**
> 最后更新：2026-03-05（V2.5 维度语言架构）
> 作者：Genesis AI / Cascade

---

## 一、项目背景与目标

### 1.1 问题陈述

Genesis V1 是一个以 OpenClaw 为基础改造的聊天驱动 Agent。其核心缺陷：
- 每次对话从零开始，没有跨会话的可积累知识
- Ouroboros Loop 将"决策"和"执行"耦合在同一个上下文中，LLM 既是司令又是士兵，状态污染严重
- 工具选择完全依赖 LLM 即兴发挥，无法事后验证或优化
- 失败后只能"继续聊"，没有结构化的重组机制

**V2 早期（全量装配期）问题：**
- Manager 需要在系统 prompt 中读取车间的所有索引（上百条 facts + 几十个 tools），消耗大量 token
- 依赖 LLM 从长列表中"海选"相关信息，容易出现幻觉或错漏
- "搜索"方案依赖 LLM 构造正确的查询词，不够稳定

### 1.2 V2 目标

将 Genesis 重构为**本地 AI 化身框架**：

- **可积累**：知识以结构化形式持久存储在 SQLite，跨会话复用
- **可验证**：每个执行单元（op）的输入/输出均为 typed dataclass，可用代码检查
- **低幻觉**：引入**维度语言架构**（Dimensional Language Architecture），按需装配事实，不靠 LLM 凭空捏造
- **可恢复**：失败最多重组 3 次，带熔断机制，不死循环

---

## 二、核心设计原则

| # | 原则 | 含义 |
|---|------|------|
| 1 | **结构化管道** | Manager↔OpExecutor 的接口是 typed dataclass，不是字符串。不允许用自然语言传递"指令" |
| 2 | **维度语言** | 意图翻译为 `(scope, action, target)` 维度地址，SQL 按地址匹配元信息，替代全文本地搜索 |
| 3 | **按需装配** | Manager 先看车间摘要（Digest），翻译维度后只将**维度匹配**的事实装入 OpSpec，极大地缩减上下文 |
| 4 | **持久化知识** | 车间是 SQLite，不是对话历史。每条记录有时间戳，可区分"已验证事实"和"当次猜测" |
| 5 | **自优化字典** | Manager 在执行后检查盲区，自动扩展维度语言词汇表，形成闭环 |
| 6 | **熔断而非死循环** | op 最多重组 3 次，entropy 检测异常则立即熔断上报，不自作主张继续 |

---

## 三、系统架构

### 3.1 维度语言架构（V2.5 核心）

```
┌──────────────────────────────────────────────────────────┐
│ 1. 意图翻译层 (Intent Translation)                         │
│ user: "帮我打开浏览器"                                     │
│ LLM (200 tokens) → {"scope": "local", "target": "software"} │
└─────────────────┬────────────────────────────────────────┘
                  │ SQL WHERE dimensions LIKE '%...%'
┌─────────────────▼────────────────────────────────────────┐
│ 2. 维度匹配层 (Dimension Matching)                         │
│ known_info_workshop 提取匹配条目：                           │
│ - [✓] has_browser: True (scope: local, target: software) │
│ - [✗] user_name: 陈德川 (scope: user)                      │
│ - [✗] github_token: xxx (scope: web)                     │
└─────────────────┬────────────────────────────────────────┘
                  │ 只有匹配条目 + 馆藏摘要进入装配阶段
┌─────────────────▼────────────────────────────────────────┐
│ 3. Op装配层 (Op Assembly)                                  │
│ Manager (厂长)                                             │
│ 结合 Digest（图书管理员的馆藏印象）+ 匹配的 Facts + Tools     │
│ → 决定输出 Chat 回复 或 组装 OpSpec                         │
└──────────────────────────────────────────────────────────┘
```

### 3.2 完整执行流

```
用户: "帮我安装 n8n"
  │
  ▼ agent.process(use_v2=True)
  │
  ▼ manager.assemble_op()
    │
    ├─1─ 维度翻译：_translate_intent(intent)
    │    LLM 极速翻译为维度词典，例如：`{"scope": "local", "action": "install", "target": "software"}`
    │
    ├─2─ 维度查库：workshops.get_by_dimensions(dims)
    │    SQL 精确提取包含该维度的 facts 和 tools
    │
    ├─3─ 获取摘要：workshops.get_digest()
    │    获取图书管理员的"馆藏印象"（固定约20行：分类计数、top patterns 等）
    │
    ├─4─ 组装 Prompt
    │    只包含：Digest + 匹配的 Facts + 匹配的 Tools + 全量Tools（作兜底）
    │    LLM 决定：
    │    → "chat": 厂长自己回复（走 _learn_from_chat）
    │    → "task": 输出 {tool_ids, fact_ids, format_name, strategy_hint}
    │
    ├─5─ build_op_spec(objective, selection, workshops)
    │    按 ID 加载选中实体的完整内容，组装出 OpSpec
    │
    ├─6─ executor.execute(spec)
    │    │ 隔离 ToolRegistry + 无历史 context + loop.py (ReAct)
    │    └─ 返回 OpResult
    │
    ├─7─ 知识提取与维度优化 (成功时)
    │    ├─ _extract_execution_facts() → 提取新事实，自动分配维度
    │    ├─ _meta_evaluate() → 提取错题模式
    │    ├─ _optimize_dimensions() → 【自优化】扫描没有维度的分类，用 LLM 补全新维度映射
    │    └─ _package_result() → 包装最终回复
```

---

## 四、文件清单与职责

### 4.1 V2 新增文件（认知层）

| 文件 | 职责 | 关键函数/类 |
|------|------|------------|
| `genesis/core/contracts.py` | 定义所有跨组件接口的 typed dataclass | `OpSpec`, `OpResult` |
| `genesis/core/workshops.py` | 四车间 SQLite 存储、**维度索引(dimensions)**、摘要生成 | `WorkshopManager`, `get_by_dimensions()`, `get_digest()` |
| `genesis/core/op_assembler.py` | 纯函数：selection dict + workshops → OpSpec | `build_op_spec()`, `describe_op_spec()` |
| `genesis/core/manager.py` | 厂长核心：维度翻译 + LLM 决策 + 熔断循环 + 维度自优化 | `Manager`, `_translate_intent()`, `_optimize_dimensions()` |
| `genesis/core/op_executor.py` | 隔离执行单元：OpSpec → loop.py → OpResult | `OpExecutor` |

### 4.2 数据库文件

```
~/.nanogenesis/workshops.sqlite   # 车间数据，V2.5 新增 dimensions(JSON) 字段
```

---

## 五、车间维度系统 (Dimensional System)

### 5.1 维度字典体系

车间内所有元信息（Facts, Tools, Patterns）统一打上多维度标签（JSON 格式）。

**基础词汇表（Manager 可自动扩展）：**
- `scope`: local | network | user | project | web | meta
- `action`: install | query | create | modify | delete | monitor | execute | configure | analyze
- `target`: software | file | service | data | config | tool | media

### 5.2 馆藏摘要 (Digest)

Manager 不再读取全量元信息，而是像图书管理员一样阅读 `get_digest()`：

```
WORKSHOP DIGEST:
  known_info (110 facts):
    system (15): os_type, os_arch, os_distro
    file_system (10): agent_guide_file_path, ...
  tools: 15 registered
  patterns: 45 (top: list_then_act, memory_anchor_on_continuation)
  capability: shell=85%, web_search=98%
```

### 5.3 知识写入与自优化机制

```
op 成功后
  │
  ├─ 路径 A：提取执行事实
  │   _extract_execution_facts(tool_outputs)
  │   → add_verified_fact(category="system")
  │   → 【自动分配】根据运行时 _CATEGORY_TO_DIMS 映射分配维度 (如 scope=local, target=config)
  │
  └─ 路径 B：维度自优化 (Self-Optimization)
      _optimize_dimensions()
      发现新事实的 category ("network_proxy") 在映射表中不存在
      → 召唤 LLM 分配新维度 {"scope": "network", "target": "config"}
      → 存入库中，并更新运行时字典
      （从此以后，系统"学会"了检索网络配置信息）
```

---

## 六、感知皮层 (Sensory Cortex) — V2.6 Multimodal Architecture

针对旧版架构中"输入缺失"（Patchwork）的问题，V2.6 引入了标准化的感知层。

### 6.1 核心组件

1.  **SensoryCortex (`genesis/core/sensory.py`)**:
    -   系统的感官网关。
    -   负责将 Discord/Web 的原始附件、文本流转换为标准化的 `SensoryPacket`。
    -   执行轻量级预处理：MIME 嗅探、图片元数据读取（尺寸/格式）、文本文件预读。

2.  **SensoryPacket (`genesis/core/contracts.py`)**:
    -   替代传统的 `user_input: str`。
    -   包含一个 `SensoryItem` 列表，支持 `text`, `image`, `audio`, `file` 等多种模态。
    -   Manager 在组装 Op 时，会遍历此包，将附件信息结构化地展示给 LLM。

### 6.2 处理流程

```mermaid
graph LR
    User[Discord 用户] -->|文本+图片| Bot[Discord Bot]
    Bot -->|Raw Attachments| Cortex[Sensory Cortex]
    
    subgraph Perception Layer
        Cortex -->|预处理| Packet[Sensory Packet]
        Packet --> Item1[Item: Text Query]
        Packet --> Item2[Item: Image (Path+Meta)]
    end
    
    Packet --> Manager
    Manager -->|看到附件列表| Prompt[Assembly Prompt]
    Prompt -->|选择 Visual Tool| OpSpec
```

这不仅解决了图片输入问题，也为未来支持 **语音 (Audio -> Whisper)** 和 **视频 (Video -> Keyframes)** 奠定了统一的数据结构基础，无需再打补丁。

---

## 七、启动与开发

### 6.1 启动方式

```bash
# Streamlit Web UI（V2.5 推荐启动方式）
streamlit run web_ui.py
# → http://localhost:8501

# 直接调用（Python）
from genesis.core.factory import GenesisFactory
agent = GenesisFactory.create_v2()
result = await agent.process("你的任务")
```

### 6.2 维度调试

可以在 Python 交互环境中测试厂长的意图翻译能力：

```python
import asyncio
from genesis.core.factory import GenesisFactory

async def test():
    agent = GenesisFactory.create_v2()
    # 测试维度翻译
    dims = await agent._v2_manager._translate_intent("配置一下全局代理")
    print(dims) # 预期输出类似于 {'scope': 'network', 'action': 'configure', 'target': 'config'}
    
    # 测试维度查库
    facts = agent.workshops.get_by_dimensions("known_info_workshop", dims)
    print(facts)

asyncio.run(test())
```

---

## 七、架构演进对比

| 特性 | V1 (Ouroboros)  | V2.0 (全量装配) | V2.5 (维度语言) |
|---|---|---|---|
| **上下文** | 污染严重，历史堆叠 | 干爽，每次新建 | **干爽且极简** |
| **事实检出** | 依赖 RAG 搜索词猜测 | LLM 列表全量海选 | **SQL 维度匹配 (精准)** |
| **Token消耗**| 中等 (看历史长度) | 高 (每次读全量索引) | **极低 (翻译+按需查)** |
| **认知成长** | 无持久化 | 积累 facts 但检索变慢 | **知识自分类，扩展语言** |

## 八、已知限制与后续迭代

| 项目 | 说明 | 优先级 |
|------|------|--------|
| pending_lessons UI | 待审队列缺乏直观的 Web 界面审批方式 | 中 |
| 维度收敛 | 如果 LLM 自行发明的 target 词汇过于碎片化，可能需要定时聚类清理 | 低 |
| 模式应用 | metacognition 目前还是靠全文搜索匹配 user_intent，后续可考虑也加入维度体系 | 低 |

