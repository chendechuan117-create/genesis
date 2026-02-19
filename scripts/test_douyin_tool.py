
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, "/home/chendechusn/Genesis/nanogenesis")

from genesis.core.factory import GenesisFactory

async def main():
    print("🚀 Initializing NanoGenesis...")
    # Initialize with mocked provider to avoid API calls, we just want to test tool registration
    agent = GenesisFactory.create_common(enable_optimization=False)
    
    # Access using public methods
    print(f"📦 Registered Tools: {agent.tools.list_tools()}")
    
    if "douyin_analysis" in agent.tools:
        print("✅ DouyinAnalysisTool found!")
        
        tool = agent.tools.get("douyin_analysis")
        print("🏃 Executing tool...")
        result = await tool.execute(account_url="https://v.douyin.com/knowledge_user/")
        print("📄 Result prefix:", result[:100])
        
        if "financial_forecast" in result:
             print("✅ Tool execution successful")
        else:
             print("❌ Tool execution returned unexpected format")
    else:
        print("❌ DouyinAnalysisTool NOT found in registry")

if __name__ == "__main__":
    asyncio.run(main())
