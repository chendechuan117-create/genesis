
import asyncio
import logging
import sys
import os

sys.path.append(os.getcwd())
from nanogenesis.core.provider import NativeHTTPProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_proxy():
    print("Testing Antigravity Tools Proxy (Port 8045)...")
    
    configs = [
        # Attempt 1: User Text Key
        {
            "name": "User Text Key (sk-f516...)",
            "api_key": "sk-f516a02bafd04d20a2e6904101d5045b",
            "base_url": "http://127.0.0.1:8045/v1",
            "model": "gemini-1.5-flash"
        },
        # Attempt 2: Screenshot Key
        {
            "name": "Screenshot Key (sk-2ae0...)",
            "api_key": "sk-2ae05ee05151417b9e71d7bb8da7545a",
            "base_url": "http://127.0.0.1:8045/v1",
            "model": "gemini-1.5-flash"
        },
        # Attempt 3: Try 'gpt-3.5-turbo' mapping
        {
            "name": "Map to GPT-3.5 (Screenshot Key)",
            "api_key": "sk-2ae05ee05151417b9e71d7bb8da7545a",
            "base_url": "http://127.0.0.1:8045/v1",
            "model": "gpt-3.5-turbo"
        }
    ]
    
    for config in configs:
        print(f"\n--- Testing [{config['name']}] ---")
        print(f"URL: {config['base_url']}")
        print(f"Model: {config['model']}")
        print(f"Key: {config['api_key'][:10]}...")
        
        provider = NativeHTTPProvider(
            api_key=config['api_key'],
            base_url=config['base_url'],
            default_model=config['model']
        )
        
        messages = [{"role": "user", "content": "Hello via Proxy! Reply 'Connected'."}]
        
        try:
            response = await provider.chat(messages, stream=False)
            print("Response:", response)
            if response.content:
                print("✓ SUCCESS!")
                return # Stop if successful
        except Exception as e:
            print(f"❌ FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_proxy())
