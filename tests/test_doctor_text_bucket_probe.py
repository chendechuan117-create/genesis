from pathlib import Path
import re


def test_doctor_test_diff_has_distinguishable_text_buckets():
    text = Path("scripts/doctor.sh").read_text(encoding="utf-8")
    required = {
        "no_matching_tests": r"No test files found for diff changes",
        "collection_skipped": r"Skipping broken test files",
    }
    for name, pattern in required.items():
        assert re.search(pattern, text), f"missing text bucket: {name}"

    cmd_start = text.index("cmd_test_diff() {")
    cmd_end = text.index("cmd_diff_status() {")
    cmd_body = text[cmd_start:cmd_end]

    assert cmd_body.count("return 0") >= 2, "expected multiple rc=0 success buckets in cmd_test_diff"
    assert "No test files found for diff changes" in cmd_body
    assert "Skipping broken test files" in cmd_body
