
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# 添加 nanabot 路径
# 添加路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanogenesis.agent import NanoGenesis
from nanogenesis.optimization.behavior_optimizer import Strategy

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("demo_strategy")

async def main():
    print("🧠 NanoGenesis 策略反馈回路演示")
    print("=" * 60)

    # 1. 初始化 Agent
    agent = NanoGenesis(enable_optimization=True)
    
    # 2. 手动注入一条成熟的策略
    # 假设这是之前多次成功交互后沉淀下来的经验
    strategy_id = "strat_hugo_deploy"
    hugo_strategy = Strategy(
        id=strategy_id,
        pattern="deploy hugo blog github pages",
        domain="devops",
        root_cause="User needs automated blog deployment",
        solution="1. Install Hugo (pacman -S hugo)\n2. Create site (hugo new site .)\n3. Git init & submodule theme\n4. Create .github/workflows/gh-pages.yml",
        dead_ends=[],
        success_count=10,
        total_count=10,
        avg_tokens=500.0,
        avg_time=10.0,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # 注入到优化器
    agent.behavior_optimizer.strategies[strategy_id] = hugo_strategy
    print(f"✓ 已注入历史策略: [ID: {strategy_id}] '{hugo_strategy.pattern}'")
    print("-" * 60)
    
    # 3. 发起新的类似提问
    query = "I want to deploy a hugo blog on github pages"
    print(f"📝 用户提问: {query}")
    print("🔄 开始处理 (观察日志是否检索到策略)...")
    print("-" * 60)
    
    # 运行处理 (这将触发元认知阶段)
    # 我们只关心日志输出，不需要真正等待 LLM 完成 (因为它会调用网络)
    try:
        await agent.process(query)
    except Exception as e:
        # 忽略网络错误或其他错误，主要看日志
        pass

if __name__ == "__main__":
    asyncio.run(main())
