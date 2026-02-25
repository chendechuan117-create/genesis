import asyncio
import os
import json
import sqlite3
import shutil
import time

from genesis.core.factory import GenesisFactory

def cleanup():
    # Remove sessions db
    db_path = os.path.expanduser("~/.nanogenesis/sessions.sqlite")
    if os.path.exists(db_path):
        os.remove(db_path)
    # Remove adaptive learning DB   
    al_path = os.path.expanduser("~/.nanogenesis/adaptive_learning.json")
    if os.path.exists(al_path):
        os.remove(al_path)
    print("🗑️ [CLEANUP]: Erazed memory.")

async def main():
    cleanup()
    print("🚀 [TEST_START]: Initiating Async Delegation & Handshake Test\n")
    
    agent = GenesisFactory.create_common(
        user_id="PrimeNode", 
        enable_optimization=True,
    )
    
    # Enable debug logging for deeper insight
    import logging
    logging.getLogger('genesis').setLevel(logging.INFO)
    
    print("\n📩 [PHASE 1]: Asking Prime Node to delegate a long running task...")
    prompt1 = "我需要你启动一个名为 'DataMiner_01' 的后台子代理去帮我计算 1 到 50 的质数总和。请务必使用 `spawn_sub_agent`。启动后立刻告诉我它的 Task ID，不要卡在这里等它算完。"
    
    result1 = await agent.process(prompt1)
    reply1 = result1['messages'][-1].content
    print(f"\n💡 [PRIME NODE REPLY 1]:\n{reply1}\n")
    
    # Extract Task ID from reply
    import re
    match = re.search(r"task_[a-zA-Z0-9]+", reply1)
    if not match:
        print("❌ [FAILURE]: Prime Node did not return a valid Task ID.")
        return
        
    task_id = match.group(0)
    print(f"✅ Extracted Task ID: {task_id}")
    
    print("\n⏳ [PHASE 2]: Waiting for sub-agent to finish in the background (15 seconds)...")
    for i in range(15):
        print(f"Waiting... {15-i}s", end="\r")
        await asyncio.sleep(1)
        
    print("\n\n📩 [PHASE 3]: Asking Prime Node to check the task status...")
    prompt2 = f"刚才派出去的子代理，它的Task ID是 {task_id}，请帮我检查它的状况。它算出质数之和了吗？另外如果它有 Cognitive Insight，你需要展示给我看并询问我是否接收。"
    
    result2 = await agent.process(prompt2)
    reply2 = result2['messages'][-1].content
    print(f"\n💡 [PRIME NODE REPLY 2 (Handshake expected)]:\n{reply2}\n")
    
    if "【系统优化握手请求】" in reply2:
        print("✅ [HANDSHAKE INITIATED]: Prime Node correctly intercepted the insight and asked for permission!")
    else:
        print("❌ [FAILURE]: Prime Node failed to initiate the Handshake Protocol.")
        return
        
    print("\n📩 [PHASE 4]: Agreeing to the handshake...")
    prompt3 = "是的，我同意将这条规律刻入你的潜意识基因库。"
    
    result3 = await agent.process(prompt3)
    reply3 = result3['messages'][-1].content
    print(f"\n💡 [PRIME NODE REPLY 3]:\n{reply3}\n")
    
    # Verify Adaptive Learning
    al_path = os.path.expanduser("~/.nanogenesis/adaptive_learning.json")
    if os.path.exists(al_path):
        with open(al_path, 'r') as f:
            data = json.load(f)
            insights = data.get("cognitive_insights", [])
            print(f"🧠 [VERIFICATION]: Found {len(insights)} insights in genome.")
            if len(insights) > 0:
                print(f"✅ [SUCCESS]: Insight properly saved: {insights[0]}")
            else:
                print("❌ [FAILURE]: No insights saved.")
                
if __name__ == "__main__":
    asyncio.run(main())
