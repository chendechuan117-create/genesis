
import sys
import asyncio
import logging
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanogenesis.agent import NanoGenesis

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("demo_memory")

async def main():
    print("🧠 NanoGenesis 长期记忆系统演示")
    print("=" * 60)

    # 1. 初始化 Agent
    agent = NanoGenesis(enable_optimization=True)
    
    # 2. 注入记忆 (模拟之前的对话)
    print("📥 正在注入记忆...")
    agent.memory.add("用户喜欢使用 Arch Linux")
    agent.memory.add("用户的 API Key 是 sk-********************************")
    agent.memory.add("项目代号是 Polyhedron")
    
    print("✓ 记忆已保存")
    print("-" * 60)
    
    # 3. 测试检索 (通过 TF-IDF)
    # Case 1: 直接相关
    query1 = "我应该装什么 Linux?"
    print(f"🔍 测试查询 1: {query1}")
    results = agent.memory.search(query1)
    if results:
        print(f"   命中: {results[0]['content']}")
    else:
        print("   未命中 (TF-IDF 限制)")
        
    # Case 2: 关键词匹配
    query2 = "我的 API Key 是多少?"
    print(f"🔍 测试查询 2: {query2}")
    results = agent.memory.search(query2)
    if results:
        print(f"   命中: {results[0]['content']}")
    else:
        print("   未命中")

    print("-" * 60)
    
    # 4. 集成测试 (Meta-Cognition Flow)
    # 观察是否能将记忆注入到 System Context 中
    final_query = "帮我生成一个 Linux 安装脚本"
    print(f"🤖 集成测试: {final_query}")
    print("   (观察日志中是否出现 '检索到相关记忆')")
    
    try:
        await agent.process(final_query)
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("✅ 记忆系统演示完成")

if __name__ == "__main__":
    asyncio.run(main())
