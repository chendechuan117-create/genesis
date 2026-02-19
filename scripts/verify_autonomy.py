
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
    print("🚀 Initializing Agent...")
    # Enable optimization to ensure behavior optimizer is active (though we rely on Protocol here)
    agent = GenesisFactory.create_common(enable_optimization=True)
    
    # 1. Ask a question requiring a NEW tool (Local Browser History)
    # The agent DOES NOT have a 'read_browser_history' tool. 
    # It MUST use 'skill_creator' to build one.
    query = "帮我看看我最近在 Chrome 浏览器里访问了哪些网站？直接读取本地历史记录文件。"
    
    print(f"\n🗣️ User: {query}")
    print("🤖 Agent is thinking... (Expecting 'skill_creator' call)")
    
    # Define callback to see what's happening inside the loop
    def debug_callback(step_type, data):
        print(f"\n[DEBUG] {step_type}: {data}")

    result = await agent.process(query, step_callback=debug_callback)
    
    print(f"\n📝 Final Response:\n{result['response']}\n-------------------")
    
    # Analyze Metrics to find skill_creator usage
    metrics = result.get('metrics')
    if metrics and metrics.tools_used:
        print(f"\n🛠️ Tools Used: {metrics.tools_used}")
        if 'skill_creator' in metrics.tools_used:
            print("✅ TEST PASS: Agent successfully called 'skill_creator'.")
            
            # Optional: Check if the skill actually works/was created
            # We can't easily check the *content* of the tool call here without deeper inspection,
            # but usage is the primary success criteria for autonomy.
        else:
            print("❌ TEST FAIL: Agent did NOT use 'skill_creator'.")
            print(f"It used: {metrics.tools_used}")
    else:
        print("❌ TEST FAIL: No tools were used.")

if __name__ == "__main__":
    asyncio.run(main())
