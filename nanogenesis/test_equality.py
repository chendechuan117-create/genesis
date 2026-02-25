import asyncio
import json
from genesis.core.factory import GenesisFactory

async def main():
    agent = GenesisFactory.create_common(user_id="Cache_Tester")
    agent.loop.context.pipeline.plugins = [p for p in agent.loop.context.pipeline.plugins if p.category == 'static']
    
    # Pad the system prompt to ensure it's >1024 tokens
    agent.loop.context.system_prompt += "\n" + ("<STATIC_PAD> " * 800)
    
    # Get the actual HTTP provider from the router
    provider = agent.loop.provider.active_provider
    
    payload_bytes = []
    
    original_stream = provider._stream_with_curl
    original_chat = provider._chat_with_curl
    
    async def intercept_stream(url, headers, data, callback):
        payload_bytes.append(data)
        return await original_stream(url, headers, data, callback)
        
    def intercept_chat(url, headers, data):
        payload_bytes.append(data)
        return original_chat(url, headers, data)
        
    provider._stream_with_curl = intercept_stream
    provider._chat_with_curl = intercept_chat
    
    print("=== Request 1 ===")
    r1, m1 = await agent.loop.run("hello", user_context="Context 1")
    print(f"Metrics 1 -> Input: {m1.input_tokens}, Cache: {m1.prompt_cache_hit_tokens}")
    
    agent.loop.context._message_history = []
    print("\n=== Request 2 ===")
    r2, m2 = await agent.loop.run("hello", user_context="Context 2")
    print(f"Metrics 2 -> Input: {m2.input_tokens}, Cache: {m2.prompt_cache_hit_tokens}")
    
    with open('data1.json', 'wb') as f: f.write(payload_bytes[0])
    with open('data2.json', 'wb') as f: f.write(payload_bytes[1])

if __name__ == "__main__":
    asyncio.run(main())
