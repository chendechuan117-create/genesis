# Genesis 使用指南

**版本**: v0.2.0 - Polyhedron Edition

---

## 🚀 快速开始

### 1. 基础使用

```python
import asyncio
from agent_with_polyhedron import NanoGenesisWithPolyhedron

async def main():
    # 创建 Agent
    agent = NanoGenesisWithPolyhedron(
        api_key="your-deepseek-api-key",
        model="deepseek-chat",
        user_persona_path="./data/user_persona.json"
    )
    
    # 处理请求
    result = await agent.process(
        user_input="Docker 容器启动失败，permission denied",
        intent_type="problem"
    )
    
    # 查看结果
    print(result['response'])

asyncio.run(main())
```

---

## 📋 完整示例

### 示例 1: 带上下文的问题诊断

```python
import asyncio
from agent_with_polyhedron import NanoGenesisWithPolyhedron

async def diagnose_problem():
    agent = NanoGenesisWithPolyhedron(
        api_key="sk-xxx",
        model="deepseek-chat"
    )
    
    # 模拟可用的记忆文件
    available_contexts = {
        'docker_issue_1': 'Docker 权限问题：用户不在 docker 组...',
        'linux_perm_1': 'Linux 权限管理：chmod, chown...',
        'docker_compose_1': 'Docker Compose 配置示例...',
    }
    
    # 处理问题
    result = await agent.process(
        user_input="Docker 容器启动失败，提示 permission denied",
        available_contexts=available_contexts,
        intent_type="problem",
        constraints={
            'budget': 0,
            'environment': 'Linux',
            'preferences': '本地化、开源'
        }
    )
    
    # 查看结果
    print("="*60)
    print("AI 响应:")
    print("="*60)
    print(result['response'])
    
    print("\n" + "="*60)
    print("性能指标:")
    print("="*60)
    print(f"复杂度: {result['complexity']}")
    print(f"使用多面体: {result['use_polyhedron']}")
    print(f"筛选的上下文: {len(result['selected_contexts'])} 个")
    print(f"编码上下文: {result['encoded_context'][:80]}...")

asyncio.run(diagnose_problem())
```

---

## 🔧 高级用法

### 1. 使用对话历史

```python
from agent_with_polyhedron import NanoGenesisWithPolyhedron
from core.conversation import ConversationManager

async def chat_with_history():
    agent = NanoGenesisWithPolyhedron(api_key="sk-xxx")
    conv_manager = ConversationManager()
    
    session_id = "user_123_session"
    
    # 第一轮对话
    user_input = "我的 Docker 容器启动失败"
    
    # 添加用户消息
    conv_manager.add_message(session_id, "user", user_input)
    
    # 处理请求
    result = await agent.process(user_input, intent_type="problem")
    
    # 添加 AI 响应
    conv_manager.add_message(session_id, "assistant", result['response'])
    
    # 第二轮对话（带历史）
    user_input_2 = "具体怎么操作？"
    conv_manager.add_message(session_id, "user", user_input_2)
    
    # 获取历史上下文
    history = conv_manager.get_context_messages(session_id, max_tokens=2000)
    
    # 处理（可以将历史传给 API）
    result_2 = await agent.process(user_input_2, intent_type="task")
    conv_manager.add_message(session_id, "assistant", result_2['response'])
    
    # 查看对话摘要
    summary = conv_manager.get_summary(session_id)
    print(f"对话轮次: {summary['total_messages']}")
    print(f"时长: {summary['duration']}")
```

### 2. 动态生成工具

```python
from intelligence.tool_generator import ToolGenerator

async def create_custom_tool():
    # 创建工具生成器
    generator = ToolGenerator(api_key="sk-xxx")
    
    # 描述需求
    tool_description = """
    创建一个查询 GitHub 仓库信息的工具。
    
    功能：
    - 输入：仓库名称（格式：owner/repo）
    - 输出：仓库的 stars、forks、issues 数量
    """
    
    # 生成工具
    tool_file = generator.generate_tool(tool_description, "github_repo_info")
    
    if tool_file:
        # 加载工具
        tool = generator.load_tool(tool_file)
        
        # 注册到 Agent
        agent = NanoGenesisWithPolyhedron(api_key="sk-xxx")
        agent.tools.register(tool)
        
        print(f"✓ 工具已注册: {tool.name}")
        print(f"  可用工具数: {len(agent.tools)}")
```

### 3. 查看用户画像

```python
from agent_with_polyhedron import NanoGenesisWithPolyhedron

async def view_user_profile():
    agent = NanoGenesisWithPolyhedron(
        api_key="sk-xxx",
        user_persona_path="./data/user_persona.json"
    )
    
    # 模拟几次交互
    interactions = [
        "Docker 容器权限问题",
        "Python 模块导入错误",
        "Git 合并冲突"
    ]
    
    for user_input in interactions:
        await agent.process(user_input, intent_type="problem")
    
    # 查看用户画像
    persona = agent.get_user_persona_summary()
    print(persona)
    
    # 查看统计
    stats = agent.get_statistics()
    print(f"\n交互次数: {stats['user_interactions']}")
    print(f"置信度: {stats['user_confidence']:.2f}")
    print(f"专业领域: {', '.join(stats['user_expertise'])}")
```

---

## 🎯 使用场景

### 场景 1: 技术问题诊断

```python
# 用户遇到技术问题
result = await agent.process(
    user_input="Python 导入模块失败，ModuleNotFoundError",
    intent_type="problem"
)
# Genesis 会：
# 1. 诊断问题（决策树匹配）
# 2. 搜索相关策略
# 3. 筛选相关记忆
# 4. 使用多面体框架思考
# 5. 给出最优解 + 代价
```

### 场景 2: 执行任务

```python
# 用户需要执行任务
result = await agent.process(
    user_input="读取 /tmp/config.json 文件",
    intent_type="task"
)
# Genesis 会：
# 1. 识别为简单任务
# 2. 不使用多面体（避免浪费）
# 3. 直接调用 read_file 工具
# 4. 返回结果
```

### 场景 3: 知识查询

```python
# 用户查询知识
result = await agent.process(
    user_input="Docker 和 Kubernetes 的区别是什么？",
    intent_type="query"
)
# Genesis 会：
# 1. 识别为查询
# 2. 搜索相关记忆
# 3. 调用 web_search（如果需要）
# 4. 综合回答
```

---

## ⚙️ 配置选项

### Agent 初始化参数

```python
agent = NanoGenesisWithPolyhedron(
    api_key="sk-xxx",              # DeepSeek API key
    base_url="https://api.deepseek.com",  # API 地址
    model="deepseek-chat",         # 模型名称
    max_iterations=10,             # 最大迭代次数
    user_persona_path="./data/user_persona.json",  # 用户画像路径
    local_llm=None                 # 本地 LLM（可选）
)
```

### Process 参数

```python
result = await agent.process(
    user_input="问题描述",         # 用户输入
    available_contexts={...},      # 可用上下文（可选）
    intent_type="problem",         # 意图类型：problem/task/query
    constraints={                  # 约束条件（可选）
        'budget': 0,
        'environment': 'Linux',
        'preferences': '本地化'
    }
)
```

---

## 📊 返回结果

```python
result = {
    'response': '...',              # AI 响应
    'metrics': {...},               # 性能指标
    'complexity': 'medium',         # 复杂度
    'use_polyhedron': True,         # 是否使用多面体
    'encoded_context': '...',       # 编码后的上下文
    'selected_contexts': [...],     # 筛选的上下文
    'diagnosis': {...},             # 诊断结果
    'strategies': [...]             # 策略列表
}
```

---

## 🔍 调试和监控

### 查看性能指标

```python
from optimization.polyhedron_optimizer import PolyhedronOptimizer

optimizer = PolyhedronOptimizer()

# 记录交互
optimizer.record_interaction(
    user_input="...",
    response="...",
    metrics={
        'total_tokens': 1866,
        'token_saved': 27.1,
        'cache_hit_rate': 97
    },
    use_polyhedron=True
)

# 获取报告
report = optimizer.get_optimization_report()
print(f"总交互: {report['total_interactions']}")
print(f"多面体使用率: {report['polyhedron_usage']['percentage']:.1f}%")
print(f"平均 Token 节省: {report['performance']['avg_token_saving']:.1f}%")
```

---

## 🐛 常见问题

### Q: API 调用失败？
A: 检查 API key 是否正确，或使用 curl 测试：
```bash
curl -X POST https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"test"}]}'
```

### Q: 本地 LLM 筛选不准确？
A: 使用 7B 模型并优化提示词：
```python
from intelligence.context_filter import LocalLLMContextFilter
from intelligence.context_filter import OllamaLLM

ollama = OllamaLLM(model="qwen2.5:7b")
filter = LocalLLMContextFilter(local_llm=ollama, max_files=5)
```

### Q: 如何查看对话历史？
A: 使用 ConversationManager：
```python
from core.conversation import ConversationManager

manager = ConversationManager()
messages = manager.get_messages("session_id")
for msg in messages:
    print(f"[{msg.role}] {msg.content}")
```

---

## 📚 更多文档

- `README.md` - 项目介绍
- `ARCHITECTURE.md` - 架构设计
- `POLYHEDRON_FRAMEWORK.md` - 多面体框架详解
- `GENESIS_ARCHITECTURE.md` - 完整架构图
- `STATUS.md` - 项目状态

---

## 🎉 开始使用

```bash
# 1. 进入项目目录
cd /home/chendechusn/nanabot/nanogenesis

# 2. 创建测试脚本
cat > my_test.py << 'EOF'
import asyncio
from agent_with_polyhedron import NanoGenesisWithPolyhedron

async def main():
    agent = NanoGenesisWithPolyhedron(
        api_key="your-api-key-here"
    )
    
    result = await agent.process(
        user_input="你的问题",
        intent_type="problem"
    )
    
    print(result['response'])

asyncio.run(main())
EOF

# 3. 运行
python3 my_test.py
```

---

**Genesis v0.2.0 - 越用越聪明的 AI Agent** 🚀
