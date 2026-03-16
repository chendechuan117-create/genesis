from genesis.core.provider import NativeHTTPProvider
from genesis.core.registry import provider_registry

def _build_deepseek(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'deepseek_api_key', None)
    
    # We allow returning the provider even if the key is None to support 
    # lazy initialization or environment fallbacks during actual API calls
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat"
    )

def _build_openai(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'openai_api_key', None)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o"
    )

def _build_openrouter(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'openrouter_api_key', None)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_model="meta-llama/llama-3.2-3b-instruct:free"
    )

def _build_antigravity(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'antigravity_key', "default-local-key") 
    url = getattr(config, 'antigravity_url', "http://127.0.0.1:8045/v1")
    return NativeHTTPProvider(
        api_key=api_key,
        base_url=url,
        default_model="gemini-2.5-flash"
    )

def _build_siliconflow(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'siliconflow_api_key', None)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://api.siliconflow.cn/v1",
        default_model="deepseek-ai/DeepSeek-V3" # Good fast baseline
    )

def _build_dashscope(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'dashscope_api_key', None)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus"
    )

def _build_qianfan(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'qianfan_api_key', None)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://qianfan.baidubce.com/v2",
        default_model="ernie-speed-128k"
    )

def _build_zhipu(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'zhipu_api_key', None)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4-flash"
    )

# Register all standard cloud providers
provider_registry.register("deepseek", _build_deepseek)
provider_registry.register("openai", _build_openai)
provider_registry.register("openrouter", _build_openrouter)
provider_registry.register("antigravity", _build_antigravity)

# Register Consumables Pool
provider_registry.register("siliconflow", _build_siliconflow)
provider_registry.register("dashscope", _build_dashscope)
provider_registry.register("qianfan", _build_qianfan)
provider_registry.register("zhipu", _build_zhipu)
