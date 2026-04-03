import importlib
import sys
import types
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

    if 'genesis.providers' not in sys.modules:
        pkg = types.ModuleType('genesis.providers')
        pkg.__path__ = ['/workspace/genesis/providers']
        sys.modules['genesis.providers'] = pkg

    sys.modules.pop('genesis.providers.cloud_providers', None)
    return importlib.import_module('genesis.providers.cloud_providers')


def test_aixj_and_codex_default_models_do_not_regress_to_gpt_5_4():
    cloud_providers = _load_cloud_providers_module()
    config = SimpleNamespace(
        aixj_api_key='aixj-key',
        aixj_api_keys=[],
        codex_api_key='codex-key',
    )

    aixj = cloud_providers._build_aixj(config)
    codex = cloud_providers._build_codex(config)

    assert aixj is not None
    assert codex is not None
    assert aixj.get_default_model() == 'gpt-4.1'
    assert codex.get_default_model() == 'gpt-4.1'
    assert aixj.get_default_model() != 'gpt-5.4'
    assert codex.get_default_model() != 'gpt-5.4'
