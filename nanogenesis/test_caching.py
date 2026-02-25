import asyncio
import os
import json
from genesis.core.factory import GenesisFactory

async def main():
    agent = GenesisFactory.create_common(user_id="Cache_Tester")
    
    # Monkey patch the curl command entirely since NativeHTTPProvider uses subprocess
    original_create_subprocess_exec = asyncio.create_subprocess_exec
    
    async def debug_subprocess_exec(*args, **kwargs):
        if args[0] == 'curl':
            # Extract the JSON payload, which is the argument after -d
            for i, arg in enumerate(args):
                if arg == "-d" and i + 1 < len(args):
                    with open("debug_payload.json", "a", encoding="utf-8") as f:
                        f.write(args[i+1] + "\n---\n")
        return await original_create_subprocess_exec(*args, **kwargs)
        
    asyncio.create_subprocess_exec = debug_subprocess_exec
    
    print("=== First Request ===")
    await agent.process("Hello, what is your name?", user_context="Static.")
    
    print("\n=== Second Request ===")
    await agent.process("What did I just ask?", user_context="Static.")

if __name__ == "__main__":
    if os.path.exists("debug_payload.json"):
        os.remove("debug_payload.json")
    asyncio.run(main())
