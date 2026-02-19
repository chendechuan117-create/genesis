
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "nanogenesis")))

from genesis.core.entropy import EntropyMonitor
from genesis.core.cognition import CognitiveProcessor

# Mock Chat function
async def mock_chat(messages, **kwargs):
    class Response:
        content = "Understood. I see the Physiological Signal."
    return Response()

async def test_soft_interrupt():
    print("🧪 Testing Dynamic Metacognition (Soft Interrupt)...")
    
    # 1. Simulate High Repetition
    monitor = EntropyMonitor(window_size=3)
    monitor.capture("cmd_output_1", "/tmp", "mission_1")
    monitor.capture("cmd_output_1", "/tmp", "mission_1")
    monitor.capture("cmd_output_1", "/tmp", "mission_1")
    
    analysis = monitor.analyze_entropy()
    print(f"📊 Entropy Analysis: {analysis}")
    
    if analysis['status'] != 'stagnant':
        print("❌ Failed: Monitor should be stagnant.")
        return

    # 2. Test Cognition Injection
    cognition = CognitiveProcessor(
        chat_func=mock_chat,
        memory=None,
        meta_protocol="System: {{context}}\nUser: {{problem}}"
    )
    
    print("🧠 Invoking Strategy Phase...")
    # Hook into the chat_func to inspect the prompt? 
    # Actually, we can just verify the output implies it, 
    # OR we can inspect the private method logic if we mock closer.
    # For now, let's subclass to capture the prompt.
    
    captured_messages = []
    async def capturing_chat(messages, **kwargs):
        captured_messages.extend(messages)
        class Response:
            content = "OK"
        return Response()
    
    cognition.chat = capturing_chat
    
    await cognition.strategy_phase(
        user_input="Do something",
        oracle_output={},
        entropy_analysis=analysis,
        active_jobs=[]
    )
    
    # 3. Verify Signal Injection
    full_prompt = captured_messages[0]['content']
    if "[PHYSIOLOGICAL SIGNAL - CRITICAL]" in full_prompt:
        print("✅ Success: Physiological Signal Injected!")
        print(f"📝 Snippet: {full_prompt.split('[PHYSIOLOGICAL SIGNAL - CRITICAL]')[1].splitlines()[1]}")
    else:
        print("❌ Failed: Signal NOT found in prompt.")
        print(f"📄 Full Prompt:\n{full_prompt}")

if __name__ == "__main__":
    asyncio.run(test_soft_interrupt())
