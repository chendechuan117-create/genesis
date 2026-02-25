import asyncio
import os
import shutil
from genesis.core.factory import GenesisFactory

async def main():
    # Clean up any previously self-forged tools before the test
    target_tool_path = "genesis/skills/ast_analyzer.py"
    if os.path.exists(target_tool_path):
        os.remove(target_tool_path)
        
    print("🔥 Forcing Genesis to analyze an AST without a pre-built tool...")
    agent = GenesisFactory.create_common(user_id="test_self_tooling", max_iterations=5, enable_optimization=False)
    
    # We ask it a question that forces it to realize it needs structured parsing
    mission = "我需要你帮我分析 `genesis/core/factory.py` 的代码结构。请提取出该文件里所有的类，以及这些类下的所有方法名。提示：由于这个文件有点长，不建议你用 grep，去现写一个基于 python `ast` 库的解析工具并加载它来完成这个任务。"
    
    result = await agent.process(user_input=mission)
    messages = result.get('messages', [])
    for m in messages:
        print(f"[{m.role}]: {m.content[:200]}...\n")
        
if __name__ == "__main__":
    asyncio.run(main())
