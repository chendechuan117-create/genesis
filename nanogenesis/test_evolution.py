import asyncio
import os
import shutil
import json
from genesis.core.factory import GenesisFactory

async def main():
    print("🔥 Multiplicative Evolution Test Initiated 🔥")
    print("--------------------------------------------------")
    
    # 1. Clear previous learned insights
    storage_path = "data/adaptive_learning.json"
    if os.path.exists(storage_path):
        os.remove(storage_path)

    # 2. Start Main Agent
    agent = GenesisFactory.create_common(user_id="test_evolution", max_iterations=4, enable_optimization=True)
    
    # Check baseline prompt
    print("\n[Baseline Prompt Check]:")
    print("Length of System Prompt:", len(agent.context.system_prompt))
    print("Has Instincts?", "Evolutionary Cognitive Insights" in agent.context.system_prompt)
    
    # 3. Fire a mission that requires a Sub-Agent
    mission = "我需要你调查 `genesis/tools/` 下面有多少个 .py 工具文件。请立即使用 `spawn_sub_agent` 派生一个子代去做这件事，子代数完后向你汇报，不要自己去 ls。"
    
    print("\n[Phase 1]: Dispatching Sub-Agent Probe...")
    res = await agent.process(user_input=mission)
    print("\n[Return]:", res.get('response')[:200], "...")
    
    # 4. Check if the AdaptiveLearner captured the insight
    print("\n[Phase 2]: Checking AdaptiveLearner Core...")
    if agent.adaptive_learner.pattern.cognitive_insights:
        print("✅ Extracted Cognitive Insights Detected:")
        for idx, ins in enumerate(agent.adaptive_learner.pattern.cognitive_insights):
            print(f"  {idx+1}. {ins}")
    else:
        print("❌ FAILED: No insights extracted.")
        return
        
    # 5. Simulate a Reboot to test genetic memory
    print("\n[Phase 3]: Simulating System Reboot...")
    agent_reborn = GenesisFactory.create_common(user_id="test_evolution", max_iterations=2, enable_optimization=True)
    
    print("\n[Evolved Prompt Check]:")
    print("Has Instincts?", "Evolutionary Cognitive Insights" in agent_reborn.context.system_prompt)
    if "Evolutionary Cognitive Insights" in agent_reborn.context.system_prompt:
        print("🧬 SUCCESS: Reborn Agent has inherited the abstract wisdom automatically!")

if __name__ == "__main__":
    asyncio.run(main())
