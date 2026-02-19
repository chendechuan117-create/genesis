import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.loop import AgentLoop
from genesis.core.registry import ToolRegistry
from genesis.core.base import LLMResponse, ToolCall, MessageRole

# Mock Context
class MockContext:
    def __init__(self):
        self.message_history = []
    
    async def build_messages(self, user_input, **kwargs):
        from genesis.core.base import Message, MessageRole
        return [Message(role=MessageRole.USER, content=user_input)]
        
    def add_to_history(self, msg):
        pass
    
    def add_tool_result(self, messages, tool_id, tool_name, result):
        # Mock implementation
        from genesis.core.base import Message, MessageRole
        messages.append(Message(role=MessageRole.TOOL, content=result, tool_call_id=tool_id))
        return messages

# Mock Provider with Sequence
class MockProvider:
    def __init__(self):
        self.call_count = 0
        
    async def chat(self, messages, tools=None, **kwargs):
        self.call_count += 1
        print(f"\n🤖 Mock LLM Call #{self.call_count}")
        
        # Check if the previous message was the Enforcement Warning
        last_msg = messages[-1]
        # AgentLoop converts messages to dicts before passing to provider
        content = last_msg.get('content') if isinstance(last_msg, dict) else last_msg.content
        if content and "[ACTION ENFORCEMENT]" in content:
            print("✅ Received Enforcement Warning!")
            # Turn 2: Compliant Tool Call
            return LLMResponse(
                content="<reflection>Goal: Fix mistake. Progress: Calling tool. Looping? No.</reflection>",
                tool_calls=[ToolCall(id="call_1", name="chain_next", arguments={"instruction": "Run test"})],
                finish_reason="tool_calls"
            )
            
        if self.call_count > 2:
             # Stop the madness
             return LLMResponse(
                content="<reflection>Goal: Done. Progress: Complete. Looping? No.</reflection>\nI am done.",
                tool_calls=[],
                finish_reason="stop"
            )
        
        # Turn 1: All Talk, No Action
        return LLMResponse(
            content="<reflection>Goal: Test enforcement. Progress: I will run the test. Looping? No.</reflection>\nI will run the test script now.",
            tool_calls=[],
            finish_reason="stop"
        )

async def test_enforcement():
    print("🚀 Starting Action Enforcement Test...")
    
    # Setup
    registry = ToolRegistry()
    # Register a dummy tool so logic doesn't fail on execution
    from genesis.tools.chain_next_tool import ChainNextTool
    registry.register(ChainNextTool())
    
    context = MockContext()
    provider = MockProvider()
    
    loop = AgentLoop(
        tools=registry,
        context=context,
        provider=provider,
        max_iterations=5
    )
    
    # Run Loop
    print("🔄 Running Agent Loop...")
    response, metrics = await loop.run("Test Input")
    
    # Verify Result
    print(f"\n📝 Loop Result: {response}")
    print(f"📊 Iterations: {metrics.iterations}")
    
    if metrics.iterations >= 2 and provider.call_count >= 2:
        print("\n✅ TEST PASSED: Loop forced a second iteration upon inaction.")
    else:
        print("\n❌ TEST FAILED: Loop exited prematurely or didn't trigger enforcement.")
        print(f"Iterations: {metrics.iterations}, LLM Calls: {provider.call_count}")

if __name__ == "__main__":
    asyncio.run(test_enforcement())
