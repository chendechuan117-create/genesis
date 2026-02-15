
import sys
import asyncio
import logging
from pathlib import Path
import os

# Ensure the current directory is in python path
sys.path.insert(0, str(Path(__file__).parent))

from agent import NanoGenesis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ProtocolVerifier")

async def main():
    print("🚀 Verifying Pure Metacognition Protocol Integration")
    print("=" * 60)

    # Initialize Agent
    # Note: We rely on config for API key or mock provider if not set
    try:
        agent = NanoGenesis(
            model="deepseek-chat",
            max_iterations=3,
            enable_optimization=True 
        )
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        return

    # Verification 1: Check Protocol Loading
    print("\n[1] Checking Protocol Loading...")
    if agent.meta_protocol:
        if "Pure Metacognition" in agent.meta_protocol:
             print("✅ Pure Metacognition Protocol loaded successfully.")
        else:
             print("⚠️ Protocol loaded but does not contain 'Pure Metacognition' signature.")
             print(f"Preview: {agent.meta_protocol[:100]}...")
    else:
        print("❌ Protocol NOT loaded.")
        return

    # Verification 2: Run Agent Process
    print("\n[2] Running Test Query...")
    user_problem = "I want to delete all files in /tmp that are older than 7 days."
    
    print(f"📝 Input: {user_problem}")
    
    try:
        # We expect the agent to use the protocol to analyze this
        # Since we might not have a real API key, this might fallback to Mock or fail if network is down
        # But we want to see if the LOGIC tries to use the protocol.
        
        result = await agent.process(user_problem)
        
        print("\n✅ Agent Process Completed.")
        print(f"Response: {result['response'][:200]}...")
        
    except Exception as e:
        print(f"❌ Agent execution failed: {e}")
        # If it failed due to API credentials, that's fine for protocol verification 
        # as long as we saw the protocol being loaded.

if __name__ == "__main__":
    asyncio.run(main())
