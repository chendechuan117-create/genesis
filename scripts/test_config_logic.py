import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

# Mock environment before importing config
os.environ["DEEPSEEK_API_KEY"] = "sk-deepseek-test"
os.environ["OPENAI_API_KEY"] = "sk-openai-test"

from genesis.core.config import ConfigManager
from genesis.core.provider_manager import ProviderRouter

def test_config_separation():
    print("🚀 Verifying Config Logic...")
    
    # Re-instantiate ConfigManager (it's a singleton, but we can inspect its state or force re-init if needed)
    # Since it's a singleton pattern without reset, and might have been imported already,
    # we rely on the fact that we set env vars *before* importing config in this script's process.
    
    # NOTE: Since python modules are cached, if config was imported before setting env, it won't see changes.
    # But this is a standalone script execution, so it should be fine.
    
    cm = ConfigManager()
    cfg = cm.config
    
    print(f"DeepSeek Key: {cfg.deepseek_api_key}")
    print(f"OpenAI Key:   {cfg.openai_api_key}")
    
    if cfg.deepseek_api_key == "sk-deepseek-test" and cfg.openai_api_key == "sk-openai-test":
        print("✅ PASS: Keys are separated correctly.")
    else:
        print("❌ FAIL: Keys are mixed up or missing.")
        if cfg.deepseek_api_key == "sk-openai-test":
            print("⚠️ ERROR: OpenAI key overwrote DeepSeek key!")

    # Verify Provider Router
    router = ProviderRouter(config=cfg)
    print(f"\nProviders Initialized: {list(router.providers.keys())}")
    print(f"Active Provider: {router.active_provider_name}")
    
    if 'deepseek' in router.providers and 'openai' in router.providers:
        print("✅ PASS: Both providers initialized.")
    else:
        print("❌ FAIL: Missing providers.")

    if router.active_provider_name == 'deepseek':
         print("✅ PASS: DeepSeek selected as default (priority).")

    # Test OpenAI fallback scenario
    print("\n[Simulating OpenAI-only scenario...]")
    # Hack: temporarily clear deepseek key in config object to test selection logic
    original_ds_key = cfg.deepseek_api_key
    cfg.deepseek_api_key = None
    
    router_fallback = ProviderRouter(config=cfg)
    print(f"Active Provider (No DeepSeek): {router_fallback.active_provider_name}")
    
    if router_fallback.active_provider_name == 'openai':
        print("✅ PASS: OpenAI selected when DeepSeek is missing.")
    else:
        print(f"❌ FAIL: Incorrect fallback selection: {router_fallback.active_provider_name}")
        
    # Restore
    cfg.deepseek_api_key = original_ds_key

if __name__ == "__main__":
    test_config_separation()
