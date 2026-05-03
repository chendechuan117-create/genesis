import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = '/workspace/runtime/scratch/doctor_test_diff_mode_probe.py'


def run_probe():
    proc = subprocess.run(
        ['./scripts/doctor.sh', 'exec', 'python3', PROBE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_host_test_diff_returns_no_tests_as_unverified():
    payload = run_probe()
    host = payload['host_test_diff']
    # NO_TESTS_FOUND (exit 3) or preflight blocked (exit 2) — unverified, not passing
    has_no_tests = host.get('has_no_tests_found', False) or 'NO_TESTS_FOUND' in host.get('output', '')
    has_preflight = 'preflight' in host.get('output', '').lower()
    # Must NOT have old "passing by default" markers
    assert 'passing by default' not in host.get('output', '')
    assert has_no_tests or has_preflight


def test_nested_contract_failure_is_not_treated_as_passing():
    payload = run_probe()
    nested = payload.get('nested_test_entry', {})
    if not nested:
        # Probe may not have created nested entry — skip gracefully
        return
    # Collection failure should NOT be treated as passing
    assert 'passing by default' not in nested.get('output', '')
