import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tests" / "final_ip_test.py"
spec = importlib.util.spec_from_file_location("final_ip_test", MODULE_PATH)
final_ip_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final_ip_test)


def test_build_proxy_config_without_proxy_clears_env(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://should-clear")
    monkeypatch.setenv("HTTP_PROXY", "http://should-clear")

    proxies, resolved = final_ip_test.build_proxy_config(use_proxy=False)

    assert proxies == {}
    assert resolved is None
    assert "http_proxy" not in final_ip_test.os.environ
    assert "HTTP_PROXY" not in final_ip_test.os.environ


def test_build_proxy_config_uses_environment_proxy(monkeypatch):
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://env-proxy:8888")

    proxies, resolved = final_ip_test.build_proxy_config(use_proxy=True)

    assert resolved == "http://env-proxy:8888"
    assert proxies == {
        "http": "http://env-proxy:8888",
        "https": "http://env-proxy:8888",
    }
    assert final_ip_test.os.environ["http_proxy"] == "http://env-proxy:8888"
    assert final_ip_test.os.environ["https_proxy"] == "http://env-proxy:8888"


def test_build_proxy_config_without_env_returns_skip_signal(monkeypatch):
    for key in final_ip_test.PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)

    proxies, resolved = final_ip_test.build_proxy_config(use_proxy=True)

    assert proxies is None
    assert resolved is None


def test_extract_ip_from_errmsg_handles_missing_comma():
    errmsg = "not allow to access from ip: 203.0.113.7 hint: [abc]"
    assert final_ip_test.extract_ip_from_errmsg(errmsg) == "203.0.113.7 hint: [abc]"


def test_test_with_proxy_settings_skips_when_proxy_missing(monkeypatch, capsys):
    for key in final_ip_test.PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)

    result = final_ip_test.test_with_proxy_settings(use_proxy=True)
    out = capsys.readouterr().out

    assert result == {"skipped": True, "reason": "proxy_not_configured"}
    assert "跳过代理测试" in out
