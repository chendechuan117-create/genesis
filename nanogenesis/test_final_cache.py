import asyncio
from genesis.core.factory import GenesisFactory

async def main():
    agent = GenesisFactory.create_common(user_id="Cache_Tester")
    agent.loop.context.pipeline.plugins = [p for p in agent.loop.context.pipeline.plugins if p.category == 'static']
    
    # Inject a massive static block to guarantee we pass the 1024 token threshold
    agent.loop.context.system_prompt += "\n" + ("<STATIC_PADDING> " * 800)
    
    print("=== First Request (Should miss, populate cache) ===")
    r1, m1 = await agent.loop.run(
        user_input="hello", 
        user_context="Strategy: Hello."
    )
    print(f"Metrics 1 -> Input: {m1.input_tokens}, Cache Hit: {m1.prompt_cache_hit_tokens}")
    
    # We must start a NEW loop or clear the history, because if the history contains the Assistant's
    # previous response and tool calls, the prefix length is longer, so it should technically hit the 
    # System Prompt part of the prefix cache. Let's see!
    print("\n=== Second Request (Same agent, history appended) ===")
    r2, m2 = await agent.loop.run(
        user_input="hello again", 
        user_context="Strategy: Hello."
    )
    print(f"Metrics 2 -> Input: {m2.input_tokens}, Cache Hit: {m2.prompt_cache_hit_tokens}")
    
    # Clear history and try again
    agent.loop.context._message_history = []
    print("\n=== Third Request (Cleared history, identical system prefix) ===")
    r3, m3 = await agent.loop.run(
        user_input="hello three", 
        user_context="Strategy: Hello."
    )
    print(f"Metrics 3 -> Input: {m3.input_tokens}, Cache Hit: {m3.prompt_cache_hit_tokens}")

if __name__ == "__main__":
    asyncio.run(main())
