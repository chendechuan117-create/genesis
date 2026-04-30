from pathlib import Path


DOCTOR = Path(__file__).resolve().parent.parent / "scripts" / "doctor.sh"


def _cmd_run_body() -> str:
    text = DOCTOR.read_text(encoding="utf-8")
    start = text.index("cmd_run() {")
    end = text.index("cmd_python() {")
    return text[start:end]


def test_doctor_run_has_bounded_job_lifecycle():
    body = _cmd_run_body()

    assert "DOCTOR_RUN_TIMEOUT_SECS" in body
    assert "DOCTOR_RUN_KILL_AFTER_SECS" in body
    assert "DOCTOR_RUN_JOB_ID" in body
    assert "setsid bash" in body
    assert "deadline=$((SECONDS + timeout_secs))" in body
    assert "exit 124" in body


def test_doctor_run_kills_process_group_and_avoids_fixed_tmp_script():
    body = _cmd_run_body()

    assert 'kill -TERM -- "-$child"' in body
    assert 'kill -KILL -- "-$child"' in body
    assert 'script_path="/tmp/${job_id}.sh"' in body
    assert "/tmp/_doctor_run.sh" not in body
