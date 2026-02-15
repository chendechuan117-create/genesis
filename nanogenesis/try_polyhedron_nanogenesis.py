
import sys
import asyncio
import logging
from pathlib import Path

# 添加 nanabot 路径 (父目录)
# 添加路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanogenesis.agent import NanoGenesis

# 设置日志
logging.basicConfig(level=logging.INFO)

async def main():
    print("🚀 启动 NanoGenesis + Polyhedron Protocol 集成测试")
    print("=" * 60)

    # 1. 加载协议
    # 1. 加载协议
    protocol_path = list(Path(__file__).parent.glob("**/polyhedron_protocol_bot_v2.txt"))[0]
    if not protocol_path.exists():
         protocol_path = Path(__file__).parent / "intelligence" / "prompts" / "polyhedron_protocol_bot_v2.txt"
    try:
        with open(protocol_path, "r", encoding="utf-8") as f:
            protocol = f.read()
        print("✓ 已加载多面体协议 (Bot v2)")
    except Exception as e:
        print(f"❌ 加载协议失败: {e}")
        return

    # 2. 初始化 Agent
    # 使用用户的 DeepSeek API Key
    # api_key = "sk-..." # 已移除
    api_key = os.getenv("DEEPSEEK_API_KEY", "your-api-key")
    
    agent = NanoGenesis(
        api_key=api_key,
        model="deepseek-chat",
        max_iterations=5
    )
    print("✓ NanoGenesis Agent 已初始化")

    # 3. 构造测试问题
    user_problem = "我想在 Linux 上自动备份我的 Obsidian 笔记到 GitHub，每天一次，怎么办？"
    user_context = "环境：Arch Linux (EndeavourOS)，已安装 git。笔记路径: ~/Documents/Obsidian"
    
    print(f"\n📝 用户问题: {user_problem}")
    print(f"📝 上下文: {user_context}")
    
    # 4. 构造包含协议的 Prompt
    # 将协议作为 System Prompt 的一部分注入
    # 注意：这里我们手动替换 {{variables}}，模拟 template 渲染
    full_prompt = protocol.replace("{{problem}}", user_problem)\
                          .replace("{{context}}", user_context)\
                          .replace("{{constraints}}", "无特殊约束")\
                          .replace("{{priority}}", "中等")

    print("\n🧠 正在进行元认知分析 (Polyhedron Thinking)...")
    
    # 我们直接调用 Agent 的 provider 来获取元认知分析结果 (Plan)
    # 因为目前的 NanoGenesis.process 是直接跑 Loop，我们想先获取 Plan
    
    # 构造消息
    messages = [
        {"role": "system", "content": "你是智能 Agent 的元认知决策引擎。"},
        {"role": "user", "content": full_prompt}
    ]
    
    try:
        # 调用 LLM 获取 Plan
        response = await agent.provider.chat(messages=messages)
        plan_content = response.content
        
        print("\n" + "=" * 60)
        print("🤖 多面体元认知输出 (Execution Plan)")
        print("=" * 60)
        print(plan_content)
        print("=" * 60)
        
        # 5. (可选) 如果生成的 Plan 包含工具调用，我们可以尝试让 Agent 执行
        # 这里仅展示 Agent 的基本运行能力
        print("\n🏃 尝试运行 Agent (基础 ReAct 模式)...")
        result = await agent.process(user_problem, user_context=user_context)
        
        print("\n✅ Agent 执行结果:")
        print(f"响应: {result['response']}")
        print(f"Token 使用: {result['metrics'].total_tokens if result['metrics'] else 'N/A'}")
        
    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
