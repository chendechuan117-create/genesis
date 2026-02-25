import asyncio
import logging
from genesis.core.factory import GenesisFactory

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

async def test_packager():
    print("--- Booting Genesis with Dual-Track SDK ---")
    agent = GenesisFactory.create_common(enable_optimization=False)
    
    prompt = "查看 deploy 目录下的 deploy_remote.sh 文件，不用修改，告诉我它部署的默认远程目录（REMOTE_DIR）是什么？"
    print(f"User: {prompt}\n")
    
    result = await agent.process(prompt)
    
    print("\n--- Final Output ---")
    print(result['response'])

if __name__ == "__main__":
    asyncio.run(test_packager())
