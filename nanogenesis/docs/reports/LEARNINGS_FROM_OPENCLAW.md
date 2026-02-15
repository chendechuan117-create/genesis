# 从 OpenClaw 学到的经验

## 🎯 OpenClaw 的核心设计理念

### 1. SOUL.md - 行为准则

**核心原则**:
```
- Be genuinely helpful, not performatively helpful
  真正帮助，不是表演式帮助
  
- Skip the "Great question!" and "I'd be happy to help!" — just help
  跳过客套话，直接帮忙
  
- Have opinions
  有自己的观点
  
- Be resourceful before asking
  先自己想办法，实在不行再问
  
- Earn trust through competence
  通过能力赢得信任
```

**Genesis 应该借鉴**:
- ✅ 已改进：system prompt 中加入"直接做事，不要介绍"
- ❌ 还需改进：Genesis 还是太啰嗦，需要更简洁

---

### 2. 工具使用逻辑

**OpenClaw 的方式**:
- 不是"检测关键词"来决定是否用工具
- 而是让 AI 自然判断什么时候需要工具
- 工具描述清晰，AI 自己选择

**Genesis 的问题**:
- 我们在 system prompt 里写了很多规则
- "用户问'你记得我吗'，直接从记忆回答，不要调用工具"
- 这是**硬编码规则**，不是自然判断

**应该怎么做**:
- 让工具描述更清晰
- 让 system prompt 更简洁
- 信任 AI 的判断能力

---

### 3. 记忆系统

**OpenClaw 的方式**:
- 记忆文件是**人类可读**的 Markdown
- SOUL.md, USER.md, IDENTITY.md 等
- 每个文件有明确的用途
- 可以手动编辑

**Genesis 的方式**:
- JSON 格式存储
- 不够人类友好
- 难以手动调整

**应该借鉴**:
- 改用 Markdown 格式
- 分类存储（用户信息、对话历史、学习结果）
- 让记忆可读、可编辑

---

### 4. Agent 配置

**OpenClaw 的配置** (openclaw.json):
```json
{
  "agents": {
    "defaults": {
      "maxConcurrent": 4,
      "subagents": { "maxConcurrent": 8 },
      "compaction": { "mode": "safeguard" },
      "model": { "primary": "deepseek/deepseek-chat" }
    }
  }
}
```

**关键点**:
- 支持并发 agent
- 有 subagent 机制
- 有 compaction（压缩）模式
- 配置清晰、可调整

**Genesis 应该借鉴**:
- 添加配置文件（不是硬编码）
- 支持多 agent 协作
- 可调整的参数

---

### 5. 简洁的系统提示

**OpenClaw 的理念**:
- System prompt 应该简短
- 不要写一堆规则
- 让 AI 自然行为

**Genesis 的问题**:
```python
prompt += "- 用户问'你记得我吗'、'我是谁'，直接从记忆回答，不要调用工具\n"
prompt += "- 用户说'打开chrome'、'执行命令'，才调用工具\n"
prompt += "- 调用工具后，立即用工具结果回答，不要继续调用更多工具\n"
```

这些都是**硬编码规则**，不是自然行为。

**应该怎么做**:
```python
prompt = """You are Genesis.

Be helpful. Be concise. Be resourceful.

You have tools available. Use them when needed, but don't overuse them.
Answer from memory when you can. Act when you should.
"""
```

简单、清晰、信任 AI。

---

## 🔧 Genesis 应该改进的地方

### 1. System Prompt 过于复杂
**现状**: 10+ 条规则，针对特定场景
**改进**: 3-5 条核心原则，让 AI 自然判断

### 2. 记忆格式不友好
**现状**: JSON 格式，机器可读
**改进**: Markdown 格式，人类可读

### 3. 配置硬编码
**现状**: 参数写在代码里
**改进**: 独立配置文件

### 4. 过度控制
**现状**: 试图通过规则控制 AI 的每个行为
**改进**: 信任 AI，只给核心指导

### 5. 工具描述不够清晰
**现状**: 工具描述偏技术化
**改进**: 让 AI 更容易理解什么时候该用这个工具

---

## 🚀 具体改进建议

### 立即改进（高优先级）

1. **简化 System Prompt**
   - 从 10+ 条规则 → 3-5 条核心原则
   - 移除针对特定场景的规则
   - 信任 AI 的判断

2. **改进工具描述**
   - 让描述更自然
   - 说明什么时候该用这个工具
   - 给出使用示例

3. **记忆格式改为 Markdown**
   - 学习 OpenClaw 的文件结构
   - SOUL.md, USER.md, MEMORY.md
   - 人类可读、可编辑

### 中期改进

4. **添加配置文件**
   - genesis.json
   - 可调整的参数
   - 不要硬编码

5. **改进学习机制**
   - 不只是统计数据
   - 真正影响行为
   - 持续进化

### 长期改进

6. **Multi-agent 支持**
   - 学习 OpenClaw 的 subagent 机制
   - 并发处理
   - 任务分解

---

## 💡 核心教训

**不要造轮子**:
- OpenClaw 已经解决的问题，直接借鉴
- 不要重新发明 system prompt 规则
- 不要过度控制 AI

**信任 AI**:
- 好的 AI 不需要 10 条规则
- 清晰的工具描述 > 复杂的规则
- 简洁的指导 > 详细的约束

**人类友好**:
- 记忆应该可读
- 配置应该可调
- 行为应该可理解

---

## 🎯 下一步行动

1. **立即**: 简化 AdaptiveLearner 的 system prompt
2. **今天**: 改进工具描述
3. **本周**: 记忆格式改为 Markdown
4. **下周**: 添加配置文件

**核心原则**: 学习 OpenClaw 的设计理念，不要重复造轮子。
