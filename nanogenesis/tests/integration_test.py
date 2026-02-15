
import sys
import os
import asyncio
import logging
import traceback
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.agent import NanoGenesis

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("simulation")

API_KEY = os.getenv("DEEPSEEK_API_KEY", "your-api-key")

async def run_simulation():
    print("\n" + "="*60)
    print("🚀 NanoGenesis Full System Simulation")
    print("="*60)
    
    # 1. Initialize
    print("\n[Init] Initializing Agent...")
    try:
        agent = NanoGenesis(
            api_key=API_KEY,
            model="deepseek-chat", # Or mock if key fails
            enable_optimization=True
        )
        if agent.scheduler:
            await agent.scheduler.start()
        print("✅ Agent Initialized (Heartbeat Active)")
    except Exception as e:
        print(f"❌ Initialization Failed: {e}")
        if 'agent' in locals():
            print(f"DEBUG: Agent attributes: {dir(agent)}")
        traceback.print_exc()
        return

    # 2. Scenario 1: Simple Chat (Local Router Check)
    print("\n[Scenario 1] Simple Chat Test ('Hi')")
    try:
        result = await agent.process("Hi")
        response = result.get('response', '')
        metrics = result.get('metrics')
        print(f"🤖 Response: {response}")
        if metrics:
            print(f"📊 Metrics: {metrics}")
            # Verify if Polyhedron was used (In Simple mode, Router should optimize)
            # We can't easily check internal flag 'use_polyhedron' from result dict unless we exposed it
            # But we can check logs or inference speed.
    except Exception as e:
        print(f"❌ Chat Failed: {e}")

    # 3. Scenario 2: Memory Save (Vector DB Check)
    print("\n[Scenario 2] Memory Save Test")
    secret = "Project NanoGenesis is located in /home/chendechusn"
    query = f"Please remember this important fact: {secret}"
    try:
        result = await agent.process(query)
        print(f"🤖 Response: {result.get('response')}")
        # Verify directly in memory
        # Wait a bit for async embedding
        await asyncio.sleep(1)
        if agent.memory:
            found = await agent.memory.search("NanoGenesis location", limit=1)
            if found:
                print(f"✅ Memory Verified: Found '{found[0]['content'][:50]}...' score={found[0].get('score', 0):.2f}")
            else:
                print("⚠️ Memory Search returned nothing (Embeddings might be all zeros if Ollama model doesn't support embed)")
    except Exception as e:
        print(f"❌ Memory Test Failed: {e}")

    # 4. Scenario 3: Memory Retrieval (Context Filter Check)
    print("\n[Scenario 3] Retrieval Test")
    try:
        result = await agent.process("Where is NanoGenesis located?")
        print(f"🤖 Response: {result.get('response')}")
    except Exception as e:
        print(f"❌ Retrieval Failed: {e}")

    # 5. Scenario 4: Agency (Scheduler Check)
    print("\n[Scenario 4] Agency/Heartbeat Test")
    try:
        # Add a job via Agent process (Simulating user command)
        # Note: User needs to invoke SchedulerTool.
        # "Add a background task to check 'date' every 2 seconds"
        # We assume intent analyzer maps this to SchedulerTool or generic complex task
        
        # Direct Tool Call simulation for reliability in test
        print(">> Adding Job via SchedulerTool...")
        scheduler_tool = agent.tools.get("scheduler_tool")
        if scheduler_tool:
            res = await scheduler_tool.execute("add", command="date", interval=2)
            print(f"Tool Output: {res}")
            
            print(">> Waiting for 5 seconds (watching logs for execution)...")
            await asyncio.sleep(5)
            
            # Check last run
            if agent.scheduler.jobs:
                job = list(agent.scheduler.jobs.values())[0]
                print(f"✅ Job Status: ID={job.id}, LastRun={job.last_run}")
                if job.last_run > 0:
                    print("✅ Heartbeat is beating.")
                else:
                    print("❌ Job never ran.")
            else:
                print("❌ No jobs found.")
        else:
            print("❌ SchedulerTool not found.")
            
    except Exception as e:
        print(f"❌ Agency Test Failed: {e}")

    # Cleanup
    if agent.scheduler:
        await agent.scheduler.stop()
    print("\n✅ Simulation Complete.")

if __name__ == "__main__":
    asyncio.run(run_simulation())
