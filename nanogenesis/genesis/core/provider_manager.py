
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
        
        # 1. Primary: OpenRouter (Higher Priority if set) or DeepSeek
        final_or_key = getattr(self.config, 'openrouter_api_key', None)
        final_ds_key = api_key or getattr(self.config, 'deepseek_api_key', None)
        
        if final_or_key:
            logger.info(f"初始化 Primary Provider: OpenRouter (Model: {getattr(self.config, 'openrouter_model', 'trinity-large-preview')})")
            self.providers['deepseek'] = NativeHTTPProvider(
                api_key=final_or_key,
                base_url="https://openrouter.ai/api/v1",
                default_model=getattr(self.config, 'openrouter_model', "trinity-large-preview")
            )
            # Alias for clarity
            self.providers['openrouter'] = self.providers['deepseek']
            
        elif final_ds_key:
            logger.info("初始化 Primary Provider: DeepSeek (NativeHTTP)")
            self.providers['deepseek'] = NativeHTTPProvider(
                api_key=final_ds_key,
                base_url=base_url,
                default_model=model or "deepseek/deepseek-chat"
            )
        
        # Add OpenAI Support
        openai_key = getattr(self.config, 'openai_api_key', None)
        if openai_key:
            logger.info("初始化 Provider: OpenAI")
            self.providers['openai'] = NativeHTTPProvider(
                api_key=openai_key,
                base_url="https://api.openai.com/v1",
                default_model="gpt-4o"
            )

        if LITELLM_AVAILABLE and not final_ds_key and not final_or_key and not openai_key:
            logger.info("初始化 Primary Provider: LiteLLM")
            self.providers['deepseek'] = LiteLLMProvider(
                api_key=api_key,
                base_url=base_url,
                default_model=model or "deepseek/deepseek-chat"
            )
        
        # 2. Backup: Gemini (via Proxy)
        final_gemini_key = getattr(self.config, 'gemini_api_key', None)
        final_gemini_url = getattr(self.config, 'gemini_base_url', "http://127.0.0.1:8045/v1")
        
        if final_gemini_key:
            logger.info(f"初始化 Backup Provider: Gemini (Proxy at {final_gemini_url})")
            self.providers['gemini'] = NativeHTTPProvider(
                api_key=final_gemini_key,
                base_url=final_gemini_url,
                default_model="gemini-1.5-flash" 
            )
            
        # 3. Extension: Antigravity Tools
        # Explicit initialization for Antigravity as a distinct provider source
        logger.info("初始化 Extension Provider: Antigravity Tools")
        self.providers['antigravity'] = NativeHTTPProvider(
            api_key="sk-8bf1cea5032d4ec0bfd421630814bff0",
            base_url="http://127.0.0.1:8045/v1",
            default_model="gemini-2.5-flash"
        )

    def _switch_provider(self, target: str):
        """Switch active provider"""
        if target not in self.providers:
            logger.error(f"Cannot switch to unknown provider: {target}")
            return
            
        logger.warning(f"⚠️ Switching Provider: {self.active_provider_name} -> {target}")
        self.active_provider_name = target
        self.active_provider = self.providers[target]

    async def chat_with_failover(self, messages: List[Dict], **kwargs) -> Any:
        """Wrapper for chat with auto-failover"""
        if not self.active_provider:
             raise RuntimeError("No active provider available")

        try:
            return await self.active_provider.chat(messages=messages, **kwargs)
        except Exception as e:
            # Generic Failover Logic
            available = list(self.providers.keys())
            current = self.active_provider_name
            
            # Determine backup candidate
            backup = None
            if current == 'deepseek':
                # Prefer openai (stable), then antigravity (experimental), then gemini
                if 'openai' in self.providers: backup = 'openai'
                elif 'antigravity' in self.providers: backup = 'antigravity'
                elif 'gemini' in self.providers: backup = 'gemini'
            elif current == 'antigravity':
                 if 'deepseek' in self.providers: backup = 'deepseek'
                 elif 'openai' in self.providers: backup = 'openai'
                 elif 'gemini' in self.providers: backup = 'gemini'
            elif current == 'openai':
                 if 'deepseek' in self.providers: backup = 'deepseek'
                 elif 'antigravity' in self.providers: backup = 'antigravity'
            
            if backup:
                logger.error(f"Provider {current} Failed: {e}. Failover -> {backup}")
                self._switch_provider(backup)
                try:
                    return await self.active_provider.chat(messages=messages, **kwargs)
                except Exception as e2:
                    logger.error(f"Backup Provider {backup} also failed: {e2}")
                    raise e2
            else:
                raise e
    
    # Delegate standard provider methods to active provider
    
    async def chat(self, *args, **kwargs):
        return await self.chat_with_failover(*args, **kwargs)
        
    def get_active_provider(self):
        return self.active_provider
