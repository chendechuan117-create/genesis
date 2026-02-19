
import asyncio
import sys
from pathlib import Path
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_autonomy")

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.factory import GenesisFactory

async def main():
    print("🚀 Initializing Agent for Autonomy Test...")
    agent = GenesisFactory.create_common(enable_optimization=True)
    
    # 1. Create a Mock Mission
    from genesis.core.mission import Mission
    from datetime import datetime
    import uuid
    
    now = datetime.now().isoformat()
    mock_mission = Mission(
        id=str(uuid.uuid4()),
        objective="Execute the command 'echo Hello Guardian Mode' using the shell tool.",
        status="active",
        created_at=now,
        updated_at=now,
        context_snapshot={},
        error_count=0
    )
    
    print(f"\n🎯 Mission: {mock_mission.objective}")
    print("🤖 Invoking autonomous_step...")
    
    try:
        # 2. Invoke Autonomous Step
        # This skips Awareness and goes straight to Strategy -> Execution
        result = await agent.autonomous_step(mock_mission)
        
        print(f"\n✅ Result: {result}")
        
        # 3. Verification
        if result['status'] == 'success':
            output = result.get('output', "")
            tools = result.get('tools_executed', 0)
            
            if tools > 0:
                print("🌟 SUCCESS: Tool was executed autonomously.")
            else:
                print("⚠️ WARNING: No tools executed (Agent might have just answered textually).")
                
            if "Hello Guardian Mode" in str(agent.context.get_history_text(limit=2)):
                 print("🌟 SUCCESS: Expected output found in context.")
            else:
                 print("⚠️ WARNING: Expected output not clearly found in immediate context.")
        else:
             print(f"❌ FAILURE: Step returned status {result['status']}")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
