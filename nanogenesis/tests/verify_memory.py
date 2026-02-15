
import sys
import os
import json
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.core.memory_vector import VectorMemory

class TestVectorMemory(unittest.TestCase):
    def setUp(self):
        self.mock_provider = MagicMock()
        self.mock_provider.embed = AsyncMock()
        self.db_path = "/tmp/test_vector_memory.json"
        
        # Clean up
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_add_and_search(self):
        print("\n=== Testing Vector Memory (Add & Search) ===")
        memory = VectorMemory(self.mock_provider, self.db_path)
        
        # Mock Embeddings: simple orthogonal vectors
        # "apple" -> [1, 0]
        # "python" -> [0, 1]
        async def mock_embed(text):
            if "apple" in text: return [1.0, 0.0]
            if "python" in text: return [0.0, 1.0]
            return [0.0, 0.0]
            
        self.mock_provider.embed.side_effect = mock_embed
        
        # Add memories
        asyncio.run(memory.add("I like apple"))
        asyncio.run(memory.add("I use python"))
        
        # Verify stored
        self.assertEqual(len(memory.memories), 2)
        
        # Search for "apple" -> Should match "I like apple"
        results = asyncio.run(memory.search("apple", limit=1))
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], "I like apple")
        self.assertAlmostEqual(results[0]['score'], 1.0)
        
        # Search for "python"
        results = asyncio.run(memory.search("python", limit=1))
        self.assertEqual(results[0]['content'], "I use python")
        
        print("✓ Vector Search Logic Verified")

    def test_persistence(self):
        print("\n=== Testing Persistence ===")
        memory = VectorMemory(self.mock_provider, self.db_path)
        self.mock_provider.embed.return_value = [0.1, 0.2]
        
        asyncio.run(memory.add("Persistent Memory"))
        
        # Reload
        memory2 = VectorMemory(self.mock_provider, self.db_path)
        self.assertEqual(len(memory2.memories), 1)
        self.assertEqual(memory2.memories[0]['content'], "Persistent Memory")
        print("✓ Persistence Verified")

if __name__ == '__main__':
    unittest.main()
