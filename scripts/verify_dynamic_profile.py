
import asyncio
import sys
import json
from pathlib import Path
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_profile")

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.factory import GenesisFactory

async def main():
    print("🚀 Initializing Agent...")
    agent = GenesisFactory.create_common(enable_optimization=True)
    
    # 1. State a preference
    print("\n🗣️ Turn 1: 'Please speak Chinese and remember that I love strawberries.'")
    # Using a slightly complex prompt to test extraction
    result1 = await agent.process("Please speak Chinese and remember that I love strawberries.")
    print(f"🤖 Agent: {result1['response'][:100]}...")
    
    # 2. Check Profile File
    profile_path = Path.home() / ".nanogenesis" / f"profile_{agent.user_id}.json"
    if profile_path.exists():
        with open(profile_path, 'r') as f:
            data = json.load(f)
            prefs = data.get('preferences', {})
            print(f"\n📂 Profile Preferences: {prefs}")
            
            if "strawberry" in str(prefs).lower() or "strawberries" in str(prefs).lower():
                print("✅ TEST PASS: Strawberry preference persisted.")
            else:
                print("❌ TEST FAIL: Strawberry not found.")
                
            if "chinese" in str(prefs).lower():
                 print("✅ TEST PASS: Language preference persisted.")
            else:
                 print("❌ TEST FAIL: Language not found.")
    else:
        print("❌ TEST FAIL: Profile file not created.")

if __name__ == "__main__":
    asyncio.run(main())
