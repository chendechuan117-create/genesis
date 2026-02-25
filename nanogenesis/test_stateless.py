import asyncio
import os
import sys

# Ensure genesis can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from genesis.core.factory import GenesisFactory
from genesis.core.config import config

async def test_stateless_executor():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Missing DEEPSEEK_API_KEY")
        return
        
    config.set("provider.api_key", api_key)
    config.set("provider.model", "deepseek-chat")
    
    # Let factory build the complex dependencies
    agent = GenesisFactory.create_common(user_id="test_user")
    
    print("\n--- TEST: Intentional Action Gap / Visual Hallucination ---")
    print("Asking the agent to perform an impossible visual task.")
    
    user_input = "帮我看看屏幕上有几个图标，用visual tool"
    
    print(f"User: {user_input}")
    
    try:
        result = await agent.process(user_input)
        print("\n=== FINAL RESULT ===")
        print(result["response"])
        print("====================")
    except Exception as e:
        print(f"Error during execution: {e}")

if __name__ == "__main__":
    asyncio.run(test_stateless_executor())
