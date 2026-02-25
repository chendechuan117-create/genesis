import asyncio
import os
import logging
from genesis.core.factory import GenesisFactory

# 调整日志级别以查看详细错误
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("genesis")
logger.setLevel(logging.DEBUG) 

async def run_full_evolution_test():
    print("🚀 [TEST_START]: Initiating Full Multiplicative Evolution Pipeline Test\n")
    
    # 1. 清理之前的学习数据和聊天历史，由于测试是全新的
    storage_path = "data/adaptive_learning.json"
    if os.path.exists(storage_path):
        os.remove(storage_path)
        
    sqlite_path = os.path.expanduser("~/.nanogenesis/sessions.sqlite")
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)
        print("🗑️ [CLEANUP]: Erased previous SQLite Session History.")

    # 2. 创建主脑
    print("🧠 [SYSTEM]: Assembling Prime Genesis Node...")
    agent = GenesisFactory.create_common(
        user_id="test_evolution_full",
        max_iterations=4,
        enable_optimization=True
    )
    
    print(f"✅ Prime Node Active Provider (Expensive): {agent.provider_router.active_provider_name}")
    
    # 3. 故意给主脑发派一个恶心、费令牌的任务，强制它动用 SpawnSubAgentTool
    # 比如：让它做大量的目录检索或者数学计算，并暗示为了节省主脑资源，必须派生探针。
    mission = "我需要你帮我计算 1 到 50 的所有质数，并将它们相加。为了保护你主脑宝贵的 Token，请**务必**且**立刻**使用 `spawn_sub_agent` 工具派生一个名为 'MathProbe_01' 的子代码去完成这个计算任务。子代算完后你把结果告诉我。"
    
    print("\n📩 [USER_INPUT]: Dispatching complex mission to Prime Node...")
    print(f"Mission: {mission}")
    
    print("\n⏳ [SYSTEM]: Waiting for Prime Node to spawn Sub-Agent and retrieve insights...\n")
    # 运行主循环!
    result = await agent.process(user_input=mission)
    
    print("\n-------------------------------------------------------------")
    print("💡 [FINAL_RESPONSE]: Main Agent Reply:")
    print(result.get('response', 'No response'))
    print("-------------------------------------------------------------\n")
    
    print("\n[MESSAGE TRACE]:")
    for msg in agent.context._message_history[-4:]:
        print(f"[{msg.role}] {msg.content}")
        if msg.tool_calls:
            print(f"   => Tool Calls: {msg.tool_calls}")

    # 4. 验证引擎底层是否成功提取了 Insight
    print("🔍 [VERIFICATION]: Inspecting AdaptiveLearner genetic memory...")
    insights = agent.adaptive_learner.pattern.cognitive_insights
    if insights:
        print("✅ SUCCESS: The following Evolutionary Cognitive Insights were permanently extracted:")
        for idx, ins in enumerate(insights):
            print(f"  {idx+1}. {ins}")
    else:
        print("❌ FAILED: Sub-Agent did not follow protocol, or Extractor failed to scrape the <OPERATIONAL_METRICS>.")
        return

    # 5. 验证是否自动重塑 Prompt
    print("\n🧬 [NEXT_BOOT_SIMULATION]: Checking if insights are woven into the prompt...")
    agent_reborn = GenesisFactory.create_common(user_id="test_evolution_full", max_iterations=2, enable_optimization=True)
    if insights[0] in agent_reborn.context.system_prompt:
         print("✅ GENETIC SUCCESS: The insights are now permanently part of the Prime Node's System Prompt!")
    else:
         print("❌ GENETIC FAILURE: Insights were saved but not injected into the prompt.")

if __name__ == "__main__":
    asyncio.run(run_full_evolution_test())
