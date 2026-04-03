import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from genesis.tools import url_tool
from genesis.tools.url_tool import ReadUrlTool


class DummyPage:
    def __init__(self, close_error=None):
        self.close_calls = 0
        self.close_error = close_error

    async def goto(self, url, wait_until="domcontentloaded", timeout=30000):
        raise RuntimeError("goto boom")

    async def content(self):
        return ""

    async def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class DummyBrowser:
    def __init__(self, page):
        self.page = page
        self.new_page_calls = 0

    async def new_page(self):
        self.new_page_calls += 1
        return self.page


def test_playwright_fetch_closes_page_on_goto_failure():
    page = DummyPage()
    browser = DummyBrowser(page)

    async def run_case():
        with patch.object(url_tool, "_get_playwright_browser", return_value=browser):
            return await ReadUrlTool._fetch_via_playwright("https://example.com")

    result = asyncio.run(run_case())

    assert result.startswith("Error: Playwright failed: goto boom")
    assert browser.new_page_calls == 1
    assert page.close_calls == 1


def test_playwright_fetch_close_error_does_not_mask_primary_error():
    page = DummyPage(close_error=RuntimeError("close boom"))
    browser = DummyBrowser(page)

    async def run_case():
        with patch.object(url_tool, "_get_playwright_browser", return_value=browser):
            return await ReadUrlTool._fetch_via_playwright("https://example.com")

    result = asyncio.run(run_case())

    assert result == "Error: Playwright failed: goto boom"
    assert page.close_calls == 1
