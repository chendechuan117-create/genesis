import sys
import asyncio
import logging
import json
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.agent import NanoGenesis

# Setup logging
logging.basicConfig(level=logging.WARN)
logger = logging.getLogger("Benchmark")
logger.setLevel(logging.INFO)

async def main():
    print("🚀 Running Hardcore System Benchmark...")
    agent = NanoGenesis(enable_optimization=False)
    
    # 1. Tool Execution Test (Shell)
    print("\n[Test 1] Tool Execution (Shell)")
    try:
        # We ask it to run a specific command
        prompt = "Execute the command 'echo GAMMA-RAY' and tell me the output."
        print(f"👉 Prompt: {prompt}")
        res = await agent.process(prompt)
        
        if "GAMMA-RAY" in res['response'] or (res.get('metrics') and any('echo' in str(t) for t in res['metrics'].tools_used)):
            print("✅ PASS: Tool executed successfully.")
        else:
            print("❌ FAIL: Tool execution failed or output not captured.")
            print(f"   Response: {res['response']}")
    except Exception as e:
        print(f"❌ CRITICAL FAIL: {e}")

    # 2. Filesystem Access Test
    print("\n[Test 2] Filesystem Capability")
    test_file = "benchmark_artifact.txt"
    try:
        prompt = f"Create a file named '{test_file}' with the content 'VOID-walkers'."
        print(f"👉 Prompt: {prompt}")
        res = await agent.process(prompt)
        
        # Verify file existence directly
        fpath = Path(test_file)
        if fpath.exists():
            content = fpath.read_text()
            if "VOID-walkers" in content:
                print("✅ PASS: File created and content verified.")
                fpath.unlink() # Cleanup
            else:
                print(f"❌ FAIL: File created but content wrong: {content}")
        else:
            # Check if it wrote it somewhere else?
            print(f"❌ FAIL: File '{test_file}' not found.")
            print(f"   Response: {res['response']}")
    except Exception as e:
        print(f"❌ CRITICAL FAIL: {e}")

    # 3. Reasoning & Strategy
    print("\n[Test 3] Strategy & Chain of Thought")
    try:
        # A request that requires Strategy Phase to break it down (or at least think)
        prompt = "If I have 3 apples and eat one, how many are left? Answer with just the number."
        print(f"👉 Prompt: {prompt}")
        res = await agent.process(prompt)
        
        if "2" in res['response']:
             print("✅ PASS: Basic reasoning intact.")
        else:
             print(f"❌ FAIL: Reasoning result incorrect. Got: {res['response']}")
             
        # Check if Reasoning Log is populated
        logs = agent.get_reasoning_log()
        if len(logs) > 0:
            print(f"✅ PASS: Reasoning log captures {len(logs)} steps.")
        else:
            print("⚠️ WARN: Reasoning log is empty.")

    except Exception as e:
        print(f"❌ CRITICAL FAIL: {e}")

    print("\n✨ Benchmark Complete.")

if __name__ == "__main__":
    asyncio.run(main())
