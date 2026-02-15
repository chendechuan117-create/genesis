# NanoGenesis (微创世纪)

> **极简主义 · 工具优先 · Linux 原生**
> Minimalist. Tool-First. Linux-Native.

NanoGenesis 是一个运行在你本地 Linux 环境中的 **工程级 AI Agent**。
它拒绝浮华的“数字生命”扮演，专注于**解决问题**。通过直接操作 Shell、文件系统和浏览器，它能像工程师一样诊断、修复和构建系统。

---

## 核心哲学 (Core Philosophy)

1.  **去伪存真 (Anti-Bloat)**: 移除了所有即兴表演、情感模拟和冗余的“人格面具”。现在它只是一个高效的 **Linux AI Assistant**。
2.  **单脑架构 (Unified Brain)**: 以 **DeepSeek V3** 为主脑，确保逻辑推理的深度。
3.  **高可用 (High Availability)**: 集成 **Gemini 2.5 Flash** (via Local Proxy) 作为热备。当主脑宕机或网络波动时，**毫秒级自动切换**。
4.  **工具至上 (Tool First)**: 不依赖复杂的规划器，而是通过代码直接读取 `Tool Registry`，确保执行层永远知道自己能干什么。

---

## 架构特性 (Architecture)

### 1. 智能核心 (The Brain)
- **Primary**: DeepSeek V3 (NativeHTTP) - 负责 99% 的推理。
- **Failover**: Gemini 2.5 Flash (Antigravity Proxy) - 负责应急接管。
- **Mechanism**: **Bidirectional Failover** (双向故障转移)。任意一方失败，自动切另一方。

### 2. 执行引擎 (The Body)
- **Model**: ReAct (Reason-Act) Loop.
- **Strategy**: **Serial Execution** (串行执行)。
    - *为什么不并行？* 为了 100% 的文件操作安全性。避免多工具同时读写同一文件导致的竞争冲突。
- **Optimization**:
    - **Intent Phase**: 极简 JSON 输出 (`core_intent` + `memory_keywords`)，无幻觉，零废话。
    - **Context Pruning**: 智能上下文剪枝，防止 Token 爆炸。

### 3. 记忆系统 (The Memory)
- **Layer 1**: 近期对话 (RAM/Markdown) - 也就是"工作记忆"。
- **Layer 2**: 语义搜索 (SQLite FTS5) - 检索历史决策和知识。
- **Adaptive**: 自动记录你的偏好，"越用越顺手"。

---

## 快速开始 (Quick Start)

### 环境要求
- Linux (Arch/Debian/Ubuntu)
- Python 3.10+
- `curl` (用于底层 HTTP 通信)

### 运行
目前的入口脚本是 `debug_genesis.py` (整合测试版)：

```bash
# 1. 激活环境
source .venv/bin/activate

# 2. 运行
python3 debug_genesis.py
```

### 目录结构
```bash
Genesis/
├── nanogenesis/
│   ├── agent.py            # 【核心】Agent 主逻辑
│   ├── core/
│   │   ├── loop.py         # ReAct 执行循环
│   │   ├── context.py      # 上下文管理 (System Prompt)
│   │   └── registry.py     # 工具注册表
│   └── intelligence/
│       └── prompts/        # 提示词协议 (已优化为纯功能型)
├── debug_genesis.py        # 启动脚本
└── conversations/          # 对话日志 (按日期存储)
```

---

## 最近更新 (Changelog)

### 2026-02-14: The "Anti-Tumor" Update
- **[Optimization] 移除人格面具**: 删除了 "Autonomous Digital Lifeform" 和 "Strategist Persona"。现在的 Prompt 纯粹是功能性的。
- **[Optimization] 意图识别瘦身**: 移除了 `tools` (幻觉列表) 和 `system_diagnostic` 字段。Token 消耗减少 60%。
- **[Feature] 自动故障转移**: 实现了 DeepSeek <-> Gemini 的双向自动切换。

---

> "Thinking is expensive. Coding is cheap. Let's code."
