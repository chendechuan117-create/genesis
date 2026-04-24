import importlib.util
import pathlib

# 依赖门控：在导入 pytest 之前检查可选依赖
if importlib.util.find_spec("requests") is None:
    # 缺少可选依赖时，跳过整个测试模块
    import sys
    # 创建一个虚拟的 pytest 模块来设置 pytestmark
    pytest_stub = type(sys)('pytest_stub')
    pytest_stub.mark = type(sys)('mark')
    pytest_stub.mark.skipif = lambda *a, **k: lambda f: f
    sys.modules['pytest'] = pytest_stub
    pytest = pytest_stub
else:
    import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("requests") is None,
    reason="optional dependency missing: requests"
)

MODULE_PATH = pathlib.Path('/workspace/tests/test_direct_ip.py')


def load_module(monkeypatch):
    calls = []

    class DummyResponse:
        status_code = 200
        text = 'ok'

        def json(self):
            return {'errcode': 0}

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return DummyResponse()

    monkeypatch.setattr('requests.get', fake_get)
    spec = importlib.util.spec_from_file_location('test_direct_ip_under_test', MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_direct_ip_does_not_force_localhost_proxy_by_default(monkeypatch):
    _, calls = load_module(monkeypatch)
    assert len(calls) >= 2
    second = calls[1]
    assert second.get('proxies') != {
        'http': 'http://127.0.0.1:20172',
        'https': 'http://127.0.0.1:20172',
    }
