from pathlib import Path

AUTO_MODE = Path('/workspace/genesis/auto_mode.py')


def _slice_between(text: str, start: str, end: str) -> str:
    s = text.index(start)
    e = text.index(end, s)
    return text[s:e]


def test_check_round_test_diff_branch_only_has_one_live_boolean_gate_and_one_success_message_after_it():
    text = AUTO_MODE.read_text(encoding='utf-8')
    branch = _slice_between(
        text,
        'test_ok, test_output = await _run_doctor_sync_command("test-diff", timeout_secs=180)',
        'apply_ok, apply_output = await _run_doctor_sync_command("auto-apply", timeout_secs=60)',
    )

    assert 'if not test_ok:' in branch
    assert '沙箱测试失败，放弃本次应用' in branch
    assert '✅ 测试通过' in branch

    # 当前成功路径只有一个统一成功文案，没有 reason code / bucket 级分流。
    assert branch.count('✅ 测试通过') == 1
    assert 'NO_MATCHING_TESTS' not in branch
    assert 'COLLECTION_SKIPPED' not in branch
    assert 'UNKNOWN' not in branch


def test_raw_test_output_is_still_live_inside_check_round_failure_window_and_not_consumed_before_success_message():
    text = AUTO_MODE.read_text(encoding='utf-8')
    branch = _slice_between(
        text,
        'test_ok, test_output = await _run_doctor_sync_command("test-diff", timeout_secs=180)',
        'apply_ok, apply_output = await _run_doctor_sync_command("auto-apply", timeout_secs=60)',
    )

    # 最小插入点事实：raw output 变量仍在当前分支存活，且成功消息发送前尚未被解析。
    assert 'test_output[-500:]' in branch
    assert branch.index('test_ok, test_output = await _run_doctor_sync_command("test-diff", timeout_secs=180)') < branch.index('✅ 测试通过')
    assert 'test_output' in branch
