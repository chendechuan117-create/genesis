# Genesis V4 手术级改造计划 (Surgical Upgrade Plan)

> **定位**: 从“代码评审”升级为“实施方案”。不仅仅指出问题，而是定义如何修改代码。
> **核心哲学**: 
> 1. **Assembly 是参考而非枷锁**: 搜不到就用通用能力，不强求。
> 2. **物理世界的防爆**: 必须有截断机制防止 Context 爆炸。
> 3. **反思的经济性**: 只记关键信息，不回传海量噪音。

---

## 手术一：安装“安全阀” (Output Truncation)
> **解决**: 场景一 (Context Nuke)
> **目标**: 无论工具输出多长，永远不会撑爆 LLM 上下文。

### 1.1 涉及文件
- `genesis/tools/shell_tool.py`
- `genesis/tools/file_tools.py`
- `genesis/v4/loop.py` (作为最后一道防线)

### 1.2 修改方案
在所有工具的返回点，实施 **"Head-Tail" 截断策略**。
- **阈值**: 单次工具输出上限 4000 字符。
- **逻辑**: 如果 `len(output) > 4000`，则保留 `output[:2000] + "\n...[Output Truncated]...\n" + output[-2000:]`。
- **作用**: 既保留了头部信息（通常包含命令回显），也保留了尾部报错（通常包含错误原因），且 Token 消耗可控。

---

## 手术二：反思回路降噪 (Reflection Optimization)
> **解决**: 场景二 (Expensive Reflection)
> **目标**: C 进程只关注“做了什么”和“结果如何”，不需要看中间几十轮的“尝试-报错-重试”细节。

### 2.1 涉及文件
- `genesis/v4/loop.py`

### 2.2 修改方案
重构 `_run_reflection_phase` 的 Context 构造逻辑。
不再直接 `reflection_messages = self.messages.copy()`。

**改为构建“精简版上下文”**:
1. **System Prompt**: 保持不变。
2. **User Intent**: 保留最早的 `USER` 消息。
3. **Execution Summary (新)**: 
   - 遍历 `self.messages`，提取所有 `TOOL` 调用的 `name` 和 `result` (截断版)。
   - 生成一个纯文本摘要：
     ```text
     [执行摘要]
     1. G (Assembly): 搜索了 [关键词], 选中节点 [ID]
     2. Op (Execution): 
        - shell: ls -la (成功)
        - read_file: config.yaml (成功)
        - shell: python main.py (失败: ModuleNotFoundError)
     3. Op (Final): 最终回复了 "..."
     ```
4. **C-Process Instruction**: 告诉 C 进程基于这个摘要进行反思。

---

## 手术三：装配逻辑软化 (Soft Assembly)
> **解决**: 场景三 (Cold Start / Hallucination)
> **目标**: 还原 Assembly 的本质——**参考**。有参考最好，没参考拉倒，不要为了参考而编造。

### 3.1 涉及文件
- `genesis/v4/manager.py` (Prompt 构建)
- `genesis/v4/loop.py` (状态机逻辑)

### 3.2 修改方案

#### A. 修改 System Prompt (`manager.py`)
删除 "必须先调用 search" 和 "必须严格遵循节点" 的强硬措辞。
改为：
> "你拥有 `search_knowledge_nodes` 工具。如果任务涉及复杂流程或特定环境，请**优先搜索**以获取参考。如果搜索结果为空，或任务非常简单（如闲聊、通用编程），请直接输出基于你通用知识的蓝图。不要强行引用不相关的节点。"

#### B. 修改状态机 (`loop.py`)
在 `ASSEMBLY` 阶段，如果 LLM 直接输出了 JSON 蓝图而**没有**调用 search：
- **旧逻辑**: 视为违规（如果没 search 过）。
- **新逻辑**: **允许通过**。只要 JSON 格式对，哪怕 `active_nodes` 为空，也直接进入 `EXECUTION`。

这样，G 变成了：
- **查阅者**: 觉得需要就查。
- **决策者**: 查不到就自己定方案。
不再是只会“照书念”的呆板员工。

---

## 总结
这三项手术将把 Genesis V4 从一个“理论模型”变成一个“实战兵器”。
1. **不炸膛** (截断)
2. **不浪费** (反思降噪)
3. **不发疯** (软化装配)
