"""
NanoGenesis Capability Benchmark
Testing against user-defined scenarios to compare with OpenClaw.
"""

import sys
import asyncio
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.agent import NanoGenesis

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

async def run_benchmark():
    print("🚀 Starting Capability Benchmark...")
    
    # Initialize Agent (Zero-Conf)
    try:
        agent = NanoGenesis(enable_optimization=True)
        if agent.scheduler:
            await agent.scheduler.start()
        print("✅ Agent Initialized")
    except Exception as e:
        print(f"❌ Init Failed: {e}")
        return

    scenarios = [
        {
            "name": "1. Temporal Awareness ('Yesterday')",
            "input": "你知道昨天干了什么吗？"
        },
        {
            "name": "2. Environment Perception",
            "input": "你能感知当前的环境吗？请把环境信息自动录入到记忆里。"
        },
        {
            "name": "3. Action Execution ('Open Chrome')",
            "input": "帮我打开 chrome"
        },
        {
            "name": "4. Correction & Learning (Part 1)",
            "input": "我觉得 NanoGenesis 这个名字太长了，以后叫你 '小N'。"
        },
        {
            "name": "4. Correction & Learning (Part 2 - Verify)",
            "input": "我是谁？你又是谁？"
        }
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n--- Scenario {scenario['name']} ---")
        print(f"👤 User: {scenario['input']}")
        
        try:
            result = await agent.process(scenario['input'])
            print(f"🤖 Agent: {result['response']}")
            
            if result['metrics'].tools_used:
                print(f"🛠️ Tools: {result['metrics'].tools_used}")
                
            if 'optimization_info' in result and result['optimization_info']:
                print(f"✨ Optimization: {result['optimization_info']}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            
    # Cleanup
    if agent.scheduler:
        await agent.scheduler.stop()

if __name__ == "__main__":
    asyncio.run(run_benchmark())
