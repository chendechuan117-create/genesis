
import sys
import asyncio
from pathlib import Path
import logging

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.agent import NanoGenesis
from nanogenesis.core.config import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def verify_integrity():
    print("\n🚀 Starting Verification of NanoGenesis v2.1 (Single-Brain)...")
    
    # 1. Initialize Agent
    try:
        agent = NanoGenesis(enable_optimization=True)
        print("✅ Agent Initialized Successfully")
    except Exception as e:
        print(f"❌ Initialization Failed: {e}")
        return

    # 2. Check Tools
    print("\n🛠️ Tool Integrity Check:")
    tool_names = agent.tools.list_tools()
    print(f"  Detected Tools: {tool_names}")
    
    required = ['shell', 'browser_tool', 'web_search', 'skill_creator']
    
    for req in required:
        if req in tool_names:
            print(f"  ✅ {req}: Active")
        else:
            print(f"  ❌ {req}: MISSING")
            
    # 3. Check Configuration (Tavily)
    print("\n🔑 Configuration Check:")
    if config.tavily_api_key:
        print(f"  ✅ Tavily API Key: Loaded ({config.tavily_api_key[:5]}...)")
    else:
        print("  ❌ Tavily API Key: MISSING")

    # 4. Functional Test (Polyhedron + Web Search)
    print("\n🧠 Functional Test: 'Search DeepSeek News'")
    print("  (Expectation: Polyhedron Meta-Analysis -> WebSearchTool)")
    
    try:
        result = await agent.process("帮我搜索关于 DeepSeek Coder V2 的最新技术新闻")
        
        print("\n🤖 Response Preview:")
        print(result['response'][:200] + "...")
        
        print("\n📊 Metrics:")
        print(f"  - Tools Used: {result['metrics'].tools_used}")
        print(f"  - Success: {result['success']}")
        
    except Exception as e:
        print(f"❌ Execution Failed: {e}")

    # Cleanup
    if agent.scheduler:
        await agent.scheduler.stop()

if __name__ == "__main__":
    asyncio.run(verify_integrity())
