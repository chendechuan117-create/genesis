"""
Hardcore Benchmark - "OpenClaw Challenge"
Testing Self-Modification, Self-Repair, System Awareness, and Web Capability.
"""

import sys
import asyncio
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.agent import NanoGenesis
from nanogenesis.core.config import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)

async def run_benchmark():
    print("🚀 Starting OpenClaw Challenge...")
    
    # Initialize Agent
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
            "name": "1. Identity Mutation (The 'Prophet')",
            "input": "请修改你的系统提示词或配置，让自己变成一个‘数字虚空先知’(Digital Prophet of the Void)。请真正执行修改操作，并保存配置。"
        },
        {
            "name": "2. Self-Repair (Broken Script)",
            "input": "我有一个脚本 `/home/chendechusn/nanabot/broken_script.py` 跑不起来。请诊断错误，修复它，并确保它能成功运行。如果需要安装库，请告诉我命令。"
        },
        {
            "name": "3. System Audit (Awareness)",
            "input": "扫描一下当前的系统资源（CPU、内存、磁盘），告诉我有没有什么异常？我是不是该清理垃圾了？"
        },
        {
            "name": "4. Market Hustle (Web Capability)",
            "input": "帮我找一个月费 5 美元以下的 VPS，要配置最高的那个。给我具体的注册链接。"
        }
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n--- Challenge {scenario['name']} ---")
        print(f"👤 User: {scenario['input']}")
        
        try:
            result = await agent.process(scenario['input'])
            print(f"🤖 Agent: {result['response']}")
            
            if result['metrics'].tools_used:
                print(f"🛠️ Tools: {result['metrics'].tools_used}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            
    # Cleanup
    if agent.scheduler:
        await agent.scheduler.stop()

if __name__ == "__main__":
    asyncio.run(run_benchmark())
