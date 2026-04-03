from genesis.core.provider import NativeHTTPProvider
from genesis.core.registry import provider_registry
from .aixj_responses_provider import AIXJResponsesProvider

def _build_aixj(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'aixj_api_key', None)
    if not api_key: return None
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://aixj.vip/v1",
        default_model="gpt-4.1",
        provider_name="aixj",
        skip_content_type=True
    )

def _build_codex(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'codex_api_key', None)
    if not api_key: return None
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://aixj.vip/v1",
        default_model="gpt-4.1",
        provider_name="codex",
        skip_content_type=True
    )

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
        default_model="gpt-4o",
        use_proxy=True
    )

def _build_gemini(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'gemini_api_key', None)
    # Use OpenAI compatibility mode for Gemini API
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.5-pro",
        provider_name="gemini",
        use_proxy=True
    )

def _build_openrouter(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'openrouter_api_key', None)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_model="meta-llama/llama-3.2-3b-instruct:free",
        use_proxy=True
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

def _build_groq(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'groq_api_key', None)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        provider_name="groq",
        use_proxy=True
    )

def _build_cloudflare(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'cloudflare_api_key', None)
    if not api_key: return None
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://api.cloudflare.com/client/v4/accounts/2c85cf36f8686813d3d0a5cf5483b1e4/ai/v1",
        default_model="@cf/meta/llama-3.1-8b-instruct",
        use_proxy=True
    )

def _build_zen(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'zen_api_key', None)
    if not api_key: return None
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://api.zenmux.com/v1",  
        default_model="gpt-4o-mini",
        use_proxy=True
    )

# Register all standard cloud providers
provider_registry.register("aixj", _build_aixj)
provider_registry.register("codex", _build_codex)
provider_registry.register("deepseek", _build_deepseek)
provider_registry.register("gemini", _build_gemini)
provider_registry.register("openai", _build_openai)
provider_registry.register("openrouter", _build_openrouter)

# Register Consumables Pool
provider_registry.register("siliconflow", _build_siliconflow)
provider_registry.register("dashscope", _build_dashscope)
provider_registry.register("qianfan", _build_qianfan)
provider_registry.register("zhipu", _build_zhipu)
provider_registry.register("groq", _build_groq)
provider_registry.register("cloudflare", _build_cloudflare)
provider_registry.register("zen", _build_zen)


def _build_aixj_responses(config) -> AIXJResponsesProvider:
    api_key = getattr(config, 'aixj_api_key', None)
    if not api_key: return None
    return AIXJResponsesProvider(
        api_key=api_key,
        base_url="https://api.aixj.cn/v1",
        default_model="gpt-4.1",
        provider_name="aixj_responses",
        skip_content_type=True
    )

# Register AIXJ Responses API provider
provider_registry.register("aixj_responses", _build_aixj_responses)
