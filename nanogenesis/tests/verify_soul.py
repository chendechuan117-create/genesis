
import sys
import os
import json
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.core.compression import CompressionEngine
from nanogenesis.core.context import SimpleContextBuilder
from nanogenesis.optimization.prompt_optimizer import PromptOptimizer
from nanogenesis.optimization.behavior_optimizer import BehaviorOptimizer
from nanogenesis.agent import NanoGenesis
from nanogenesis.core.base import Message, MessageRole, PerformanceMetrics

class TestSoulInjection(unittest.TestCase):
    def setUp(self):
        # Mock Provider
        self.mock_provider = MagicMock()
        self.mock_provider.chat = AsyncMock()
        self.mock_provider.available = True

    def test_compression_engine(self):
        print("\n=== Testing Compression Engine (Cache-Friendly) ===")
        engine = CompressionEngine(self.mock_provider, block_size=2) # Small block size for test
        
        # Simulate 2 turns (4 messages) -> Should trigger compression
        engine.add_interaction("Hi", "Hello")
        engine.add_interaction("How are you?", "I am fine")
        
        # Check pending
        self.assertEqual(len(engine.pending_turns), 4)
        
        # Trigger compression
        # Mock LLM response for compression
        self.mock_provider.chat.return_value.content = json.dumps({
            "summary": "User greeted and asked status.",
            "diff": "",
            "anchors": {"status": "fine"}
        })
        
        asyncio.run(engine._compress_pending_to_block())
        
        # Verify block created
        self.assertEqual(len(engine.blocks), 1)
        self.assertEqual(engine.blocks[0].summary, "User greeted and asked status.")
        self.assertEqual(len(engine.pending_turns), 0)
        print("✓ Compression Logic Verified")

    def test_context_builder_integration(self):
        print("\n=== Testing Context Builder Integration ===")
        builder = SimpleContextBuilder()
        builder.set_provider(self.mock_provider)
        builder.compression_engine.block_size = 2
        
        # Add messages
        builder.add_to_history(Message(MessageRole.USER, "1"))
        builder.add_to_history(Message(MessageRole.ASSISTANT, "2"))
        builder.add_to_history(Message(MessageRole.USER, "3"))
        builder.add_to_history(Message(MessageRole.ASSISTANT, "4"))
        
        # Verify trigger condition (SimpleContextBuilder currently doesn't auto-compress in add_to_history, 
        # it waits for explicit call or Agent loop. In my code I commented out auto-trigger to avoid async issues)
        
        # Explicitly compress
        # Mock LLM response
        self.mock_provider.chat.return_value.content = json.dumps({
            "summary": "Block 1 Summary",
            "diff": "",
            "anchors": {}
        })
        
        asyncio.run(builder.compress_history())
        
        # Verify messages built
        messages = asyncio.run(builder.build_messages("Current Query"))
        
        # Check for Block Summary in System message
        system_msg = messages[1] # messages[0] is Fixed Prefix, messages[1] should be Block Summary if present
        self.assertIn("【历史对话摘要】", system_msg.content)
        self.assertIn("Block 1 Summary", system_msg.content)
        print("✓ Context Builder Integration Verified")

    def test_prompt_optimizer(self):
        print("\n=== Testing Prompt Optimizer (Real LLM) ===")
        optimizer = PromptOptimizer(provider=self.mock_provider, optimize_interval=1)
        
        # Log simulated interaction
        metrics = PerformanceMetrics(total_tokens=1000, total_time=1.0, tools_used=[], iterations=1)
        optimizer.log_interaction(metrics, "input", "response", False) # Failure case
        
        # Mock LLM response for optimization
        self.mock_provider.chat.return_value.content = json.dumps({
            "analysis": "Too many tokens.",
            "optimized_prompt": "Identity\nNew Instructions"
        })
        
        # Run optimize
        result = asyncio.run(optimizer.optimize("Identity\nOld Instructions"))
        
        self.assertIsNotNone(result)
        self.assertEqual(result.new_prompt, "Identity\nNew Instructions")
        print("✓ Prompt Optimizer Logic Verified")

    def test_behavior_optimizer(self):
        print("\n=== Testing Behavior Optimizer (Real LLM) ===")
        optimizer = BehaviorOptimizer(provider=self.mock_provider)
        
        # Mock Extract Pattern
        self.mock_provider.chat.return_value.content = json.dumps({
            "problem_pattern": "docker error",
            "domain": "docker",
            "root_cause": "permission",
            "solution": "sudo"
        })
        
        asyncio.run(optimizer.learn_from_interaction({"success": True, "problem": "fix docker", "response": "done"}))
        
        self.assertIn("docker error", [s.pattern for s in optimizer.strategies.values()])
        print("✓ Behavior Optimizer Logic Verified")

if __name__ == '__main__':
    unittest.main()
