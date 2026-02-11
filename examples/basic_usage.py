"""
NanoGenesis 基础使用示例
"""

import asyncio
from nanogenesis import NanoGenesis
from nanogenesis.core import MockLLMProvider


async def example_basic():
    """基础使用示例"""
    print("=" * 60)
    print("示例 1: 基础使用")
    print("=" * 60)
    
    # 初始化（使用 Mock Provider 演示）
    agent = NanoGenesis()
    agent.provider = MockLLMProvider()
    
    # 处理问题
    result = await agent.process("Hello, NanoGenesis!")
    
    print(f"\n用户输入: Hello, NanoGenesis!")
    print(f"Agent 响应: {result['response']}")
    print(f"Token 使用: {result['metrics'].tokens}")
    print(f"耗时: {result['metrics'].time:.2f}s")
    print(f"迭代次数: {result['metrics'].iterations}")


async def example_multiple_interactions():
    """多次交互示例"""
    print("\n" + "=" * 60)
    print("示例 2: 多次交互")
    print("=" * 60)
    
    agent = NanoGenesis()
    agent.provider = MockLLMProvider()
    
    questions = [
        "Docker 容器启动失败",
        "Python 依赖冲突",
        "Git 合并冲突",
    ]
    
    for i, question in enumerate(questions, 1):
        result = await agent.process(question)
        print(f"\n问题 {i}: {question}")
        print(f"响应: {result['response']}")
        print(f"Token: {result['metrics'].tokens}")
    
    # 查看统计
    stats = agent.get_stats()
    print("\n" + "-" * 60)
    print("统计信息:")
    print(f"  总交互次数: {stats['total_interactions']}")
    print(f"  平均 Token: {stats['avg_tokens']:.0f}")
    print(f"  平均耗时: {stats['avg_time']:.2f}s")
    print(f"  成功率: {stats['success_rate']:.1%}")


async def example_custom_context():
    """自定义上下文示例"""
    print("\n" + "=" * 60)
    print("示例 3: 自定义用户上下文")
    print("=" * 60)
    
    agent = NanoGenesis()
    agent.provider = MockLLMProvider()
    
    # 添加用户上下文
    user_context = """
    用户画像：
    - 专业领域: Docker, Kubernetes
    - 解题风格: 偏好修改配置文件
    - 第一反应: 检查日志
    """
    
    result = await agent.process(
        "容器无法访问宿主机文件",
        user_context=user_context
    )
    
    print(f"\n用户输入: 容器无法访问宿主机文件")
    print(f"用户上下文: {user_context.strip()}")
    print(f"Agent 响应: {result['response']}")


async def example_update_system_prompt():
    """更新系统提示词示例"""
    print("\n" + "=" * 60)
    print("示例 4: 更新系统提示词")
    print("=" * 60)
    
    agent = NanoGenesis()
    agent.provider = MockLLMProvider()
    
    # 第一次交互
    result1 = await agent.process("问题 1")
    print(f"\n使用默认提示词:")
    print(f"响应: {result1['response']}")
    
    # 更新系统提示词
    new_prompt = """
    你是一个专注于 Docker 问题的专家。
    
    你的特点：
    1. 总是先检查日志
    2. 优先使用配置文件解决问题
    3. 给出具体的命令示例
    """
    
    agent.update_system_prompt(new_prompt)
    
    # 第二次交互
    result2 = await agent.process("问题 2")
    print(f"\n使用新提示词:")
    print(f"响应: {result2['response']}")


async def main():
    """运行所有示例"""
    await example_basic()
    await example_multiple_interactions()
    await example_custom_context()
    await example_update_system_prompt()
    
    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
