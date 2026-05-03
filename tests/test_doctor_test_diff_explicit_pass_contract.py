import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUTO_MODE = ROOT / 'genesis' / 'auto_mode.py'
DOCTOR = ROOT / 'scripts' / 'doctor.sh'


def test_auto_mode_classifies_test_diff_evidence():
    text = AUTO_MODE.read_text(encoding='utf-8')
    assert 'test_ok, test_output = await _run_doctor_sync_command("test-diff", timeout_secs=180)' in text
    assert 'is_no_tests' in text
    assert 'is_collection_failed' in text
    assert 'is_unverified' in text
    # Must NOT treat NO_TESTS_FOUND as passing
    assert 'passing by default' not in text


def test_doctor_test_diff_returns_no_tests_found_when_no_coverage():
    proc = subprocess.run(
        [str(DOCTOR), 'test-diff'],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=240,
        check=False,
    )
    output = proc.stdout
    # Either NO_TESTS_FOUND (exit 3) or preflight blocked (exit 2) —
    # both are "unverified" not "passing by default"
    has_no_tests = 'NO_TESTS_FOUND' in output
    has_preflight = 'preflight' in output.lower()
    assert has_no_tests or has_preflight, output
    # Must NOT contain old "passing by default" messages
    assert 'passing by default' not in output
    assert 'Skipping broken test files' not in output
