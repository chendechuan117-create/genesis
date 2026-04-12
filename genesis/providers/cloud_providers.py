from genesis.core.provider import NativeHTTPProvider
from genesis.core.registry import provider_registry
from .aixj_responses_provider import AIXJResponsesProvider

def _build_xcode(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'xcode_api_key', None)
    if not api_key: return None
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://api.xcode.best/v1",
        default_model="gpt-5.4",
        provider_name="xcode"
    )


def _build_xcode_responses(config) -> AIXJResponsesProvider:
    api_key = getattr(config, 'xcode_api_key', None)
    if not api_key: return None
    return AIXJResponsesProvider(
        api_key=api_key,
        base_url="https://api.xcode.best/v1",
        default_model="gpt-4.1",
        provider_name="xcode_responses"
    )


provider_registry.register("xcode", _build_xcode)
provider_registry.register("xcode_responses", _build_xcode_responses)
