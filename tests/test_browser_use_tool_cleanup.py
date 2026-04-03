import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from genesis.tools.browser_use_tool import BrowserUseTool


class DummyBrowser:
    def __init__(self):
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class DummyAgent:
    def __init__(self, *args, **kwargs):
        pass

    async def run(self, max_steps: int):
        raise RuntimeError('boom')


class DummyBrowserConfig:
    def __init__(self, **kwargs):
        self.proxy = None


async def _fake_wait_for(awaitable, timeout):
    return await awaitable


class DummyLLM:
    pass


def test_browser_use_closes_browser_on_agent_failure():
    tool = BrowserUseTool()
    browser = DummyBrowser()
    fake_module = types.SimpleNamespace(
        Agent=DummyAgent,
        Browser=lambda config=None: browser,
        BrowserConfig=DummyBrowserConfig,
    )

    with patch.object(BrowserUseTool, '_get_llm', return_value=DummyLLM()), \
         patch('genesis.tools.browser_use_tool.asyncio.wait_for', _fake_wait_for), \
         patch.dict(sys.modules, {'browser_use': fake_module}):
        result = asyncio.run(tool.execute(task='failing task'))

    assert result.startswith('Error: browser-use 执行失败')
    assert browser.close_calls == 1
