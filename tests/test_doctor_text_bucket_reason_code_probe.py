from pathlib import Path


NO_MATCHING_TESTS_MARKER = "No test files found for diff changes"
COLLECTION_SKIPPED_MARKER = "Skipping broken test files"
UNKNOWN_REASON_CODE = "UNKNOWN"


def _cmd_test_diff_body() -> str:
    text = Path("/workspace/scripts/doctor.sh").read_text(encoding="utf-8")
    start = text.index("cmd_test_diff() {")
    end = text.index("cmd_diff_status() {")
    return text[start:end]


def classify_reason_code(output: str) -> str:
    if NO_MATCHING_TESTS_MARKER in output:
        return "NO_MATCHING_TESTS"
    if COLLECTION_SKIPPED_MARKER in output:
        return "COLLECTION_SKIPPED"
    return UNKNOWN_REASON_CODE


def test_reason_code_parser_is_single_valued_and_has_unknown_fallback() -> None:
    body = _cmd_test_diff_body()
    combined = COLLECTION_SKIPPED_MARKER + "\n...\n" + NO_MATCHING_TESTS_MARKER

    assert classify_reason_code(body) == "NO_MATCHING_TESTS"
    assert classify_reason_code(COLLECTION_SKIPPED_MARKER) == "COLLECTION_SKIPPED"
    assert classify_reason_code(combined) == "NO_MATCHING_TESTS", "precedence must be stable"
    assert classify_reason_code("totally unknown bucket") == UNKNOWN_REASON_CODE

    assert NO_MATCHING_TESTS_MARKER in body
    assert COLLECTION_SKIPPED_MARKER in body
