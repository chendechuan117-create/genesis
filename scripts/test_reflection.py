import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.loop import AgentLoop
from genesis.core.registry import ToolRegistry
from genesis.core.base import LLMResponse, MessageRole

# Mock Context and Provider
class MockContext:
    def __init__(self):
        self.message_history = []
    
    async def build_messages(self, user_input, **kwargs):
        from genesis.core.base import Message, MessageRole
        return [Message(role=MessageRole.USER, content=user_input)]
        
    def add_to_history(self, msg):
        pass

class MockProvider:
    async def chat(self, messages, tools=None, **kwargs):
        # Simulate the LLM providing a reflection that triggers termination
        print("\n🤖 Mock LLM: Generating Reflection...")
        return LLMResponse(
            content="<reflection>\n1. Goal: Test organic interrupt.\n2. Progress: Failing repeatedly.\n3. Loop Check: Yes, I am stuck, requesting strategic intervention.\n</reflection>\nI cannot proceed.",
            tool_calls=[]
        )

async def test_reflection():
    print("🚀 Starting Organic Reflexion Test...")
    
    # Setup
    registry = ToolRegistry()
    context = MockContext()
    provider = MockProvider()
    
    loop = AgentLoop(
        tools=registry,
        context=context,
        provider=provider
    )
    
    # Run Loop
    print("🔄 Running Agent Loop...")
    response, metrics = await loop.run("Test Input")
    
    # Verify Result
    print(f"\n📝 Loop Result: {response}")
    print(f"📊 Success Metric: {metrics.success}")
    
    expected_signal = "[STRATEGIC_INTERRUPT_SIGNAL]"
    if expected_signal in response and metrics.success is False:
        print("\n✅ TEST PASSED: Natural Language Interrupt triggered correctly.")
    else:
        print("\n❌ TEST FAILED: Interrupt signal not received.")
        print(f"Expected to contain: {expected_signal}")

if __name__ == "__main__":
    asyncio.run(test_reflection())
