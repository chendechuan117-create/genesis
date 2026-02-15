import asyncio
import logging
import inspect
import nanogenesis
print(f"NANOGENESIS PATH: {nanogenesis.__file__}")

from nanogenesis.core.provider import NativeHTTPProvider
import os
import time

print(f"PROVIDER CLASS FILE: {inspect.getfile(NativeHTTPProvider)}")
try:
    stat = os.stat(inspect.getfile(NativeHTTPProvider))
    print(f"FILE SIZE: {stat.st_size} bytes")
    print(f"LAST MODIFIED: {time.ctime(stat.st_mtime)}")
except Exception as e:
    print(f"FAILED TO STAT FILE: {e}")

import hashlib
try:
    with open(inspect.getfile(NativeHTTPProvider), "rb") as f:
        data = f.read()
        print(f"FILE MD5: {hashlib.md5(data).hexdigest()}")
        content_str = data.decode("utf-8")
        if 'logger.debug(f"Starting curl command' in content_str:
            print("✅ FILE HAS LOGGING")
        else:
            print("❌ FILE DOES NOT HAVE LOGGING")
except Exception as e:
    print(f"FAILED TO HASH FILE: {e}")

print("Inspecting _stream_with_curl source code for 'logger.debug':")
src = inspect.getsource(NativeHTTPProvider._stream_with_curl)
if "logger.debug(f\"Starting curl command" in src:
    print("✓ Source contains logging statements.")
else:
    print("❌ Source DOES NOT contain logging statements.")
    print("Printing source snippet:")
    print(src[:500])

logging.basicConfig(level=logging.DEBUG)

async def test_curl():
    provider = NativeHTTPProvider()
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say Hello."}
    ]
    
    print("Sending simple prompt via NativeHTTPProvider...")
    
    async def callback(chunk_type, chunk_data):
        print(f"[{chunk_type}] {chunk_data}")
        
    try:
        response = await provider.chat(messages=messages, stream=True, stream_callback=callback)
        print("\n--- RESPONSE ---")
        print(response)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_curl())
