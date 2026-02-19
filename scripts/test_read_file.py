
import asyncio
import sys
from pathlib import Path
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_read_file")

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.tools.file_tools import ReadFileTool

async def main():
    print("🚀 Testing ReadFileTool...")
    tool = ReadFileTool()
    
    # Try to read a known file
    target = Path(__file__).parent.parent / ".env"
    print(f"Reading {target}...")
    
    result = await tool.execute(str(target))
    print(f"Result:\n{result}")
    
    if "Error" in result:
        print("❌ ReadFileTool Failed")
    else:
        print("✅ ReadFileTool Worked")

if __name__ == "__main__":
    asyncio.run(main())
