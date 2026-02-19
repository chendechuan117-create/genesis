import sys
import asyncio
import logging
import json
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.agent import NanoGenesis
from genesis.core.base import MessageRole

# Setup logging
logging.basicConfig(level=logging.WARN)
logger = logging.getLogger("DeepVerify")
logger.setLevel(logging.INFO)

async def main():
    print("🚀 Running Deep Functional Verification...")
    
    agent = NanoGenesis(enable_optimization=False) # Disable opt to reduce noise
    print(f"✨ Session ID: {agent.session_manager.session_id}")

    # --- Test 1: Memory Persistence & Context Injection ---
    print("\n🧪 Test 1: Memory Persistence & Context Injection")
    try:
        # 1. Inject a fact
        fact = f"The secret code is OMEGA-{agent.session_manager.session_id[:4]}"
        print(f"   👉 User says: '{fact}'")
        res1 = await agent.process(fact)
        
        # 2. Check Session Persistence (Immediate Short-term Memory)
        history = await agent.session_manager.get_full_history()
        found_in_session = any(m['content'] == fact for m in history)
        
        if found_in_session:
            print("   ✅ Session: Fact persisted in sessions.sqlite.")
        else:
            print("   ❌ Session: Fact NOT found in sessions.sqlite.")
            print(f"      Full History: {history}")
            return

        # 3. Check Long-term Memory (Brain) - might be skipped if not deemed worthy
        conn = agent.memory._get_conn()
        cursor = conn.execute("SELECT body FROM content WHERE body LIKE ?", (f"%{fact}%",))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            print("   ✅ Brain: Fact consolidated to long-term memory.")
        else:
            print("   ⚠️ Brain: Fact not yet consolidated (Expected if not deemed critical).")
            # Do not return/fail here, strictly speaking. Context injection relies on Session.
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- Test 2: Retrieval & Reasoning ---
    print("\n🧪 Test 2: Retrieval & Reasoning")
    try:
        query = "What is the secret code?"
        print(f"   👉 User asks: '{query}'")
        
        # We expect the agent to recall OMEGA-xxxx
        res2 = await agent.process(query)
        response = res2['response']
        print(f"   🤖 Agent replies: {response[:100]}...")
        
        if "OMEGA" in response:
            print("   ✅ Recall: Agent correctly retrieved the secret code.")
        else:
            print("   ❌ Recall: Agent failed to retrieve the code.")
            print(f"      Full Response: {response}")
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return

    # --- Test 3: Tool Execution (Self-Correction) ---
    print("\n🧪 Test 3: System Resilience")
    try:
        # We trigger a known "safe" error flow or just check if components exist
        if hasattr(agent, '_error_response'):
             print("   ✅ Safety: _error_response method exists.")
        else:
             print("   ❌ Safety: _error_response method MISSING.")
             
        if hasattr(agent, '_check_and_optimize'):
             print("   ✅ Safety: _check_and_optimize method exists.")
        else:
             print("   ❌ Safety: _check_and_optimize method MISSING.")

    except Exception as e:
        print(f"   ❌ Exception: {e}")

    print("\n✨ Deep Verification Complete.")

if __name__ == "__main__":
    asyncio.run(main())
