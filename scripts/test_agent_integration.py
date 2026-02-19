
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.factory import GenesisFactory

async def test_agent_integration():
    print("🚀 Initializing NanoGenesis via Factory...")
    
    # Create agent using common factory method
    agent = GenesisFactory.create_common(user_id="test_user")
    
    # Verify MissionManager injection
    print("\n1. Verifying MissionManager Injection")
    if hasattr(agent, 'mission_manager') and agent.mission_manager:
        print(f"   ✅ MissionManager found: {agent.mission_manager}")
    else:
        print("   ❌ MissionManager NOT found on Agent!")
        exit(1)
        
    # Verify Active Mission Logic (should be None or auto-created in process)
    print("\n2. Checking Active Mission")
    mission = agent.mission_manager.get_active_mission()
    if mission:
        print(f"   ℹ️ Found active mission: {mission.objective}")
    else:
        print("   ℹ️ No active mission (Expected for fresh session)")
        
    print("\n✅ Agent Integration Test PASSED!")

if __name__ == "__main__":
    asyncio.run(test_agent_integration())
