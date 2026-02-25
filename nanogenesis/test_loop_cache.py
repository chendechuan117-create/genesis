import asyncio
from genesis.core.factory import GenesisFactory

async def main():
    agent1 = GenesisFactory.create_common(user_id="Cache_Tester_Final")
    # Only keep static plugins for strict test
    agent1.loop.context.pipeline.plugins = [p for p in agent1.loop.context.pipeline.plugins if p.category == 'static']
    
    # 强制增加 System Prompt 长度以触发 DeepSeek 的 1024 Token 缓存阈值
    padding = "\n" + ("This is a deterministic static padding string to ensure the system prompt exceeds the minimum token length required for DeepSeek prefix caching to activate. " * 100)
    agent1.loop.context.system_prompt += padding
    
    print("=== Request 1 (Expect Miss) ===")
    r1, m1 = await agent1.loop.run("hello, what is your name?", user_context="Context 1")
    print(f"Metrics 1 -> Input: {m1.input_tokens}, Cache: {m1.prompt_cache_hit_tokens}")
    
    print("\n=== Request 2 (Expect Hit on System Prompt) ===")
    r2, m2 = await agent1.loop.run("hello again, list your tools", user_context="Context 2")
    print(f"Metrics 2 -> Input: {m2.input_tokens}, Cache: {m2.prompt_cache_hit_tokens}")

if __name__ == "__main__":
    asyncio.run(main())
