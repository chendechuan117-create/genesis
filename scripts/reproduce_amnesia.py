
import asyncio
import sys
from pathlib import Path
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reproduce")

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.factory import GenesisFactory

async def main():
    print("🚀 Initializing Agent...")
    agent = GenesisFactory.create_common(enable_optimization=True)
    
    print("\n🗣️ Turn 1: 'My name is Neo.'")
    result1 = await agent.process("My name is Neo.")
    print(f"🤖 Agent: {result1['response'][:100]}...")
    
    print("\n🗣️ Turn 2: 'What is my name?'")
    result2 = await agent.process("What is my name?")
    print(f"🤖 Agent: {result2['response']}")
    
    if "Neo" in result2['response']:
        print("\n✅ Memory Working: Agent remembered the name.")
    else:
        print("\n❌ Memory FAIL: Agent forgot the name.")
        if "[CLARIFICATION_REQUIRED]" in result2['response']:
            print("   (Triggered Clarification Protocol)")

if __name__ == "__main__":
    asyncio.run(main())
