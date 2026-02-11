# OpenClaw 如何解决"重复介绍自己"的问题

## 🎯 关键发现

### OpenClaw 的方式

**AGENTS.md 的指导**:
```markdown
## Every Session

Before doing anything else:

1. Read `SOUL.md` — this is who you are
2. Read `USER.md` — this is who you're helping
3. Read `memory/YYYY-MM-DD.md` (today + yesterday) for recent context
4. **If in MAIN SESSION**: Also read `MEMORY.md`

Don't ask permission. Just do it.
```

**关键点**:
- OpenClaw 在**每个会话开始时**读取记忆
- 读取后就**不再提及**"我读取了记忆"
- 直接进入对话，像人一样

---

## 🔍 Genesis 的问题

### Genesis 现在的行为

**每次回复都说**:
```
我回来了。根据记忆文件，我了解到：
1. 你是陈德川，我是Chen
2. 你正在学习技术...
```

**问题**:
- 每次都在**重复读取和介绍**记忆
- 像是每次都"重新认识"用户
- 不像连续对话

---

## 💡 OpenClaw 的解决方案

### 1. 会话初始化时读取记忆

OpenClaw 的逻辑：
```
Session Start:
  1. 读取 SOUL.md, USER.md, MEMORY.md
  2. 内化这些信息
  3. 开始对话 - 不提及"我读取了记忆"
  
During Conversation:
  - 自然使用记忆中的信息
  - 不重复介绍
  - 像朋友一样对话
```

### 2. System Prompt 的设计

OpenClaw 的 System Prompt 可能是：
```
You are Chen. You know the user is 陈德川.

[Memory content loaded here]

Now chat naturally. Don't say "I read the memory" or "According to the files".
Just talk like you remember these things naturally.
```

---

## 🔧 Genesis 应该怎么改

### 当前问题

**Genesis 的流程**:
```python
# 每次 process() 调用时
1. 加载 OpenClaw 记忆
2. 筛选相关记忆
3. 把记忆作为"上下文"传递给 LLM
4. LLM 看到记忆后说："我回来了，根据记忆..."
```

**根本原因**: 
- 记忆是作为**显式上下文**传递的
- LLM 看到"相关记忆："这样的标记
- 所以它会说"根据记忆文件"

---

### 解决方案

**方案 1: 记忆融入 System Prompt（推荐）**

```python
# 会话开始时
system_prompt = """You are Genesis.

You know:
- User is 陈德川 (Chen Dechuan)
- You are Chen, his AI assistant
- He's learning Linux, had issues with Steam on Wayland
- He wants to play Terraria with tModLoader
- You've helped with network optimization and DNS

Chat naturally. Don't mention "according to memory" or "I read files".
Just know these things.
"""

# 对话时
# 不需要每次都传递记忆
# 只在 system prompt 里有就够了
```

**方案 2: 改进 User Message 格式**

当前：
```
相关记忆：
### USER.md
你是陈德川...
```

改为：
```
[Background context - don't mention this explicitly]
User: 陈德川
Previous work: network optimization, Steam installation
```

**方案 3: 明确告诉 AI 不要提及记忆**

在 System Prompt 中加入：
```
IMPORTANT: You have access to memory and context.
Use this information naturally in conversation.
NEVER say phrases like:
- "I read the memory"
- "According to the files"
- "I came back"
- "Based on the records"

Just talk like you naturally remember these things.
```

---

## 🎯 具体实现建议

### 立即改进

1. **在 System Prompt 中明确禁止**
   ```python
   prompt += "\nIMPORTANT: Use your knowledge naturally. "
   prompt += "Don't say 'according to memory' or 'I read files'. "
   prompt += "Just know these things.\n"
   ```

2. **改进记忆传递方式**
   - 不要用"相关记忆："这样的标记
   - 直接融入 system prompt
   - 或者用更隐式的方式

3. **会话级记忆加载**
   - 在会话开始时加载一次
   - 后续对话不再重复加载
   - 保持对话连贯性

---

## 📊 对比

### OpenClaw 的对话

```
User: 你记得我吗
OpenClaw: 记得，陈德川。上次我们搞定了网络优化。现在需要什么？

User: 对telegram有印象吗
OpenClaw: 有，之前 Qt6-wayland 更新搞坏了 Telegram，我们降级修复了。
```

**特点**: 简洁、直接、不提及"记忆"

### Genesis 当前的对话

```
User: 你记得我吗
Genesis: 我回来了。根据记忆文件，我了解到：
1. 你是陈德川，我是Chen
2. 你正在学习技术...

User: 对telegram有印象吗
Genesis: 我回来了。根据记忆文件，你是陈德川...
```

**问题**: 啰嗦、格式化、每次都"重新认识"

---

## 🚀 行动计划

### 高优先级（立即）

1. **在 AdaptiveLearner 的 prompt 中加入明确禁止**
   ```python
   prompt += "\nNEVER say: 'I read the memory', 'According to files', 'I came back'.\n"
   prompt += "Just use your knowledge naturally.\n"
   ```

2. **改进记忆传递格式**
   - 移除"相关记忆："标记
   - 直接融入 system prompt

### 中优先级（本周）

3. **实现会话级记忆**
   - 会话开始时加载一次
   - 后续对话复用
   - 不重复加载

4. **学习 OpenClaw 的 prompt 结构**
   - 研究它的 system prompt 设计
   - 借鉴其记忆管理方式

---

## 💡 核心教训

**OpenClaw 成功的原因**:
1. 记忆是**内化**的，不是**显式传递**的
2. System prompt 设计得像"你已经知道这些"
3. 明确告诉 AI 不要提及记忆来源

**Genesis 需要改进**:
1. 不要把记忆当作"上下文"显式传递
2. 融入 system prompt，让 AI "自然知道"
3. 明确禁止"根据记忆"这类表述

**本质区别**:
- OpenClaw: "你知道这些事情"
- Genesis: "这里有一些记忆文件，请参考"

前者更自然，后者太机械。
