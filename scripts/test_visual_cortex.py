
import sys
import asyncio
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.tools.visual_tool import VisualTool

async def test_visual_cortex():
    print("🚀 Testing Visual Cortex...")
    
    tool = VisualTool()
    
    # 1. Test Desktop Capture (as we likely don't have ADB connected in this environment)
    # Use 'desktop' target. If scrot is missing, it might fail, but let's try.
    print("\n📸 Attempting Desktop Capture...")
    result = await tool.execute(action="capture_screenshot", target="desktop")
    
    if isinstance(result, dict) and result.get("type") == "image":
        print(f"✅ Capture Success: {result['path']}")
        
        # 2. Verify File Exists
        path = Path(result['path'])
        if path.exists():
            print(f"✅ File Verified: {path} ({path.stat().st_size} bytes)")
        else:
            print("❌ File NOT found on disk!")
            return


        # 3. Simulate Loop Processing (Base64 Encoding)
        print("\n🧠 Simulating Neuro-Optic Pathway...")
        try:
            import base64
            with open(path, "rb") as img_file:
                b64_str = base64.b64encode(img_file.read()).decode("utf-8")
            print(f"✅ Base64 Conversion Success (First 50 chars): {b64_str[:50]}...")
            
            payload = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64_str}"
                }
            }
            print("✅ Multimodal Payload Constructed!")
            
            # 4. LIVE TEST: Call OpenRouter
            print("\n📡 Connecting to Cloud Brain (OpenRouter)...")
            from genesis.core.config import config
            from genesis.core.provider_manager import ProviderRouter
            
            # Force reload config to pick up .env changes if needed
            # In a script, config is loaded at import time. 
            # Assuming .env was written before this script runs.
            
            router = ProviderRouter(config)
            provider = router.get_active_provider()
            
            if not provider:
                print("❌ No active provider found in config!")
                return

            messages = [
                {"role": "system", "content": "You are a Vision AI. Describe what you see in the image briefly."},
                {"role": "user", "content": [
                    {"type": "text", "text": "What is in this screenshot?"},
                    payload
                ]}
            ]
            
            print(f"📤 Sending Request to {config.openrouter_model}...")
            response = await provider.chat(messages=messages)
             
            print("\n🤖 VISION RESPONSE:")
            print("-" * 40)
            print(response.content)
            print("-" * 40)
            print("✅ End-to-End Vision Test PASSED!")
            
        except Exception as e:
            print(f"❌ Pathway Simulation Failed: {e}")

    else:
        print(f"⚠️ Capture Output: {result}")

        print("(This might be expected if 'scrot' is missing in the CI/CD environment)")

if __name__ == "__main__":
    asyncio.run(test_visual_cortex())
