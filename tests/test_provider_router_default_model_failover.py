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
        aixj_api_key='aixj-key',
        aixj_api_keys=[],
        codex_api_key='codex-key',
        gemini_api_key='gemini-key',
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
    aixj = DummyProvider('aixj', 'gpt-4.1', [ok_response('ok')])
    codex = DummyProvider('codex', 'gpt-4.1-mini', [ok_response('codex-ok')])

    router = _build_router_with_registry(
        monkeypatch,
        router_module,
        {
            'aixj': lambda config: aixj,
            'codex': lambda config: codex,
        },
    )

    assert router.active_provider_name == 'aixj'
    assert router.get_active_provider() is aixj
    assert router.get_default_model() == 'gpt-4.1'
    assert router.get_default_model() != 'gpt-5.4'


@pytest.mark.asyncio
async def test_provider_router_failover_switches_active_provider_and_default_model(monkeypatch, router_module):
    aixj = DummyProvider(
        'aixj',
        'gpt-4.1',
        [ProviderError(503, 'Service temporarily unavailable', error_type='http_error')],
    )
    codex = DummyProvider('codex', 'gpt-4.1-mini', [ok_response('ok-from-codex')])

    router = _build_router_with_registry(
        monkeypatch,
        router_module,
        {
            'aixj': lambda config: aixj,
            'codex': lambda config: codex,
        },
    )

    result = await router.chat(messages=[{'role': 'user', 'content': 'ping'}])

    assert result.content == 'ok-from-codex'
    assert aixj.calls == 1
    assert codex.calls == 1
    assert router.active_provider_name == 'codex'
    assert router.get_active_provider() is codex
    assert router.get_default_model() == 'gpt-4.1-mini'
    assert router.get_default_model() != 'gpt-5.4'




def test_aixj_responses_is_registered_but_not_in_failover_order(monkeypatch, router_module):
    aixj = DummyProvider('aixj', 'gpt-4.1', [ok_response('aixj-ok')])
    codex = DummyProvider('codex', 'gpt-4.1-mini', [ok_response('codex-ok')])
    gemini = DummyProvider('gemini', 'gemini-2.5-flash', [ok_response('gemini-ok')])

    aixj_responses_builder = router_module.provider_registry.get_builder('aixj_responses')

    router = _build_router_with_registry(
        monkeypatch,
        router_module,
        {
            'aixj': lambda config: aixj,
            'aixj_responses': lambda config: aixj_responses_builder(config),
            'codex': lambda config: codex,
            'gemini': lambda config: gemini,
        },
    )

    assert 'aixj_responses' in router.providers
    assert router.providers['aixj_responses'].provider_name == 'aixj_responses'
    assert 'aixj_responses' not in router.failover_order
    assert router.failover_order == ['aixj', 'codex', 'gemini']


@pytest.mark.asyncio
async def test_provider_router_recovery_probe_restores_preferred_provider_default_model(monkeypatch, router_module):


@pytest.mark.asyncio
async def test_provider_router_recovery_probe_restores_preferred_provider_default_model(monkeypatch, router_module):
    aixj = DummyProvider('aixj', 'gpt-4.1', [ok_response('probe-ok'), ok_response('real-ok')])
    codex = DummyProvider('codex', 'gpt-4.1-mini', [ok_response('codex-ok')])

    router = _build_router_with_registry(
        monkeypatch,
        router_module,
        {
            'aixj': lambda config: aixj,
            'codex': lambda config: codex,
        },
    )
    router._switch_provider('codex')
    router._last_recovery_attempt = 0
    router._last_refresh_time = 10**12

    monkeypatch.setattr(router_module.time, 'time', lambda: 10**9)

    result = await router.chat(messages=[{'role': 'user', 'content': 'real-request'}])

    assert result.content == 'real-ok'
    assert aixj.calls == 2
    assert codex.calls == 0
    assert router.active_provider_name == 'aixj'
    assert router.get_default_model() == 'gpt-4.1'
