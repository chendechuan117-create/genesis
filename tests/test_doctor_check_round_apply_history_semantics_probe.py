from pathlib import Path

AUTO_MODE_PATH = Path('/workspace/genesis/auto_mode.py')
NO_MATCHING = '🧪 No test files found for diff changes — passing by default'
COLLECTION_SKIPPED = '⚠️ Smoke test: pytest collection failed for discovered tests\n🧪 Skipping broken test files — passing by default'


def _extract_check_round_window() -> str:
    text = AUTO_MODE_PATH.read_text(encoding='utf-8')
    start = text.index('        # 1. Run diff-scoped tests in sandbox (only test files related to current changes)')
    end = text.index('        # 4. Write restart marker + record history + clear cooling state')
    return text[start:end]


def classify_reason_code(output: str) -> str:
    if 'No test files found for diff changes' in output:
        return 'NO_MATCHING_TESTS'
    if 'Skipping broken test files' in output:
        return 'COLLECTION_SKIPPED'
    return 'UNKNOWN'


def success_message_for(output: str) -> str:
    code = classify_reason_code(output)
    if code == 'NO_MATCHING_TESTS':
        return '🧬 ✅ 差分范围无匹配测试（NO_MATCHING_TESTS）'
    if code == 'COLLECTION_SKIPPED':
        return '🧬 ⚠️ 测试收集异常，已跳过问题用例（COLLECTION_SKIPPED）'
    return '🧬 ✅ 测试通过'


def test_message_contract_patch_does_not_require_new_apply_history_statuses():
    window = _extract_check_round_window()
    assert 'self.apply_history.append({' in window
    assert window.count('self.apply_history.append({') == 2
    assert '"status": "test_failed"' in window
    assert '"status": "apply_failed"' in window
    assert '"status": "success"' not in window


def test_success_message_customization_still_routes_to_same_success_apply_history_shape():
    outputs = {
        'plain_pass': 'all selected tests passed',
        'no_matching_tests': NO_MATCHING,
        'collection_skipped': COLLECTION_SKIPPED,
    }
    rendered = {k: success_message_for(v) for k, v in outputs.items()}
    assert rendered['plain_pass'] == '🧬 ✅ 测试通过'
    assert rendered['no_matching_tests'] != rendered['plain_pass']
    assert rendered['collection_skipped'] != rendered['plain_pass']
    assert rendered['no_matching_tests'].endswith('（NO_MATCHING_TESTS）')
    assert rendered['collection_skipped'].endswith('（COLLECTION_SKIPPED）')


def test_apply_history_schema_today_has_no_reason_code_field_on_success_records():
    text = AUTO_MODE_PATH.read_text(encoding='utf-8')
    success_window = text.rsplit('self.apply_history.append({', 1)[1].split('})', 1)[0]
    assert '"status": "success"' in success_window
    assert 'rollback_commit' in success_window
    assert 'reason_code' not in success_window
    assert 'test_output' not in success_window
    assert 'NO_MATCHING_TESTS' not in success_window
    assert 'COLLECTION_SKIPPED' not in success_window
