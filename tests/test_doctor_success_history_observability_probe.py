from pathlib import Path

AUTO_MODE = Path('/workspace/genesis/auto_mode.py')


def _read() -> str:
    return AUTO_MODE.read_text(encoding='utf-8')


def test_success_history_record_is_generic_and_lacks_reason_trace_fields():
    text = _read()
    assert '"status": "success"' in text
    success_block = text.rsplit('self.apply_history.append({', 1)[1].split('})', 1)[0]
    assert '"status": "success"' in success_block
    assert 'reason_code' not in success_block
    assert 'test_output' not in success_block
    assert 'NO_MATCHING_TESTS' not in success_block
    assert 'COLLECTION_SKIPPED' not in success_block


def test_runtime_message_layer_can_split_but_history_layer_would_recollapse_to_success_bucket():
    def classify_reason_code(output: str) -> str:
        if 'No test files found for diff changes' in output:
            return 'NO_MATCHING_TESTS'
        if 'Skipping broken test files' in output:
            return 'COLLECTION_SKIPPED'
        return 'UNKNOWN'

    def success_history_record(output: str) -> dict:
        return {'status': 'success'}

    outputs = [
        '🧪 No test files found for diff changes — passing by default',
        '⚠️ Smoke test: pytest collection failed for discovered tests\n🧪 Skipping broken test files — passing by default',
        'ok',
    ]
    reason_codes = [classify_reason_code(o) for o in outputs]
    assert reason_codes == ['NO_MATCHING_TESTS', 'COLLECTION_SKIPPED', 'UNKNOWN']

    history_statuses = [success_history_record(o)['status'] for o in outputs]
    assert history_statuses == ['success', 'success', 'success']
    assert len(set(reason_codes)) == 3
    assert len(set(history_statuses)) == 1


def test_minimal_traceable_success_schema_candidate_fits_existing_success_shape():
    def build_success_record(*, reason_code: str, raw_output: str) -> dict:
        return {
            'status': 'success',
            'test_reason_code': reason_code,
            'test_output_excerpt': raw_output[-200:].replace('\n', ' ').strip(),
        }

    record = build_success_record(
        reason_code='NO_MATCHING_TESTS',
        raw_output='🧪 No test files found for diff changes — passing by default',
    )
    assert record['status'] == 'success'
    assert record['test_reason_code'] == 'NO_MATCHING_TESTS'
    assert 'No test files found for diff changes' in record['test_output_excerpt']
