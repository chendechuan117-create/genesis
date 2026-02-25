import asyncio
from genesis.core.factory import GenesisFactory

async def main():
    agent = GenesisFactory.create_common(user_id="Cache_Tester")
    agent.loop.context.pipeline.plugins = [p for p in agent.loop.context.pipeline.plugins if p.category == 'static']
    
    # Pad the system prompt to ensure it's >1024 tokens
    agent.loop.context.system_prompt += "\n" + ("<STATIC_PAD> " * 800)
    
    print("=== Request 1 ===")
    r1, m1 = await agent.loop.run("hello", user_context="Context 1")
    print(f"Metrics 1 -> Input: {m1.input_tokens}, Cache: {m1.prompt_cache_hit_tokens}")
    
    agent.loop.context._message_history = []
    print("\nWaiting 3 seconds for DeepSeek to write Prefix Cache...")
    await asyncio.sleep(3)
    
    print("\n=== Request 2 ===")
    r2, m2 = await agent.loop.run("hello", user_context="Context 2")
    print(f"Metrics 2 -> Input: {m2.input_tokens}, Cache: {m2.prompt_cache_hit_tokens}")

if __name__ == "__main__":
    asyncio.run(main())
