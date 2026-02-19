
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, "/home/chendechusn/Genesis/nanogenesis")

from genesis.core.provider import NativeHTTPProvider

async def main():
    print("🚀 Testing NativeHTTPProvider Connectivity...")
    
    # Use a dummy key - we expect 401, but we want to see if we get a response, not a connection error.
    # If we get "Expecting value...", it means we failed to handle the non-JSON 401 response (which is likely HTML or text).
    # DeepSeek usually returns JSON 401 if the format is correct.
    
    provider = NativeHTTPProvider(api_key="invalid_test_key")
    
    print(f"📡 Connecting to: {provider.base_url}")
    
    messages = [{"role": "user", "content": "Hello"}]
    
    try:
        response = await provider.chat(messages)
        print("✅ Success (Unexpectedly got a valid response with invalid key?)")
        print(response)
    except Exception as e:
        print(f"⚠️ Caught expected exception: {e}")
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg or "API 响应解析失败" in error_msg:
             print("✅ Connection Successful (Server reachable, auth failed as expected)")
             if "Content:" in error_msg:
                 print(f"📄 Response Content Preview: {error_msg.split('Content:')[-1][:200]}")
        elif "curl 失败" in error_msg:
             print("❌ Connection Failed (curl execution error)")
        else:
             print(f"❓ Unknown Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
