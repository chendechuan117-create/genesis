import asyncio
import sys
from pathlib import Path

# Ensure genesis is in the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.core.config import ConfigManager
from genesis.core.registry import provider_registry, tool_registry
from genesis.core.factory import GenesisFactory
from genesis.core.provider_manager import ProviderRouter

def get_test_config():
    """Provides a sterile, test-specific config environment"""
    cfg_manager = ConfigManager()
    cfg = cfg_manager.config
    cfg.deepseek_api_key = "test_key_deepseek"
    cfg.openai_api_key = "test_key_openai"
    cfg.openrouter_api_key = "test_key_openrouter"
    return cfg

def test_provider_registry_architecture():
    """
    [CONTRACT LEVEL 1: PROVIDER ISOLATION]
    Asserts that providers are dynamically loaded from the registry
    without being hardcoded into the ProviderRouter.
    """
    config = get_test_config()
    # 1. Ensure the registry has the core cloud providers loaded via the __init__ hook
    import genesis.providers
    
    assert "deepseek" in provider_registry.list_providers(), "DeepSeek not found in registry"
    assert "openai" in provider_registry.list_providers(), "OpenAI not found in registry"
    
    # 2. Build the router
    router = ProviderRouter(config)
    
    # 3. Assert that the router instantiated the providers by asking the registry,
    # rather than building them itself.
    assert "deepseek" in router.providers, "ProviderRouter failed to load DeepSeek from registry"
    assert "openai" in router.providers, "ProviderRouter failed to load OpenAI from registry"
    
    # 4. Verify that timeout settings from config properly cascade into the provider
    assert router.providers["deepseek"].api_key == "test_key_deepseek", "API Key did not cascade correctly"
    print("✅ [CONTRACT LEVEL 1] Provider Isolation Passed")

async def test_tool_factory_auto_discovery():
    """
    [CONTRACT LEVEL 2: TOOL AUTO-DISCOVERY]
    Asserts that the system boots up and auto-discovers tools from the 
    tools/ directory rather than relying on hardcoded imports in factory.py.
    """
    config = get_test_config()
    print("⏳ Building GenesisFactory...")
    # Create the agent via the factory
    agent = GenesisFactory.create_common(
        user_id="test_user",
        enable_optimization=False
    )
    print("✅ GenesisFactory built successfully.")
    
    # Assert that tool_registry was populated during creation
    registered_tools = tool_registry.list_tools()
    
    assert "shell" in registered_tools, "The core 'shell' tool failed to auto-discover."
    assert "browser" in registered_tools, "The core 'browser' tool failed to auto-discover."
    assert "list_directory" in registered_tools, "list_directory failed to auto-discover"
    
    # Assert that the loop logic is bound to the dynamic max_iterations config
    assert agent.loop.max_iterations == config.max_iterations, "Loop max_iterations not synced with config"
    print("✅ [CONTRACT LEVEL 2] Tool Auto-Discovery Passed")

if __name__ == "__main__":
    print("🚀 Running Architecture Contracts...")
    test_provider_registry_architecture()
    asyncio.run(test_tool_factory_auto_discovery())
    print("✨ All Architecture Contracts Passed Successfully.")
