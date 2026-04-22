from genesis.core.provider import NativeHTTPProvider
from genesis.core.registry import provider_registry
from .aixj_responses_provider import AIXJResponsesProvider

def _build_xcode(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'xcode_api_key', None)
    if not api_key: return None
    base_url = getattr(config, 'xcode_base_url', None) or "https://api.xcode.best/v1"
    default_model = getattr(config, 'xcode_model', None) or "gpt-5.4"
    host_header = getattr(config, 'xcode_host_header', None)
    ssl_verify = getattr(config, 'xcode_ssl_verify', True)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url=base_url,
        default_model=default_model,
        default_headers={"Host": host_header} if host_header else None,
        ssl_verify=ssl_verify,
        provider_name="xcode"
    )


def _build_xcode_backup(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'xcode_api_key', None)
    backup_base_url = getattr(config, 'xcode_backup_base_url', None)
    if not api_key or not backup_base_url:
        return None
    default_model = getattr(config, 'xcode_model', None) or "gpt-5.4"
    host_header = getattr(config, 'xcode_backup_host_header', None)
    ssl_verify = getattr(config, 'xcode_backup_ssl_verify', True)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url=backup_base_url,
        default_model=default_model,
        default_headers={"Host": host_header} if host_header else None,
        ssl_verify=ssl_verify,
        provider_name="xcode_backup"
    )


def _build_deepseek(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'deepseek_api_key', None)
    if not api_key: return None
    return NativeHTTPProvider(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        provider_name="deepseek"
    )


def _build_xcode_responses(config) -> AIXJResponsesProvider:
    api_key = getattr(config, 'xcode_api_key', None)
    if not api_key: return None
    base_url = getattr(config, 'xcode_base_url', None) or "https://api.xcode.best/v1"
    default_model = getattr(config, 'xcode_model', None) or "gpt-5.4"
    host_header = getattr(config, 'xcode_host_header', None)
    ssl_verify = getattr(config, 'xcode_ssl_verify', True)
    return AIXJResponsesProvider(
        api_key=api_key,
        base_url=base_url,
        default_model=default_model,
        default_headers={"Host": host_header} if host_header else None,
        ssl_verify=ssl_verify,
        provider_name="xcode_responses"
    )


def _build_newshrimp(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'newshrimp_api_key', None)
    if not api_key: return None
    base_url = getattr(config, 'newshrimp_base_url', None) or "https://api.new-shrimp.icu/v1"
    default_model = getattr(config, 'newshrimp_model', None) or "MiniMax-M2.7-highspeed"
    ssl_verify = getattr(config, 'newshrimp_ssl_verify', True)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url=base_url,
        default_model=default_model,
        ssl_verify=ssl_verify,
        provider_name="newshrimp"
    )


def _build_newshrimp_backup(config) -> NativeHTTPProvider:
    api_key = getattr(config, 'newshrimp_api_key', None)
    backup_base_url = getattr(config, 'newshrimp_backup_base_url', None)
    if not api_key or not backup_base_url: return None
    default_model = getattr(config, 'newshrimp_model', None) or "MiniMax-M2.7-highspeed"
    ssl_verify = getattr(config, 'newshrimp_backup_ssl_verify', True)
    return NativeHTTPProvider(
        api_key=api_key,
        base_url=backup_base_url,
        default_model=default_model,
        ssl_verify=ssl_verify,
        provider_name="newshrimp_backup"
    )


provider_registry.register("xcode", _build_xcode)
provider_registry.register("xcode_backup", _build_xcode_backup)
provider_registry.register("deepseek", _build_deepseek)
provider_registry.register("xcode_responses", _build_xcode_responses)
provider_registry.register("newshrimp", _build_newshrimp)
provider_registry.register("newshrimp_backup", _build_newshrimp_backup)
