from pathlib import Path

p = Path('/workspace/genesis/auto_mode.py')
text = p.read_text(encoding='utf-8')
anchor = '        test_ok, test_output = await _run_doctor_sync_command("test-diff", timeout_secs=180)\n'
if anchor not in text:
    raise SystemExit('anchor not found')
insert = anchor + '        test_reason_code = "TESTS_PASSED"\n        if "No test files found for diff changes" in test_output:\n            test_reason_code = "NO_MATCHING_TESTS"\n        elif "Skipping broken test files" in test_output:\n            test_reason_code = "COLLECTION_SKIPPED"\n'
text = text.replace(anchor, insert, 1)
old = '        self.apply_history.append({\n            "round": round_num,\n            "status": "success",\n            "timestamp": _time_module.strftime("%Y-%m-%d %H:%M:%S"),\n            "rollback_commit": rollback_commit,\n            "applied_commit": applied_commit,\n        })\n'
new = '        self.apply_history.append({\n            "round": round_num,\n            "status": "success",\n            "test_reason_code": test_reason_code,\n            "timestamp": _time_module.strftime("%Y-%m-%d %H:%M:%S"),\n            "rollback_commit": rollback_commit,\n            "applied_commit": applied_commit,\n        })\n'
if old not in text:
    raise SystemExit('success history block not found')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

p = Path('/workspace/tests/test_doctor_check_round_apply_history_semantics_probe.py')
text = p.read_text(encoding='utf-8')
old = '''def test_apply_history_schema_today_has_no_reason_code_field_on_success_records():
    text = AUTO_MODE_PATH.read_text(encoding='utf-8')
    success_window = text.rsplit('self.apply_history.append({', 1)[1].split('})', 1)[0]
    assert '"status": "success"' in success_window
    assert 'rollback_commit' in success_window
    assert 'reason_code' not in success_window
    assert 'test_output' not in success_window
    assert 'NO_MATCHING_TESTS' not in success_window
    assert 'COLLECTION_SKIPPED' not in success_window
'''
new = '''def test_apply_history_success_records_now_distinguish_test_diff_success_buckets():
    text = AUTO_MODE_PATH.read_text(encoding='utf-8')
    success_window = text.rsplit('self.apply_history.append({', 1)[1].split('})', 1)[0]
    assert '"status": "success"' in success_window
    assert 'rollback_commit' in success_window
    assert '"test_reason_code": test_reason_code' in success_window


def test_success_apply_history_payload_contract_can_distinguish_live_and_test_diff_successes():
    def build_success_history(test_output: str) -> dict:
        test_reason_code = 'TESTS_PASSED'
        if 'No test files found for diff changes' in test_output:
            test_reason_code = 'NO_MATCHING_TESTS'
        elif 'Skipping broken test files' in test_output:
            test_reason_code = 'COLLECTION_SKIPPED'
        return {
            'status': 'success',
            'test_reason_code': test_reason_code,
        }

    plain = build_success_history('================== 3 passed in 0.12s ==================')
    no_matching = build_success_history(NO_MATCHING)
    collection_skipped = build_success_history(COLLECTION_SKIPPED)

    assert plain['test_reason_code'] == 'TESTS_PASSED'
    assert no_matching['test_reason_code'] == 'NO_MATCHING_TESTS'
    assert collection_skipped['test_reason_code'] == 'COLLECTION_SKIPPED'
'''
if old not in text:
    raise SystemExit('target test block not found')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

print('patches applied')
