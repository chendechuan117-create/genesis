
import logging
import asyncio
from typing import Dict, Any, List, Optional
from genesis.core.provider import NativeHTTPProvider, MockLLMProvider
from genesis.core.registry import provider_registry
# Ensure providers are loaded
import genesis.providers
logger = logging.getLogger(__name__)

# provider_name -> config attribute that must be truthy for it to be valid
# "antigravity" (local proxy) is always valid, handled separately
PROVIDER_KEY_MAP = {
    "deepseek": "deepseek_api_key",
    "openai": "openai_api_key",
    "openrouter": "openrouter_api_key",
    "sambanova": "sambanova_api_key",
    "siliconflow": "siliconflow_api_key",
    "dashscope": "dashscope_api_key",
    "qianfan": "qianfan_api_key",
    "zhipu": "zhipu_api_key",
}

class ProviderRouter:
    """
    Provider Router - Manages multiple LLM providers and handles failover.
    Decouples the 'brain' logic from the Agent body.
    """
    
    def __init__(self, config: Any, api_key: str = None, base_url: str = None, model: str = None):
        self.config = config
        self.providers: Dict[str, Any] = {}
        self.active_provider_name = 'antigravity'
        
        self._initialize_providers(api_key, base_url, model)
        self.active_provider = self.providers.get(self.active_provider_name)
        
        # Fallback if preferred provider not available
        if not self.active_provider:
            if 'deepseek' in self.providers:
                self._switch_provider('deepseek')
            elif 'gemini' in self.providers:
                self._switch_provider('gemini')
            else:
                 # Last resort mock
                 self.providers['mock'] = MockLLMProvider()
                 self._switch_provider('mock')

    def _initialize_providers(self, api_key: str, base_url: str, model: str):
        """Initialize all available providers based on the dynamically registered factories"""
        
        for name in provider_registry.list_providers():
            builder = provider_registry.get_builder(name)
            if not builder:
                continue
            try:
                provider_instance = builder(self.config)
                if not provider_instance:
                    continue
                    
                # Legacy override: explicit runtime key for deepseek
                if name == "deepseek" and api_key:
                    provider_instance.api_key = api_key
                
                # Validate: key-based providers need their config key; local proxy always valid
                required_attr = PROVIDER_KEY_MAP.get(name)
                is_valid = (
                    name == "antigravity"
                    or api_key
                    or (required_attr and getattr(self.config, required_attr, None))
                )
                
                if is_valid:
                    self.providers[name] = provider_instance
                    logger.info(f"Initialized Provider from Registry: {name}")
                             
            except Exception as e:
                logger.warning(f"Failed to build provider plugin '{name}': {e}")
        
        # Determine Activation & Failover Order
        self.failover_order = ['deepseek', 'openrouter', 'openai', 'antigravity']
        
        self.active_provider_name = 'antigravity'
        for name in self.failover_order:
            if name in self.providers:
                self.active_provider_name = name
                break
                
    def _switch_provider(self, target: str):
        """Switch active provider"""
        if target not in self.providers:
            # logger.error(f"Cannot switch to unknown provider: {target}")
            return False
            
        if target == self.active_provider_name:
            return True
            
        logger.warning(f"⚠️ Switching Provider: {self.active_provider_name} -> {target}")
        self.active_provider_name = target
        self.active_provider = self.providers[target]
        return True

    async def chat_with_failover(self, messages: List[Dict], **kwargs) -> Any:
        """Wrapper for chat with dynamic failover"""
        if not self.active_provider:
             raise RuntimeError("No active provider available")

        # Try active first
        try:
            return await self.active_provider.chat(messages=messages, **kwargs)
        except Exception as e:
            logger.error(f"Provider {self.active_provider_name} Failed: {e}")
            
            # Dynamic Failover
            current_index = -1
            try:
                current_index = self.failover_order.index(self.active_provider_name)
            except ValueError:
                pass
                
            # Try next providers in the list
            start_index = current_index + 1
            for next_provider_name in self.failover_order[start_index:]:
                if next_provider_name in self.providers:
                     if self._switch_provider(next_provider_name):
                         logger.info(f"🔄 Failover Attempt: {next_provider_name}")
                         try:
                             return await self.active_provider.chat(messages=messages, **kwargs)
                         except Exception as e2:
                             logger.error(f"Backup Provider {next_provider_name} also failed: {e2}")
                             continue # Try next
            
            # If all failed
            raise e
    
    # Delegate standard provider methods to active provider
    
    async def chat(self, *args, **kwargs):
        return await self.chat_with_failover(*args, **kwargs)
        
    def get_active_provider(self):
        return self.active_provider

    def get_consumable_provider(self):
        """Returns the first available cheap/free provider from the consumables pool"""
        consumable_order = ['sambanova', 'siliconflow', 'dashscope', 'zhipu', 'qianfan']
        for name in consumable_order:
            if name in self.providers:
                logger.info(f"🧬 Selected Consumable Provider: {name}")
                return self.providers[name]
                
        logger.warning("No Consumable Provider found! Falling back to active provider (May consume premium tokens!)")
        return self.active_provider
