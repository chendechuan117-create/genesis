import subprocess
import time

import pytest

from genesis.core.jobs import JobManager


def test_health_check_ping_failure_does_not_mark_network_failed(monkeypatch):
    manager = JobManager()

    def fake_get_system_info():
        return {"mem_usage_pct": 12.5}

    def fake_run(cmd, capture_output, text, timeout):
        assert cmd == ["ps", "aux"]

        class DummyCompletedProcess:
            stdout = ""

        return DummyCompletedProcess()

    monkeypatch.setattr(JobManager, "_get_system_info", staticmethod(fake_get_system_info))
    monkeypatch.setattr(subprocess, "run", fake_run)

    report = manager.health_check()

    assert report["jobs_running"] == 0
    assert report["jobs_total"] == 0
    assert report["system"]["mem_usage_pct"] == 12.5
    assert "network_failed" not in report
    assert report["zombie_check"]["zombie_count"] == 0


def test_health_check_network_probe_timeout_is_degraded_not_global_block(monkeypatch):
    manager = JobManager()

    def fake_get_system_info():
        return {"mem_usage_pct": 1.0}

    def fake_check_zombies():
        return {"genesis_processes": [], "zombie_count": 0}

    def fake_probe_https(url: str = "https://example.com", timeout: int = 5):
        time.sleep(0.01)
        return {
            "url": url,
            "ok": False,
            "status": "timeout",
            "timeout_seconds": timeout,
            "error": "simulated timeout",
        }

    monkeypatch.setattr(JobManager, "_get_system_info", staticmethod(fake_get_system_info))
    monkeypatch.setattr(JobManager, "_check_zombies", staticmethod(fake_check_zombies))
    monkeypatch.setattr(JobManager, "_probe_https", staticmethod(fake_probe_https))

    started = time.perf_counter()
    report = manager.health_check()
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert report["network_probe"]["status"] == "timeout"
    assert report["network_probe"]["ok"] is False
    assert report["system"]["mem_usage_pct"] == 1.0
    assert report["zombie_check"]["zombie_count"] == 0


@pytest.mark.skipif(__import__("importlib").util.find_spec("requests") is None, reason="requests not installed")
def test_probe_https_sets_explicit_timeout(monkeypatch):
    import requests

    seen = {}

    class DummyResponse:
        status_code = 200

    def fake_get(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    result = JobManager._probe_https()

    assert seen["url"] == "https://example.com"
    assert seen["timeout"] == 5
    assert result["status"] == "ok"
    assert result["http_status"] == 200


@pytest.mark.skipif(__import__("importlib").util.find_spec("requests") is None, reason="requests not installed")
def test_probe_https_request_exception_returns_error_status(monkeypatch):
    import requests

    def fake_get(url, timeout):
        raise requests.RequestException("simulated request failure")

    monkeypatch.setattr(requests, "get", fake_get)

    result = JobManager._probe_https()

    assert result["url"] == "https://example.com"
    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"] == "simulated request failure"



def test_shell_health_check_surfaces_top_level_aggregate_fields(monkeypatch):
    from genesis.tools.shell_tool import ShellTool

    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 1,
                "jobs_total": 2,
                "status": "degraded",
                "overall": "warning",
                "summary": "network probe degraded but jobs healthy",
                "warnings": ["probe timeout", "disk nearing threshold"],
                "issues": ["network reachability degraded"],
                "system": {"mem_usage_pct": 12.5, "mem_available_mb": 2048},
                "network_probe": {"status": "timeout", "summary": "timed out without exception", "ok": False},
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Status: degraded" in output
    assert "Overall: warning" in output
    assert "Summary: network probe degraded but jobs healthy" in output
    assert "Warnings: probe timeout; disk nearing threshold" in output
    assert "Issues: network reachability degraded" in output


def test_shell_health_check_network_probe_summary_without_error_is_stable(monkeypatch):
    from genesis.tools.shell_tool import ShellTool

    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "system": {},
                "network_probe": {
                    "status": "degraded",
                    "summary": "TLS handshake intermittently slow",
                    "ok": False,
                },
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Network probe: degraded" in output
    assert "Summary: TLS handshake intermittently slow" in output
    assert "Error:" not in output


def test_shell_tool_health_check_uses_network_probe_summary_when_error_missing():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "system": {"mem_usage_pct": 7.0, "mem_available_mb": 1024},
                "network_probe": {
                    "status": "degraded",
                    "summary": "partial probe result",
                    "http_status": 204,
                    "url": "https://example.com/health",
                },
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Network probe: degraded" in output
    assert "Summary: partial probe result" in output
    assert "HTTP status: 204" in output
    assert "URL: https://example.com/health" in output


def test_shell_health_check_network_probe_ok_without_status_does_not_render_unknown():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "system": {},
                "network_probe": {
                    "ok": True,
                    "summary": "https probe succeeded",
                },
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Network probe: ok" in output
    assert "Network probe: unknown" not in output
    assert "Summary: https probe succeeded" in output




def test_shell_health_check_non_dict_network_probe_is_tolerated():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "system": {},
                "network_probe": "probe unavailable",
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Network probe:" in output
    assert "probe unavailable" in output or "unknown" in output
    assert "Genesis instances: 0" in output


def test_shell_health_check_list_network_probe_is_tolerated():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "system": {},
                "network_probe": ["offline", 503],
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Network probe:" in output
    assert "offline" in output or "unknown" in output
    assert "Genesis instances: 0" in output

def test_shell_health_check_load_line_tolerates_missing_5m_and_15m():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "system": {
                    "load_1m": 0.21,
                },
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Load: 0.21" in output
    assert "Genesis instances: 0" in output




def test_shell_tool_health_check_zombie_truthy_non_dict_does_not_crash():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "system": {},
                "zombie_check": "oops",
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Jobs: 0 running / 0 total" in output
    assert "Genesis instances: 0" in output
    assert "oops" in output or "unknown" in output

def test_shell_tool_health_check_system_truthy_non_dict_does_not_crash():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "system": "degraded raw text",
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Jobs: 0 running / 0 total" in output
    assert "Genesis instances: 0" in output


def test_shell_tool_health_check_warnings_dict_is_rendered_stably_with_json_ordering():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "warnings": {"b": 2, "a": 1},
                "issues": None,
                "system": {},
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert 'Warnings: {"a": 1, "b": 2}' in output
    assert "Warnings: {'b': 2, 'a': 1}" not in output



def test_shell_tool_health_check_warnings_mixed_nested_structures_are_rendered_stably():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "warnings": ["x", {"b": 2, "a": 1}, ["y", {"c": 3}]],
                "issues": None,
                "system": {},
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert 'Warnings: x; {"a": 1, "b": 2}; ["y", {"c": 3}]' in output
    assert "['y', {'c': 3}]" not in output


def test_shell_tool_health_check_issues_mixed_nested_structures_are_rendered_stably():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "warnings": None,
                "issues": ["x", {"b": 2, "a": 1}, ("y", {"c": 3})],
                "system": {},
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert 'Issues: x; {"a": 1, "b": 2}; ["y", {"c": 3}]' in output
    assert "('y', {'c': 3})" not in output



def test_shell_tool_health_check_issues_bytearray_is_rendered_as_text_not_byte_values():
    class DummyJobManager:
        def health_check(self):
            return {
                "jobs_running": 0,
                "jobs_total": 0,
                "warnings": None,
                "issues": bytearray(b"issue:\xff"),
                "system": {},
                "zombie_check": {"genesis_processes": [], "zombie_count": 0},
            }

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert "Issues: issue:�" in output
    assert "Issues: 105; 115; 115; 117; 101; 58; 255" not in output

def test_shell_tool_health_check_non_dict_report_returns_invalid_report_message():
    class DummyJobManager:
        def health_check(self):
            return 'not a dict'

        def cleanup_stale(self):
            return 0

    from genesis.tools.shell_tool import ShellTool

    tool = ShellTool(job_manager=DummyJobManager())

    output = tool.health_check()

    assert output == '=== Genesis Health Check ===\nReport: invalid health report'
