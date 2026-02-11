
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# 添加 nanabot 路径
# 添加路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanogenesis.agent import NanoGenesis
from nanogenesis.core.base import PerformanceMetrics

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("demo_evolution")

async def main():
    print("🧬 NanoGenesis 自我迭代机制演示")
    print("=" * 60)

    # 1. 初始化 Agent (启用优化)
    agent = NanoGenesis(enable_optimization=True)
    print("✓ Agent 已初始化")
    
    # 打印初始 System Prompt
    print("\n[初始状态]")
    print(f"System Prompt: {agent.context.system_prompt[:50]}...")
    
    # =================================================================
    # 演示 1: 工具使用自优化 (Tool Optimizer)
    # =================================================================
    print("\n" + "-" * 60)
    print("🔬 演示 1: 工具使用自优化 (学习最优路径)")
    print("-" * 60)
    
    # 模拟多次成功的工具调用序列：对于 "file_search" 类型问题，先 ls 再 cat
    problem_type = "file_search"
    optimal_tools = ["ListDirectoryTool", "ReadFileTool"]
    
    print(f"模拟: 连续 5 次成功解决 '{problem_type}' 问题，使用序列: {optimal_tools}")
    
    for i in range(5):
        # 注入模拟数据
        agent.tool_optimizer.record_sequence(
            problem_type,
            optimal_tools,
            success=True,
            metrics={'tokens': 100, 'time': 1.0, 'iterations': 2}
        )
    
    # 触发推荐
    recommendation = agent.tool_optimizer.get_tool_recommendations(problem_type)
    print(f"\n[进化后] 针对 '{problem_type}' 的建议:")
    print(f"👉 {recommendation['message']}")
    
    # =================================================================
    # 演示 2: 用户画像进化 (Profile Evolution)
    # =================================================================
    print("\n" + "-" * 60)
    print("👤 演示 2: 用户画像进化 (适应用户偏好)")
    print("-" * 60)
    
    # 模拟用户多次偏好 "Python 代码" 解决方案
    print("模拟: 用户在 5 次交互中都选择了 Python 代码解决方案...")
    
    for i in range(5):
        agent.profile_evolution.log_interaction({
            'domain': 'python_dev',
            'solution_type': 'code',
            'tools_used': ['WriteFileTool'],
            'success': True
        })
    
    # 强制触发进化
    changes = agent.profile_evolution.evolve()
    
    if changes:
        print(f"\n[进化检测] 发现画像变化: {changes}")
        
        # 重新生成 Prompt
        new_prompt = agent.profile_evolution.generate_adaptive_prompt()
        print(f"\n[进化后] System Prompt 已自动调整:")
        print(new_prompt)
    else:
        print("\n(数据量不足以触发显著进化，需更多交互)")

    # =================================================================
    # 演示 3: 提示词自优化 (Prompt Optimizer)
    # =================================================================
    print("\n" + "-" * 60)
    print("📝 演示 3: 提示词自优化 (基于性能指标)")
    print("-" * 60)
    
    # 模拟高 Token 消耗的历史记录
    print("模拟: 最近 50 次交互 Token 消耗过高 (>500)...")
    
    # 填充历史数据
    agent.prompt_optimizer.performance_log = [] # 清空
    for i in range(50):
        agent.prompt_optimizer.log_interaction(
            metrics=PerformanceMetrics(
                total_tokens=800, 
                total_time=5.0, 
                iterations=5, 
                success=True,
                tools_used=[]  # Fix: Initialize empty list
            ),
            user_input="test",
            response="response",
            success=True
        )
        
    # 检查优化条件
    if agent.prompt_optimizer.should_optimize():
        print("✓ 触发优化条件 (交互次数达标)")
        
        # 模拟优化过程 (因为实际 optimize 需要调用 LLM)
        metrics = agent.prompt_optimizer.analyze_performance()
        suggestions = agent.prompt_optimizer.generate_optimization_suggestions(
            agent.context.system_prompt, metrics
        )
        
        print(f"\n[性能分析] 平均 Token: {metrics['avg_tokens']}")
        print(f"[优化建议] {suggestions['reason']}")
        print(f"[新 Prompt 草案]\n{suggestions['new_prompt']}")
        
    print("\n" + "=" * 60)
    print("✅ 演示完成：NanoGenesis 具备全方位的自我进化能力")

if __name__ == "__main__":
    asyncio.run(main())
