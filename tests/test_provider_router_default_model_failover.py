import asyncio
import importlib
import sys
import types
from types import SimpleNamespace

import pytest


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


def _reset_provider_modules():
    for name in [
        'genesis.core.provider_manager',
        'genesis.providers.cloud_providers',
        'genesis.providers',
    ]:
        sys.modules.pop(name, None)


def _load_router_module():
    _stub_httpx()
    _stub_aixj_responses_provider()
    _reset_provider_modules()

    if 'genesis.providers' not in sys.modules:
        pkg = types.ModuleType('genesis.providers')
        pkg.__path__ = ['/workspace/genesis/providers']
        sys.modules['genesis.providers'] = pkg

    import genesis.core.provider_manager as provider_manager
    return provider_manager


class DummyProvider:
    def __init__(self, name, default_model, outcomes):
        self.name = name
        self._default_model = default_model
        self.outcomes = list(outcomes)
        self.calls = 0
        self.api_key = f'{name}-key'
        self._http_client = None

    async def chat(self, messages, **kwargs):
        self.calls += 1
        if not self.outcomes:
            raise AssertionError(f'No outcomes queued for {self.name}')
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_default_model(self):
        return self._default_model


class ProviderError(Exception):
    def __init__(self, status_code, message, error_type=None, category=None, already_retried=False):
        super().__init__(f'{status_code} {message} [{error_type or category or "error"}]')
        self.status_code = status_code
        self.message = message
        self.error_type = error_type
        self.category = category
        self.already_retried = already_retried


class DummyResponse:
    def __init__(self, content):
        self.content = content
        self.tool_calls = []
        self.finish_reason = 'stop'
        self.input_tokens = 1
        self.output_tokens = 1
        self.total_tokens = 2
        self.has_tool_calls = False


def ok_response(text):
    return DummyResponse(text)


@pytest.fixture()
def router_module(monkeypatch):
    provider_manager = _load_router_module()

    class DummyTracer:
        @staticmethod
        def get_instance():
            return DummyTracer()

        def log_llm_call(self, *args, **kwargs):
            return None

    monkeypatch.setattr(provider_manager, 'Tracer', DummyTracer)
    return provider_manager


def _build_router_with_registry(monkeypatch, router_module, builders, config=None):
    names = list(builders.keys())

    monkeypatch.setattr(router_module.provider_registry, 'list_providers', lambda: names)
    monkeypatch.setattr(router_module.provider_registry, 'get_builder', lambda name: builders[name])

    cfg = config or SimpleNamespace(
        xcode_api_key='xcode-key',
        aliyun_api_key=None,
        newshrimp_api_key=None,
        newshrimp_2_api_key=None,
        newshrimp_3_api_key=None,
        deepseek_api_key=None,
        openai_api_key=None,
        openrouter_api_key=None,
        siliconflow_api_key=None,
        dashscope_api_key=None,
        qianfan_api_key=None,
        zhipu_api_key=None,
        groq_api_key=None,
        cloudflare_api_key=None,
        zen_api_key=None,
    )
    return router_module.ProviderRouter(cfg)


def test_provider_router_init_prefers_available_provider_and_exposes_its_default_model(monkeypatch, router_module):
    xcode = DummyProvider('xcode', 'gpt-4.1', [ok_response('ok')])
    xcode_backup = DummyProvider('xcode_backup', 'gpt-4.1-mini', [ok_response('backup-ok')])

    router = _build_router_with_registry(
        monkeypatch,
        router_module,
        {
            'xcode': lambda config: xcode,
            'xcode_backup': lambda config: xcode_backup,
        },
    )

    assert router.active_provider_name == 'xcode'
    assert router.get_active_provider() is xcode
    assert router.get_default_model() == 'gpt-4.1'
    assert router.get_default_model() != 'gpt-5.4'


def test_provider_router_failover_switches_active_provider_and_default_model(monkeypatch, router_module):
    xcode = DummyProvider(
        'xcode',
        'gpt-4.1',
        [ProviderError(503, 'Service temporarily unavailable', error_type='http_error')],
    )
    xcode_backup = DummyProvider('xcode_backup', 'gpt-4.1-mini', [ok_response('ok-from-backup')])

    router = _build_router_with_registry(
        monkeypatch,
        router_module,
        {
            'xcode': lambda config: xcode,
            'xcode_backup': lambda config: xcode_backup,
        },
    )

    result = asyncio.run(router.chat(messages=[{'role': 'user', 'content': 'ping'}]))

    assert result.content == 'ok-from-backup'
    assert xcode.calls == 1
    assert xcode_backup.calls == 1
    assert router.active_provider_name == 'xcode_backup'
    assert router.get_active_provider() is xcode_backup
    assert router.get_default_model() == 'gpt-4.1-mini'
    assert router.get_default_model() != 'gpt-5.4'




def test_xcode_responses_is_registered_but_not_in_failover_order(monkeypatch, router_module):
    xcode = DummyProvider('xcode', 'gpt-4.1', [ok_response('xcode-ok')])
    xcode_backup = DummyProvider('xcode_backup', 'gpt-4.1-mini', [ok_response('backup-ok')])
    xcode_responses = DummyProvider('xcode_responses', 'gpt-4.1', [ok_response('responses-ok')])

    router = _build_router_with_registry(
        monkeypatch,
        router_module,
        {
            'xcode': lambda config: xcode,
            'xcode_responses': lambda config: xcode_responses,
            'xcode_backup': lambda config: xcode_backup,
        },
    )

    assert 'xcode_responses' in router.providers
    assert router.providers['xcode_responses'].name == 'xcode_responses'
    assert 'xcode_responses' not in router.failover_order
    assert router.failover_order == ['xcode', 'xcode_backup']


def test_provider_router_recovery_probe_restores_preferred_provider_default_model(monkeypatch, router_module):
    newshrimp = DummyProvider('newshrimp', 'kimi-k2.6', [ok_response('probe-ok'), ok_response('real-ok')])
    xcode = DummyProvider('xcode', 'gpt-4.1', [ok_response('xcode-ok')])

    router = _build_router_with_registry(
        monkeypatch,
        router_module,
        {
            'newshrimp': lambda config: newshrimp,
            'xcode': lambda config: xcode,
        },
        config=SimpleNamespace(
            xcode_api_key='xcode-key',
            newshrimp_api_key='newshrimp-key',
            newshrimp_2_api_key=None,
            newshrimp_3_api_key=None,
            aliyun_api_key=None,
            deepseek_api_key=None,
        ),
    )
    router._switch_provider('xcode')
    router._last_recovery_attempt = 0
    router._last_refresh_time = 10**12

    monkeypatch.setattr(router_module.time, 'time', lambda: 10**9)

    result = asyncio.run(router.chat(messages=[{'role': 'user', 'content': 'real-request'}]))

    assert result.content == 'real-ok'
    assert newshrimp.calls == 2
    assert xcode.calls == 0
    assert router.active_provider_name == 'newshrimp'
    assert router.get_default_model() == 'kimi-k2.6'
