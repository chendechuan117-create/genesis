import sys
import asyncio
import logging
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.agent import NanoGenesis

# Setup logging
logging.basicConfig(level=logging.WARN)
logger = logging.getLogger("MemoryTest")
logger.setLevel(logging.INFO)

async def main():
    print("🚀 Testing Memory Retention...")
    try:
        agent = NanoGenesis(enable_optimization=True)
        session_id = agent.session_manager.session_id
        print(f"✨ Session: {session_id}")
        
        # Turn 1: Seed Information
        print("\n👉 User: 'My codename is Project-X.'")
        res1 = await agent.process("My codename is Project-X.")
        if res1['success']:
             print(f"✅ Agent: {res1['response'][:100]}...")
        else:
             print(f"❌ Turn 1 Failed: {res1['response']}")
             return

        # Turn 2: Recall Information
        print("\n👉 User: 'What is my codename?'")
        res2 = await agent.process("What is my codename?")
        
        response = res2['response']
        print(f"✅ Agent: {response}")
        
        if "Project-X" in response or "Project X" in response:
            print("\n✨ MEMORY VERIFICATION PASSED ✨")
        else:
            print("\n❌ MEMORY VERIFICATION FAILED (Amnesia Detected) ❌")
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
