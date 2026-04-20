from pathlib import Path

AUTO_MODE = Path('/workspace/genesis/auto_mode.py')
NO_MATCHING_TESTS_MARKER = 'No test files found for diff changes'
COLLECTION_SKIPPED_MARKER = 'Skipping broken test files'
UNKNOWN_REASON_CODE = 'UNKNOWN'


def _slice_between(text: str, start: str, end: str) -> str:
    s = text.index(start)
    e = text.index(end, s)
    return text[s:e]


def classify_reason_code(output: str) -> str:
    if NO_MATCHING_TESTS_MARKER in output:
        return 'NO_MATCHING_TESTS'
    if COLLECTION_SKIPPED_MARKER in output:
        return 'COLLECTION_SKIPPED'
    return UNKNOWN_REASON_CODE


def render_success_message(output: str) -> str:
    reason_code = classify_reason_code(output)
    if reason_code == 'NO_MATCHING_TESTS':
        return '🧬 ✅ 差分范围无匹配测试（NO_MATCHING_TESTS）'
    if reason_code == 'COLLECTION_SKIPPED':
        return '🧬 ⚠️ 测试收集异常，已跳过问题用例（COLLECTION_SKIPPED）'
    return '🧬 ✅ 测试通过'


def test_minimal_success_message_contract_distinguishes_false_green_buckets_from_true_pass() -> None:
    assert render_success_message(NO_MATCHING_TESTS_MARKER) == '🧬 ✅ 差分范围无匹配测试（NO_MATCHING_TESTS）'
    assert render_success_message(COLLECTION_SKIPPED_MARKER) == '🧬 ⚠️ 测试收集异常，已跳过问题用例（COLLECTION_SKIPPED）'
    assert render_success_message('================== 3 passed in 0.12s ==================') == '🧬 ✅ 测试通过'
    assert render_success_message('some future success-like text drift') == '🧬 ✅ 测试通过'


def test_live_check_round_still_uses_single_generic_success_message_so_contract_is_not_yet_adopted() -> None:
    text = AUTO_MODE.read_text(encoding='utf-8')
    branch = _slice_between(
        text,
        'test_ok, test_output = await _run_doctor_sync_command("test-diff", timeout_secs=180)',
        'apply_ok, apply_output = await _run_doctor_sync_command("auto-apply", timeout_secs=60)',
    )

    assert 'await channel.send("🧬 ✅ 测试通过")' in branch
    assert 'NO_MATCHING_TESTS' not in branch
    assert 'COLLECTION_SKIPPED' not in branch
    assert '差分范围无匹配测试' not in branch
    assert '测试收集异常，已跳过问题用例' not in branch
