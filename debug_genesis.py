import asyncio
import logging
from nanogenesis.agent import NanoGenesis

# Configure intense logging
logging.basicConfig(level=logging.DEBUG)

async def run_scenario():
    print("Initializing NanoGenesis (Multi-Provider Mode)...")
    agent = NanoGenesis(
        gemini_key="sk-8bf1cea5032d4ec0bfd421630814bff0",
        gemini_url="http://127.0.0.1:8045/v1"
    )
    
    prompt = "你是谁？你自己动手赚钱试试。"
    print(f"\nSending prompt: {prompt}\n")
    
    async def step_callback(step_type, data):
        print(f"[{step_type.upper()}] {data[:100]}...")  # Truncate for readability
        
    try:
        response_data = await agent.process(prompt, step_callback=step_callback)
        print("\n--- FINAL RESPONSE ---")
        print(response_data.get("response", "No response content"))
        print("\n--- FULL DATA ---")
        print(response_data)
    except Exception as e:
        print(f"\nCRITICAL FAILURE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_scenario())
