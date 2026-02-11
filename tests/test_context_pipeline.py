"""
Unit Test for ContextPipeline
Verifies that the Nervous System correctly injects Time, Environment, and Memory.
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_pipeline import ContextPipeline, ContextContext

class TestContextPipeline(unittest.TestCase):
    def setUp(self):
        self.base_prompt = "You are NanoGenesis."
        self.pipeline = ContextPipeline(self.base_prompt)

    def test_identity_plugin(self):
        ctx = self.pipeline.build_system_context("Hello")
        self.assertIn("You are NanoGenesis.", ctx)

    def test_time_awareness(self):
        ctx = self.pipeline.build_system_context("What time is it?")
        # Check for format [System Time: YYYY-MM-DD
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.assertIn("[System Time:", ctx)
        self.assertIn(current_date, ctx)
        print(f"✓ Time Injection Verified: {current_date}")

    def test_environment_awareness(self):
        ctx = self.pipeline.build_system_context("Where am I?")
        self.assertIn("[Environment]", ctx)
        self.assertIn("OS:", ctx)
        self.assertIn("CWD:", ctx)
        print("✓ Environment Injection Verified")

    def test_memory_injection(self):
        raw_memory = [{"content": "User name is Chen."}]
        ctx = self.pipeline.build_system_context("Who am I?", raw_memory=raw_memory)
        self.assertIn("[Relevant Memories]", ctx)
        self.assertIn("User name is Chen.", ctx)
        print("✓ Memory Injection Verified")

if __name__ == '__main__':
    unittest.main()
