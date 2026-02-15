"""
核心组件测试
"""

import pytest
from nanogenesis.core import (
    ToolRegistry,
    SimpleContextBuilder,
    MockLLMProvider,
    AgentLoop,
    Message,
    MessageRole,
    Tool
)


class DummyTool(Tool):
    """测试用的虚拟工具"""
    
    @property
    def name(self) -> str:
        return "dummy_tool"
    
    @property
    def description(self) -> str:
        return "A dummy tool for testing"
    
    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input text"}
            },
            "required": ["input"]
        }
    
    async def execute(self, input: str) -> str:
        return f"Processed: {input}"


class TestToolRegistry:
    """测试工具注册表"""
    
    def test_register_tool(self):
        registry = ToolRegistry()
        tool = DummyTool()
        
        registry.register(tool)
        
        assert "dummy_tool" in registry
        assert len(registry) == 1
        assert registry.get("dummy_tool") == tool
    
    def test_unregister_tool(self):
        registry = ToolRegistry()
        tool = DummyTool()
        
        registry.register(tool)
        registry.unregister("dummy_tool")
        
        assert "dummy_tool" not in registry
        assert len(registry) == 0
    
    def test_get_definitions(self):
        registry = ToolRegistry()
        tool = DummyTool()
        
        registry.register(tool)
        definitions = registry.get_definitions()
        
        assert len(definitions) == 1
        assert definitions[0]["type"] == "function"
        assert definitions[0]["function"]["name"] == "dummy_tool"
    
    @pytest.mark.asyncio
    async def test_execute_tool(self):
        registry = ToolRegistry()
        tool = DummyTool()
        
        registry.register(tool)
        result = await registry.execute("dummy_tool", {"input": "test"})
        
        assert result == "Processed: test"
    
    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        
        assert "Error" in result


class TestContextBuilder:
    """测试上下文构建器"""
    
    @pytest.mark.asyncio
    async def test_build_messages(self):
        builder = SimpleContextBuilder()
        messages = await builder.build_messages("Hello")
        
        assert len(messages) == 2
        assert messages[0].role == MessageRole.SYSTEM
        assert messages[1].role == MessageRole.USER
        assert messages[1].content == "Hello"
    
    @pytest.mark.asyncio
    async def test_build_messages_with_context(self):
        builder = SimpleContextBuilder()
        messages = await builder.build_messages(
            "Hello",
            user_context="User is a developer"
        )
        
        assert len(messages) == 2
        assert "User is a developer" in messages[0].content
    
    def test_add_tool_result(self):
        builder = SimpleContextBuilder()
        messages = [
            Message(role=MessageRole.SYSTEM, content="System"),
            Message(role=MessageRole.USER, content="User")
        ]
        
        updated = builder.add_tool_result(
            messages,
            tool_call_id="123",
            tool_name="test_tool",
            result="Tool result"
        )
        
        assert len(updated) == 3
        assert updated[2].role == MessageRole.TOOL
        assert updated[2].content == "Tool result"
        assert updated[2].name == "test_tool"
    
    def test_update_system_prompt(self):
        builder = SimpleContextBuilder()
        original = builder.system_prompt
        
        builder.update_system_prompt("New prompt")
        
        assert builder.system_prompt != original
        assert builder.system_prompt == "New prompt"


class TestAgentLoop:
    """测试 Agent 循环"""
    
    @pytest.mark.asyncio
    async def test_simple_run(self):
        tools = ToolRegistry()
        context = SimpleContextBuilder()
        provider = MockLLMProvider()
        loop = AgentLoop(tools, context, provider, max_iterations=5)
        
        response, metrics = await loop.run("Hello")
        
        assert response.startswith("Mock response")
        assert metrics.success
        assert metrics.iterations == 1
        assert metrics.tokens > 0
    
    @pytest.mark.asyncio
    async def test_run_with_tool(self):
        # 这个测试需要 mock 工具调用，暂时跳过
        pass


class TestMockProvider:
    """测试 Mock LLM 提供商"""
    
    @pytest.mark.asyncio
    async def test_chat(self):
        provider = MockLLMProvider()
        
        response = await provider.chat(
            messages=[{"role": "user", "content": "Hello"}]
        )
        
        assert response.content.startswith("Mock response")
        assert not response.has_tool_calls
        assert response.usage["total_tokens"] == 150
    
    def test_get_default_model(self):
        provider = MockLLMProvider()
        assert provider.get_default_model() == "mock-model"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
