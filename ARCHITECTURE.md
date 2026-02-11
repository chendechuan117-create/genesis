# NanoGenesis 2.0 终极架构图谱

> "一个融合了云端算力与本地本能的有机智能生命体。"

本文档详细拆解了 NanoGenesis 2.0 的最终形态，包含双脑架构、本能层设计及全链路数据流。

---

## 1. 全景架构图 (The Big Picture)

```mermaid
graph TD
    User((用户)) --> Interfaces[交互层]
    
    subgraph Interfaces [🔌 交互层 (Interfaces)]
        CLI[命令行 CLI]
        Web[网页端 Web]
        Telegram[Telegram Bridge]
        Telegram -- Hijack --> OpenClaw(OpenClaw)
    end
    
    Interfaces --> Orchestrator[中枢神经 (Agent.py)]
    
    subgraph LocalBrain [⚡ 本能层 / 快思考 (System 1)]
        LocalLLM[[本地模型 (Ollama)]]
        Intent[意图识别 (IntentAnalyzer)]
        Filter[记忆筛选 (ContextFilter)]
        
        Orchestrator --> Intent
        Intent --> LocalLLM
        Orchestrator --> Filter
        Filter --> LocalLLM
    end
    
    subgraph CloudBrain [🧠 认知层 / 慢思考 (System 2)]
        CloudLLM[[云端模型 (DeepSeek API)]]
        Polyhedron[多面体协议]
        
        Orchestrator --> Polyhedron
        Polyhedron --> CloudLLM
    end
    
    subgraph MemorySystem [� 记忆系统]
        ShortTerm[短期上下文]
        LongTerm[长期记忆 (SimpleMemory)]
        Strategy[策略库 (Behavior)]
        
        Filter <--> LongTerm
    end
    
    subgraph Body [🛡️ 躯体与四肢]
        Sandbox[Docker 沙箱]
        Tools[工具集]
        SkillGen[技能生成器]
        
        CloudLLM --> Tools
        Tools --> Sandbox
    end
    
    subgraph NervousSystem [✨ 自优化闭环]
        PromptOpt[提示词优化]
        ToolOpt[工具推荐]
        
        Orchestrator --> PromptOpt
        Orchestrator --> ToolOpt
    end
    
    Intent -- Simple --> LocalLLM
    Intent -- Complex --> CloudBrain
```

---

## 2. 模块详解 (Module Breakdown)

### 🔌 交互层 (Interfaces)
**作用**：连接世界，接收指令。
*   **`cli.py`**: 开发者控制台。最快启动，适合调试。
*   **`server.py`**: 零依赖 Web UI。让手机可以通过局域网访问，体验类似 ChatGPT。
*   **`telegram_bridge.py`**: 远程遥控器。
    *   **Hijack Mode**: 支持 `/hijack` 指令，强制关闭冲突的 OpenClaw 进程，接管通信渠道。
    *   **Resilience**: 内置 `curl` 降级，在 Python 网络库被墙时自动切换系统命令发送请求。

### ⚡ 本能层 (Instinct Layer / Local Brain)
**作用**：基于本地算力 (Ollama) 的快思考，零成本、低延迟。
*   **`core/provider_local.py`**: 本地 LLM 驱动。默认连接 `deepseek-r1:latest`。
*   **`intelligence/intent_analyzer.py`**: **直觉判断**。
    *   分析用户是想闲聊（Simple）还是想干活（Complex）。
    *   如果判断为闲聊，直接由本地模型回复，**响应时间 < 0.5s**。
*   **`intelligence/context_filter.py`**: **潜意识过滤**。
    *   从海量记忆中初步捞出 20 条后，由本地模型快速阅读并挑选出真正相关的 5 条。
    *   **核心价值**：防止垃圾信息污染主大脑，**节省 80% 的云端 Token**。

### 🧠 认知层 (Cognition Layer / Cloud Brain)
**作用**：基于云端算力 (DeepSeek API) 的慢思考，处理复杂逻辑。
*   **`core/provider.py`**: 云端 LLM 驱动。支持网络自动重试。
*   **`intelligence/prompts/polyhedron_protocol.txt`**: **多面体协议**。
    *   当意图被判断为 Complex 时启动。
    *   强制模型进行多维度思考（诊断、规划、反思）后再行动。

### �️ 躯体层 (Body / Execution)
**作用**：安全地执行对物理世界的改变。
*   **`core/sandbox.py`**: **免疫系统**。
    *   所有 Shell 命令都在 Docker 容器内执行。
    *   即使模型发疯想删库 (`rm -rf /`)，也只会删掉容器内的临时文件，宿主机毫发无损。
*   **`tools/skill_creator_tool.py`**: **进化机制**。
    *   当现有工具不够用时，Agent 会自己写一段 Python 代码并保存为新工具。即刻生效。

### ✨ 神经系统 (Nervous System / Optimization)
**作用**：从经验中学习，自我迭代。
*   **`optimization/behavior_optimizer.py`**: 记录所有成功的操作序列。下次遇到类似问题，直接调用“肌肉记忆”，跳过推理步骤。
*   **`core/context.py` (Constitution)**: 系统宪法。将“记忆优先”等核心原则写入基因，而非每次临时教导。

---

## 3. 数据流转 (The Flow)

当你说一句：**“帮我看看服务器负载”**

1.  **感知**: `telegram_bridge` 收到消息。
2.  **直觉 (Local)**: `IntentAnalyzer` 调用本地 Ollama，判断为 **Complex**（需要执行命令）。
3.  **潜意识 (Local)**: `ContextFilter` 从记忆库检索“服务器”、“负载”相关记录，发现你之前教过它 `top` 命令的用法，筛选出这条记忆。
4.  **思考 (Cloud)**: 
    *   主大脑接收：用户指令 + 筛选后的记忆 + 系统宪法。
    *   多面体引擎规划：1. `uptime` 看概况 -> 2. `top` 看细节。
5.  **行动 (Body)**: 
    *   在 Docker 沙箱中执行 `uptime`。
    *   在 Docker 沙箱中执行 `top -b -n 1`。
6.  **表达**: 汇总结果，通过 Telegram 发回给你。
7.  **反思 (Nerves)**: 记录这次成功的操作序列。下次再问，直接执行，不再重新规划。

这就是一个**融洽的、适应性强**的有机体。
