
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.tools.shell_tool import ShellTool

async def test_daemon_mercy():
    print("🚀 Initializing ShellTool with 2s timeout...")
    tool = ShellTool(timeout=2)
    
    # Simulate a fake scrcpy command
    # We use 'sleep 5' which is > 2s timeout
    # We include 'scrcpy' in the command name to trigger mercy logic
    cmd = "echo 'Starting generic daemon...'; sleep 5; echo 'Still running'"
    
    print(f"\n1. Running Command (is_daemon=True): {cmd}")
    result = await tool.execute(cmd, is_daemon=True)
    
    print(f"\n📋 Result Output:\n{result}")
    
    if "[TIMEOUT_GUARD] [参数指定]" in result:
        print("\n✅ Daemon Mercy Triggered! Process was NOT explicitly killed (per logic).")
    elif "[TIMEOUT_WARNING]" in result:
        print("\n❌ Failed: Process was killed (Standard Warning).")
    else:
        print("\n❓ Unexpected Result.")

if __name__ == "__main__":
    asyncio.run(test_daemon_mercy())
