import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace


def _stub_httpx():
    if 'httpx' in sys.modules:
        return
    httpx = types.ModuleType('httpx')

    class Timeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

    httpx.Timeout = Timeout
    httpx.AsyncClient = AsyncClient
    sys.modules['httpx'] = httpx


def _stub_aixj_responses_provider():
    module = types.ModuleType('genesis.providers.aixj_responses_provider')

    class AIXJResponsesProvider:
        def __init__(self, api_key=None, base_url=None, default_model=None, provider_name=None, skip_content_type=False):
            self.api_key = api_key
            self.base_url = base_url
            self.default_model = default_model
            self.provider_name = provider_name
            self.skip_content_type = skip_content_type

        def get_default_model(self):
            return self.default_model

    module.AIXJResponsesProvider = AIXJResponsesProvider
    sys.modules['genesis.providers.aixj_responses_provider'] = module


def _load_cloud_providers_module():
    _stub_httpx()
    _stub_aixj_responses_provider()

    sys.modules.pop('genesis.providers.cloud_providers', None)
    pkg = types.ModuleType('genesis.providers')
    pkg.__path__ = [str(Path(__file__).resolve().parents[1] / 'genesis' / 'providers')]
    sys.modules['genesis.providers'] = pkg
    return importlib.import_module('genesis.providers.cloud_providers')


def test_cloud_provider_default_models_match_current_policy():
    cloud_providers = _load_cloud_providers_module()
    config = SimpleNamespace(
        xcode_api_key='xcode-key',
        xcode_backup_base_url='https://backup.example/v1',
        aliyun_api_key='aliyun-key',
    )

    xcode = cloud_providers._build_xcode(config)
    xcode_backup = cloud_providers._build_xcode_backup(config)
    aliyun = cloud_providers._build_aliyun(config)

    assert xcode is not None
    assert xcode_backup is not None
    assert aliyun is not None
    assert xcode.get_default_model() == 'gpt-5.4'
    assert xcode_backup.get_default_model() == 'gpt-5.4'
    assert aliyun.get_default_model() == 'deepseek-v4-flash'
