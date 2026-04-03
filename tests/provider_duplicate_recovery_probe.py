import asyncio
from types import SimpleNamespace

import pytest

from genesis.core.base import LLMResponse
from genesis.core.provider_manager import ProviderRouter


class ProviderError(Exception):
    def __init__(self, status_code, message, error_type=None, category=None, already_retried=False):
        super().__init__(f"{status_code} {message} [{error_type or category or 'error'}]")
        self.status_code = status_code
        self.message = message
        self.error_type = error_type
        self.category = category
        self.already_retried = already_retried


class DummyProvider:
    def __init__(self, name, outcomes):
        self.name = name
        self.outcomes = list(outcomes)
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_default_model(self):
        return f"{self.name}-model"


def ok_response(text):
    return LLMResponse(content=text, tool_calls=[], finish_reason="stop", input_tokens=1, output_tokens=1, total_tokens=2)


def build_router(providers, active="aixj"):
    router = ProviderRouter.__new__(ProviderRouter)
    router.config = SimpleNamespace()
    router.providers = providers
    router.active_provider_name = active
    router.active_provider = providers[active]
    router._preferred_provider_name = active
    router._failover_time = 0
    router._last_recovery_attempt = 0
    router._last_refresh_time = 10**12
    router._provider_limiters = {}
    router.failover_order = list(providers.keys())
    return router


@pytest.mark.asyncio
async def test_failover_on_provider_error_without_duplicate_retry():
    aixj = DummyProvider(
        "aixj",
        [ProviderError(503, "Service temporarily unavailable", error_type="http_error", category="service_unavailable", already_retried=True)],
    )
    codex = DummyProvider("codex", [ok_response("ok-from-codex")])
    router = build_router({"aixj": aixj, "codex": codex})

    result = await router.chat(messages=[{"role": "user", "content": "ping"}])

    assert result.content == "ok-from-codex"
    assert aixj.calls == 1
    assert codex.calls == 1
    assert router.active_provider_name == "codex"


@pytest.mark.asyncio
async def test_rate_limit_error_failsover_without_duplicate_retry(monkeypatch):
    rate_limit_err = ProviderError(
        429,
        "Concurrency limit exceeded",
        error_type="rate_limit_error",
        category="rate_limit",
        already_retried=True,
    )
    aixj = DummyProvider("aixj", [rate_limit_err])
    codex = DummyProvider("codex", [ok_response("ok-after-429-failover")])
    router = build_router({"aixj": aixj, "codex": codex})

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    result = await router.chat(messages=[{"role": "user", "content": "ping"}])

    assert result.content == "ok-after-429-failover"
    assert aixj.calls == 1
    assert codex.calls == 1
    assert sleep_calls == []
    assert router.active_provider_name == "codex"
