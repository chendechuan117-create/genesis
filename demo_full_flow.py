
import sys
import asyncio
import logging
from pathlib import Path

# 添加路径 (Dynamically resolve project root)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanogenesis.agent import NanoGenesis

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    print("\n🚀 NanoGenesis 全流程演示 (Meta-Cognition -> Execution)")
    print("=" * 60)

    # 1. 初始化
    import os
    # api_key = "sk-..." # 已移除
    api_key = os.getenv("DEEPSEEK_API_KEY", "your-api-key")
    agent = NanoGenesis(
        api_key=api_key,
        model="deepseek-chat",
        enable_optimization=True  # 开启优化以激活元认知
    )
    
    # 2. 定义复杂问题
    problem = "我想搭建一个自动化的个人博客，要求使用 Hugo，部署在 GitHub Pages，并且每次 push 自动更新。请给出方案并执行第一步检查。"
    context = "环境：Linux, 已安装 git, hugo, docker。"
    
    print(f"📝 用户问题: {problem}")
    
    # 3. 执行流程
    print("\n🔄 开始处理 (Agent.process)...")
    try:
        result = await agent.process(problem, user_context=context)
        
        print("\n✅ 执行完成")
        print("=" * 60)
        
        # 检查是否生成了优化信息
        opt_info = result.get('optimization_info', {})
        if opt_info:
            print(f"自优化信息: {opt_info}")
            
        print(f"\n最终响应:\n{result['response']}")
        
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        # 如果是网络错误，我们可以模拟展示预期的流程
        if "Remote end closed connection" in str(e) or "urlopen error" in str(e):
            print("\n⚠️ 网络连接不稳定，演示预期流程：")
            print("1. [Meta-Cognition] 识别为复杂问题 -> 启动多面体协议")
            print("2. [Thinking] 生成3条路径 (Direct/Safe/Creative) -> 剪枝")
            print("3. [Planning] 选择路径 B (Safe) -> 生成 Execution Plan")
            print("4. [Execution] AgentLoop 接收 Plan -> 执行 'hugo version' 检查环境")
            print("5. [Response] 返回检查结果并建议下一步")

if __name__ == "__main__":
    asyncio.run(main())
