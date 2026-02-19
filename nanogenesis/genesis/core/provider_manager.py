
import logging
import asyncio
from typing import Dict, Any, List, Optional
from genesis.core.provider import LiteLLMProvider, NativeHTTPProvider, LITELLM_AVAILABLE, MockLLMProvider

logger = logging.getLogger(__name__)

class ProviderRouter:
    """
    Provider Router - Manages multiple LLM providers and handles failover.
    Decouples the 'brain' logic from the Agent body.
    """
    
    def __init__(self, config: Any, api_key: str = None, base_url: str = None, model: str = None):
        self.config = config
        self.providers: Dict[str, Any] = {}
        
        # Determine default provider
        if getattr(config, 'openrouter_api_key', None):
            self.active_provider_name = 'deepseek' # OpenRouter is mapped to deepseek
        elif getattr(config, 'deepseek_api_key', None):
             self.active_provider_name = 'deepseek'
        elif getattr(config, 'openai_api_key', None):
             self.active_provider_name = 'openai'
        else:
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
        """Initialize all available providers based on config"""
        # 1. Initialize Providers based on available config
        # OpenRouter
        or_key = getattr(self.config, 'openrouter_api_key', None)
        if or_key:
            logger.info(f"Initialized Provider: OpenRouter")
            # Force use of a free model since user has no credits
            # utilizing google/gemini-2.0-flash-lite-preview-02-05:free
            self.providers['openrouter'] = NativeHTTPProvider(
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
                default_model="google/gemini-2.0-flash-lite-preview-02-05:free"
            )

        # DeepSeek Native
        ds_key = api_key or getattr(self.config, 'deepseek_api_key', None)
        if ds_key:
            logger.info("Initialized Provider: DeepSeek (Native)")
            self.providers['deepseek'] = NativeHTTPProvider(
                api_key=ds_key,
                base_url="https://api.deepseek.com/v1",
                default_model="deepseek-chat"
            )

        # OpenAI
        oa_key = getattr(self.config, 'openai_api_key', None)
        if oa_key:
            logger.info("Initialized Provider: OpenAI")
            self.providers['openai'] = NativeHTTPProvider(
                api_key=oa_key,
                base_url="https://api.openai.com/v1",
                default_model="gpt-4o"
            )

        # Antigravity (Local/Proxy)
        # Use config if available, otherwise fallback to defaults (but don't hardcode valid keys)
        ag_key = getattr(self.config, 'antigravity_key', "default-local-key") 
        ag_url = getattr(self.config, 'antigravity_url', "http://127.0.0.1:8045/v1")
        
        logger.info(f"Initialized Provider: Antigravity (Local/Proxy at {ag_url})")
        self.providers['antigravity'] = NativeHTTPProvider(
            api_key=ag_key,
            base_url=ag_url,
            default_model="gemini-2.5-flash"
        )
        
        # 2. Determine Activation & Failover Order
        # Default Priority: OpenRouter -> DeepSeek -> OpenAI -> Antigravity
        self.failover_order = ['openrouter', 'deepseek', 'openai', 'antigravity']
        
        # Set Active
        self.active_provider_name = 'antigravity' # Default fallback
        
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
