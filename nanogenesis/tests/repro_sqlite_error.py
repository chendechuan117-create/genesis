import sys
import sqlite3
import logging
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.memory import SQLiteMemoryStore
import asyncio

logging.basicConfig(level=logging.INFO)

async def main():
    print("🚀 Reproducing SQLite Error...")
    store = SQLiteMemoryStore()
    
    # Inject dummy data if needed, but error likely happens on search
    await store.add("My codename is Project-X.")
    
    print("\n👉 Searching: 'Project-X'")
    try:
        results = await store.search("Project-X")
        print(f"✅ Results: {len(results)}")
        for r in results:
            print(r)
    except Exception as e:
        print(f"❌ Search Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
