import asyncio
import logging
from genesis.core.factory import GenesisFactory

logging.basicConfig(level=logging.INFO, format='%(message)s')

async def main():
    agent = GenesisFactory.create_common(user_id="test_user", enable_optimization=False)
    
    print("\n\n--- TEST: 3D Mission Tree & Capability Forge ---")
    instruction = (
        "I need you to calculate the trajectory of a ballistic missile. "
        "You currently DO NOT have a tool for this. "
        "As a test of your new 3D Mission Tree architecture, you MUST NOT try to write a python script blindly. "
        "You MUST first trigger your [CAPABILITY_FORGE] ability to spawn a Z-axis mission, "
        "and use `skill_creator` to forge a tool named `calculate_trajectory`. "
        "After acquiring it, use it to return the trajectory of a missile launched at 45 degrees with 100m/s velocity."
    )
    
    print(f"Instruction: {instruction}\n")
    try:
        response = await agent.run(instruction)
        print("\n\n=== FINAL PACKAGED RESPONSE ===")
        print(response)
    except Exception as e:
        print(f"\n\nERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
