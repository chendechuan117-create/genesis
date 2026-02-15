# Genesis - AI 开发者交接文档

> **致下一位接手的 AI：**
> 这是一个融合了 nanobot、OpenClaw 和 Genesis 的自进化 Agent 项目。核心目标是**极致省 Token** + **自我进化**。
> 本文档将指引你快速理解核心架构，避免踩坑。

---

## 🚦 核心文件优先级 (Tier 0 - 必须理解)

**项目入口**：
1.  **`genesis/cli.py`**
    *   **作用**：命令行入口，解析参数，启动 Agent。
    *   **注意**：查看 `main()` 函数，了解如何初始化 `NanoGenesis` 类。

2.  **`genesis/agent.py`**
    *   **作用**：Agent 的大脑，`NanoGenesis` 主类所在地。
    *   **关键点**：`process()` 方法是主循环的入口；`_build_optimized_context()` 负责构建上下文（含缓存机制）。

3.  **`genesis/core/loop.py`**
    *   **作用**：ReAct 循环引擎。
    *   **关键点**：理解 Tool 调用和结果回传的逻辑。

4.  **`genesis/system_profile.md`**
    *   **作用**：当前运行环境的详细描述。
    *   **重要**：务必读取此文件以了解硬件资源、文件路径和用户习惯（如中文目录）。

---

## 🧠 智能核心 (Tier 1 - 调优重点)

1.  **`genesis/intelligence/`**
    *   包含所有智能相关的 Prompt 和逻辑。
    *   **`prompts/`**: 存放系统提示词模板。
    *   **`router.py`**: 意图识别模块。

2.  **`genesis/optimization/`**
    *   **自进化引擎**的核心。
    *   **`prompt_optimizer.py`**: 提示词优化器（A/B 测试）。
    *   **`behavior_optimizer.py`**: 策略库管理器（经验学习）。
    *   **`tool_optimizer.py`**: 工具链优化。

3.  **`genesis/data/`**
    *   **知识库**：
        *   `strategies.json`: 存储成功的解题策略。
        *   `history.json`: 交互历史。
        *   `user_profile.json`: 用户画像数据。

---

## 🛠️ 工具与能力 (Tier 2 - 扩展方向)

1.  **`genesis/core/registry.py`**
    *   工具注册表，管理所有可用工具。
    *   **扩展**：添加新工具需在此注册。

2.  **`genesis/core/provider.py`**
    *   **LLM 接口**。
    *   **注意**：如果遇到网络超时或 API 错误，请检查此处的重试机制和超时设置。

3.  **`genesis/tools/`**
    *   内置工具集（Shell, File, Web 等）。

---

## ⚠️ 避坑指南 (Critical Issues)

1.  **GUI 死锁风险**
    *   **现象**：在 Linux 桌面环境下，如果 Agent 尝试启动 GUI 程序（如 `kcalc`, `gedit`）且没有后台运行 (`&`)，会导致主线程挂起。
    *   **解决**：所有 GUI 命令必须追加 `&`，或者使用 `nohup`。

2.  **网络超时**
    *   **现象**：中国大陆网络环境下，部分 API 可能访问缓慢。
    *   **解决**：项目内已配置代理检测逻辑（见 `check_proxy_ports.sh`），必要时使用 `curl` 替代 `requests` 进行网络测试。

3.  **文件路径**
    *   **注意**：项目已被移动到 `/home/chendechusn/Genesis`。
    *   **旧路径**（已废弃）：`/home/chendechusn/nanabot/nanogenesis`，请勿在该路径下写入。

---

## 📝 常用维护命令

- **启动 Agent**:
  ```bash
  python -m genesis.cli "你的问题"
  ```
- **运行测试**:
  ```bash
  pytest tests/
  ```
- **查看状态**:
  ```bash
  cat STATUS.md
  ```

---

*祝你好运，愿你的 Token 永远够用！*
