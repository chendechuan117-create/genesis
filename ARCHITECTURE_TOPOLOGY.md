# NanoGenesis v2.0 架构拓扑图 (Architecture Topology)

本文档详细描述了 NanoGenesis v2.0 的生物学架构、运作流程及模块映射。

---

## 🧬 1. 生物学架构概览 (Biological Architecture)

NanoGenesis 模仿生物体结构，分为三大核心系统：

1.  **神经中枢 (Nervous System)**: 负责感知环境、时间、记忆。
2.  **双脑认知 (Dual-Brain Cognition)**: 负责反射（快思考）和推理（慢思考）。
3.  **肢体躯干 (Body & Limbs)**: 负责执行具体操作。

```mermaid
graph TD
    User((用户输入)) --> Nervous[神经中枢 (Perception)]
    
    subgraph Nervous System [感知层]
        Nervous --> Time[时间感知]
        Nervous --> Env[环境感知]
        Nervous --> Memory[海马体记忆]
        Config[配置中枢 ConfigManager] -.-> Nervous
        Nervous --> Compression[压缩协议 CompressionEngine]
    end
    
    Compression --> Meta[多面体元认知 Polyhedron]
    
    subgraph Single Brain [认知层]
        Meta --> Polyhedron[递归多面体 Recursive Polyhedron]
        Polyhedron -- 缺条件? --> Acquisition[获取环 RECT Loop]
        Acquisition -- 无法获取? --> Human[人类介入 Human-in-the-Loop]
        Human -- 提供条件 --> Polyhedron
        Polyhedron -- 条件完备 --> CloudBrain[云端主脑 DeepSeek-V3]
    end
    
    CloudBrain --> ToolSelector[工具选择]
    
    subgraph Body [执行层]
        ToolSelector --> Hands[ShellTool (双手)]
        ToolSelector --> Eyes[BrowserTool (眼睛)]
        ToolSelector --> Fingers[FileTools (手指)]
        ToolSelector --> Womb[SkillCreator (工具生成)]
        
        Hands --> Host[宿主系统]
        Eyes --> Web[互联网]
        Womb --> NewSkill[新技能]
    end
    
    Host --> Feedback[反馈循环]
    Web --> Feedback
    Feedback --> Evolution[进化模块 ProfileEvolution]
    Evolution -.-> CloudBrain
```

---

## 🔬 2. 模块节点详解 (Module Nodes)

### A. 神经中枢 (Nervous System)
| 文件路径 | 模块名称 | 功能描述 | 生物对应 |
| :--- | :--- | :--- | :--- |
| `core/config.py` | **ConfigManager** | 零配置启动，自动吸取 OpenClaw/Env 配置。 | **DNA/基因** |
| `core/context_pipeline.py` | **ContextPipeline** | 组装时间、环境、记忆，构建“世界观”。 | **感觉皮层** |
| `core/compression.py` | **CompressionEngine** | 历史记录分块压缩，Token 密度优化。 | **神经修剪** |
| `core/memory_vector.py` | **VectorMemory** | 长期记忆存储与检索 (RAG)。 | **海马体** |

### B. 认知中枢 (The Brain)
| 文件路径 | 模块名称 | 功能描述 | 生物对应 |
| :--- | :--- | :--- | :--- |
| `agent.py` | **AgentLoop** | 核心循环，单脑直连云端 LLM (V3) 进行推理。 | **大脑皮层** |
| `intelligence/prompts/polyhedron` | **Polyhedron** | **[默认激活]** 处理任务的元认知思维框架。 | **前额叶 (深度思考)** |

### C. 躯干与工具 (The Body)
| 文件路径 | 模块名称 | 功能描述 | 生物对应 |
| :--- | :--- | :--- | :--- |
| `tools/shell_tool.py` | **ShellTool** | 执行系统命令 (无沙箱，直连宿主)。 | **双手** |
| `tools/browser_tool.py` | **BrowserTool** | 打开网页、搜索信息 (native xdg-open)。 | **眼睛/腿** |
| `tools/file_tools.py` | **FileTools** | 读写文件系统。 | **手指** |
| `tools/skill_creator_tool.py` | **SkillCreator** | 动态生成 Python 工具代码并热加载。 | **子宫 (繁殖)** |

### D. 进化系统 (Evolution)
| 文件路径 | 模块名称 | 功能描述 | 生物对应 |
| :--- | :--- | :--- | :--- |
| `optimization/profile_evolution.py` | **ProfileEvolution** | 观察用户习惯，动态调整 System Prompt。 | **神经可塑性** |

---

## 🌊 3. 运作流程示例 (Operation Flow)

以 **“帮我打开网页版 Gemini”** 为例：

1.  **启动 (Boot)**: `ConfigManager` 读取宿主代理设置，系统唤醒。
2.  **感知 (Sensation)**:
    *   `ContextPipeline` 注入当前时间 (2026-02-08) 和环境 (Linux Desktop)。
3.  **反射 (Reflex)**:
    *   本地脑 (`IntentAnalyzer`) 判定：“打开网页”是简单指令，无需元认知规划。
4.  **认知 (Cognition)**:
    *   云端脑 (`AgentLoop`) 接收上下文。
    *   它发现意图是“访问 URL”，并检索到工具箱里有 `BrowserTool`。
    *   它**不再**尝试编写 Shell 脚本，而是直接生成工具调用：`browser_tool.execute(action="open", url="...")`。
5.  **执行 (Action)**:
    *   `BrowserTool` 接收指令，调用底层 OS 接口 (`xdg-open`)。
    *   浏览器弹出。
6.  **反馈 (Feedback)**:
    *   执行结果（“已打开”）回传给大脑。
    *   `ProfileEvolution` 记录：“用户喜欢使用网页工具”。

---

## ⚠️ 关键架构变更 (v2.0 vs v1.0)

1.  **去沙箱化 (De-Sandboxing)**: 移除了 `ShellTool` 的 Docker 隔离，允许直接操作宿主。
2.  **器官专用化 (Specialization)**: 新增 `BrowserTool`，不再强行用 Shell 模拟浏览器操作。
3.  **零配置 (Zero-Conf)**: 移除了繁琐的 `.env` 依赖，直接复用 OpenClaw 生态。
