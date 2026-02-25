import asyncio
import logging
from genesis.core.factory import GenesisFactory

logging.basicConfig(level=logging.INFO, format='%(message)s')

async def main():
    agent = GenesisFactory.create_common(user_id="test_user", enable_optimization=False)
    
    print("\n\n--- TEST: Entropy-Driven Circuit Breaker ---")
    instruction = (
        "I want you to use the `shell` tool to run the following commands in exact order, one tool call per command, even though they will fail. Do not stop until you have run all 4. \n"
        "1. `cat /non_existent_file_1`\n"
        "2. `cat /non_existent_file_2`\n"
        "3. `cat /non_existent_file_3`\n"
        "4. `cat /non_existent_file_4`\n"
        "Notice that each command generates a SLIGHTLY different error message because the filename is different. "
        "Your new entropy-driven circuit breaker should allow you to execute all 4 without triggering a Strategic Interrupt."
    )
    
    print(f"Instruction: {instruction}\n")
    try:
        response = await agent.process(instruction)
        print("\n\n=== FINAL PACKAGED RESPONSE ===")
        print(response)
    except Exception as e:
        print(f"\n\nERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
