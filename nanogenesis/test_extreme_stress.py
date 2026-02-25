import asyncio
import os
import logging
from genesis.core.factory import GenesisFactory

def cleanup():
    db_path = os.path.expanduser("~/.nanogenesis/sessions.sqlite")
    if os.path.exists(db_path):
        os.remove(db_path)
    print("🗑️ [CLEANUP]: Erased memory.")

async def main():
    cleanup()
    print("🚀 [STRESS_TEST]: Initiating Multi-Agent Concurrent Load Test\n")
    
    agent = GenesisFactory.create_common(
        user_id="PrimeNode", 
        enable_optimization=True,
    )
    
    logging.getLogger('genesis').setLevel(logging.INFO)
    
    print("\n📩 [PHASE 1]: Asking Prime Node to delegate 3 concurrent mathematical tasks...")
    prompt1 = """
    我现在需要进行一次压力测试。请你立刻、连续使用 3 次 `spawn_sub_agent` 工具，派发 3 个后台子代理去同时完成以下计算：
    1. 代理名 'Miner_A': 计算 1 到 30 的质数和。
    2. 代理名 'Miner_B': 计算 31 到 60 的质数和。
    3. 代理名 'Miner_C': 计算 61 到 90 的质数和。
    
    请确保将这 3 个任务都抛入后台，并在回复中把它们的 3 个 Task ID 一次性告诉我。
    """
    
    result1 = await agent.process(prompt1)
    msgs = result1.get('messages', [])
    reply1 = msgs[-1].content if msgs else str(result1)
    print(f"\n💡 [PRIME NODE REPLY 1]:\n{reply1}\n")
    
    import re
    task_ids = re.findall(r"task_[a-zA-Z0-9]+", reply1)
    
    if len(task_ids) == 0:
        print("❌ [FAILURE]: Prime Node failed to return any Task IDs.")
        return
        
    print(f"✅ Extracted Task IDs: {task_ids}")
    
    wait_time = 25
    print(f"\n⏳ [PHASE 2]: Waiting {wait_time}s for the server farm to process concurrent tasks...")
    for i in range(wait_time):
        print(f"Waiting... {wait_time-i}s", end="\r")
        await asyncio.sleep(1)
        
    print("\n\n📩 [PHASE 3]: Asking Prime Node to check all task statuses...")
    prompt2 = f"请使用 `check_sub_agent` 依次帮我查询这几个任务的进度：{', '.join(task_ids)}。把它们的结果汇编给我看。"
    
    result2 = await agent.process(prompt2)
    msgs2 = result2.get('messages', [])
    reply2 = msgs2[-1].content if msgs2 else str(result2)
    print(f"\n💡 [PRIME NODE REPLY 2]:\n{reply2}\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STRESS TEST] Interrupted by user/system (Code 130). Existing tasks might still be running...")
