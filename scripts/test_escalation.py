import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.loop import AgentLoop
from genesis.core.registry import ToolRegistry
from genesis.tools.escalate_tool import EscalateTool

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
        from genesis.core.base import LLMResponse
        # Simulate the LLM deciding to call escalate_tool
        return LLMResponse(
            content=None,
            tool_calls=[{
                "id": "call_test_123",
                "type": "function",
                "function": {
                    "name": "escalate_to_strategist",
                    "arguments": '{"reason": "Testing Escalation", "introspection": "I am stuck in a test loop."}'
                }
            }]
        )

async def test_escalation():
    print("🚀 Starting Cognitive Escalation Test...")
    
    # Setup
    registry = ToolRegistry()
    # escalate_tool is registered internally by AgentLoop, but we can register others if needed
    
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
    
    if "[STRATEGIC_INTERRUPT_SIGNAL]" in response and metrics.success is False:
        print("\n✅ TEST PASSED: Strategic Interrupt Signal received and success is False.")
    else:
        print("\n❌ TEST FAILED: Signal not received or success is True.")

if __name__ == "__main__":
    asyncio.run(test_escalation())
