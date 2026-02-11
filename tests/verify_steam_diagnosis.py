
import asyncio
import logging
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.agent import NanoGenesis

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Enable debug for provider to see curl usage
logging.getLogger("nanogenesis.core.provider").setLevel(logging.INFO)

async def main():
    print("🚀 Starting Steam Diagnosis Verification...")
    
    # Initialize Agent
    agent = NanoGenesis(enable_optimization=True)
    
    # Mock User Input
    user_input = "我的steam打不开了"
    print(f"\n👤 User: {user_input}")
    
    # Run Process
    import time
    start_time = time.time()
    
    result = await agent.process(user_input)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Output Result
    print("\n" + "="*40)
    print(f"⏱️  Total Duration: {duration:.2f}s")
    
    if result['success']:
        print("✅ Response:")
        print(result['response'])
        
        metrics = result['metrics']
        print(f"\n📊 Tools Used: {metrics.tools_used}")
        print(f"📊 Kernel Time: {metrics.total_time:.2f}s")
        
        # Check for expected behavior
        response_text = result['response']
        tools = metrics.tools_used
        
        # 1. Check Identity (Did it act?)
        if 'shell' in tools:
            print("✓ PASS: Agent used ShellTool (Action First).")
        else:
            print("❌ FAIL: Agent did NOT use ShellTool (Passive).")
            
        # 2. Check Logic (Did it find error?)
        if "error" in response_text.lower() or "log" in response_text.lower() or "display" in response_text.lower():
             print("✓ PASS: Agent attempted diagnosis.")
        else:
             print("⚠️ WARN: Response might be generic.")

    else:
        print(f"❌ Error: {result['response']}")

if __name__ == "__main__":
    asyncio.run(main())
