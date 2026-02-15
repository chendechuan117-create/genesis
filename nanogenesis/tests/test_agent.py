"""
NanoGenesis 主类测试
"""

import pytest
from nanogenesis import NanoGenesis
from nanogenesis.core import MockLLMProvider


class TestNanoGenesis:
    """测试 NanoGenesis 主类"""
    
    def test_init(self):
        """测试初始化"""
        # 使用 Mock Provider 避免需要真实 API Key
        agent = NanoGenesis()
        agent.provider = MockLLMProvider()
        
        assert agent.tools is not None
        assert agent.context is not None
        assert agent.loop is not None
        assert len(agent.metrics_history) == 0
    
    @pytest.mark.asyncio
    async def test_process(self):
        """测试处理用户输入"""
        agent = NanoGenesis()
        agent.provider = MockLLMProvider()
        
        result = await agent.process("Hello, NanoGenesis!")
        
        assert result['success']
        assert 'response' in result
        assert 'metrics' in result
        assert len(agent.metrics_history) == 1
    
    @pytest.mark.asyncio
    async def test_multiple_interactions(self):
        """测试多次交互"""
        agent = NanoGenesis()
        agent.provider = MockLLMProvider()
        
        for i in range(5):
            result = await agent.process(f"Question {i}")
            assert result['success']
        
        assert len(agent.metrics_history) == 5
    
    def test_get_stats(self):
        """测试统计信息"""
        agent = NanoGenesis()
        
        # 空统计
        stats = agent.get_stats()
        assert stats['total_interactions'] == 0
        assert stats['avg_tokens'] == 0
    
    @pytest.mark.asyncio
    async def test_get_stats_with_data(self):
        """测试有数据的统计"""
        agent = NanoGenesis()
        agent.provider = MockLLMProvider()
        
        # 执行几次交互
        for _ in range(3):
            await agent.process("Test")
        
        stats = agent.get_stats()
        assert stats['total_interactions'] == 3
        assert stats['avg_tokens'] > 0
        assert stats['success_rate'] == 1.0
    
    def test_update_system_prompt(self):
        """测试更新系统提示词"""
        agent = NanoGenesis()
        original = agent.context.system_prompt
        
        agent.update_system_prompt("New system prompt")
        
        assert agent.context.system_prompt != original
        assert agent.context.system_prompt == "New system prompt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
