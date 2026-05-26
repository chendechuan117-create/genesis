import sqlite3
import sys
import types


def test_auto_signals_hide_arena_win_loss_counts(tmp_path, monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / ".genesis" / "workshop_v4.sqlite"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE knowledge_nodes ("
            "node_id TEXT PRIMARY KEY, title TEXT, type TEXT, usage_success_count INTEGER DEFAULT 0, "
            "usage_fail_count INTEGER DEFAULT 0, usage_count INTEGER DEFAULT 0, ablation_active INTEGER DEFAULT 0, "
            "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE node_edges (source_id TEXT, target_id TEXT, relation TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE void_tasks (void_id TEXT PRIMARY KEY, query TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO knowledge_nodes "
            "(node_id, title, type, usage_success_count, usage_fail_count, usage_count, ablation_active, created_at) "
            "VALUES ('AUTO_FAILING_NODE', 'failing but useful', 'LESSON', 1, 4, 5, 0, datetime('now', '-2 hours'))"
        )
        conn.commit()
    finally:
        conn.close()

    from genesis.auto_mode import _get_auto_signals

    output = _get_auto_signals()
    assert "AUTO_FAILING_NODE" in output
    assert "实践表现不稳定" in output
    assert "1W/4L" not in output
    assert "4L" not in output
    assert "usage_fail_count" not in output


def test_auto_knowledge_state_is_not_destructively_trimmed(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _build_auto_knowledge_state

    long_observation = "本轮确认 " + "O" * 700
    frontier_state = {
        "candidate_issue": "候选问题 " + "I" * 500,
        "observations": [long_observation],
        "carry_warnings": ["警告 " + "W" * 650],
        "next_checks": [f"check-{idx}" for idx in range(8)],
    }
    raw_state = {
        "verified_facts": [f"raw-fact-{idx}" for idx in range(6)],
        "failed_attempts": ["raw-failure " + "F" * 600],
        "next_checks": ["raw-check " + "C" * 500],
    }
    state = _build_auto_knowledge_state(frontier_state, [], raw_state=raw_state)
    assert state["issue"].endswith("I" * 500)
    assert state["verified_facts"][0] == long_observation
    assert len(state["verified_facts"]) == 7
    assert state["failed_attempts"][0].endswith("W" * 650)
    assert state["failed_attempts"][1].endswith("F" * 600)
    assert len(state["next_checks"]) == 9


def test_round_topology_classifies_anchored_then_wandering(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _build_round_topology

    events = [
        {"t": 1.0, "type": "llm_call_start", "phase": "GP_PHASE"},
        {"t": 2.0, "type": "tool_result", "name": "record_point", "result_preview": "✅ POINT [P_A] created", "iteration": 0},
        {"t": 3.0, "type": "tool_result", "name": "record_line", "result_preview": "✅ LINE: P_A --[RELATED_TO]--> P_BASE", "iteration": 0},
        {"t": 4.0, "type": "tool_result", "name": "search_knowledge_nodes", "result_preview": "found", "iteration": 1},
        {"t": 5.0, "type": "llm_call_start", "phase": "GP_PHASE"},
        {"t": 6.0, "type": "tool_result", "name": "record_point", "result_preview": "✅ POINT [P_B] created", "iteration": 2},
        {"t": 7.0, "type": "llm_call_end", "phase": "GP_PHASE", "data": {"tool_call_count": 1, "content_chars": 10}},
    ]
    topology = _build_round_topology(events, duration_s=8.0)

    assert topology["schema"] == "genesis.round_topology.v1"
    assert topology["classification"] == "anchored_then_wandering"
    assert topology["anchor_timing"] == "early_anchor"
    assert topology["post_anchor_shape"] == "compact"
    assert topology["points_created"] == 2
    assert topology["lines_successful"] == 1
    assert topology["knowledge_searches"] == 1
    assert topology["gp_llm_calls"] == 2
    assert topology["first_anchor_point_id"] == "P_A"
    assert topology["first_anchor_basis_id"] == "P_BASE"
    assert topology["new_points_after_anchor"] == 1
    assert topology["last_gp_tool_call_count"] == 1


def test_frontier_carry_warnings_expose_signal_provenance(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _build_frontier_state

    frontier = _build_frontier_state(
        round_index=4,
        response="继续分析这个概念缺口",
        kb_delta_summary="+0新/0更新",
        kb_changed=False,
        node_telemetry="节点计数观测: stable",
        round_events=[],
        consecutive_dry=4,
        progress_class="strong",
    )
    rendered = "\n".join(frontier["observations"] + frontier["carry_warnings"] + frontier["next_checks"])

    assert "KB(source=vault_delta)" in rendered
    assert "候选问题(source=response_text)" in rendered
    assert "文本回复(source=response_text)" in rendered
    assert "source=sandbox_diff_snapshot" in rendered
    assert "source=vault_delta" in rendered
    assert "source=tool_event_absence" in rendered
    assert "semantic_progress=unknown" in rendered
    assert "已确认:" not in rendered
    assert "有活动但无持久产出" not in rendered
    assert "当前线索已连续空转" not in rendered


def test_candidate_issue_skips_closure_boilerplate(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _extract_candidate_issue

    response = """
本轮探索已完成收束。

**核心发现：Session Planner 议程恢复与触发重置的三层断裂**

通过代码审计确认了 planner_agenda 保留但 last_planner_round 重置。
"""

    issue = _extract_candidate_issue(response)
    assert issue.startswith("Session Planner 议程恢复")
    assert "本轮探索" not in issue


def test_topic_tracker_detects_isomorphic_template_saturation(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import TopicTracker

    tracker = TopicTracker()
    issues = [
        "Evidence Assessor 防御性休眠机制定性",
        "技能层孤儿工厂的三层断裂验证",
        "GENESIS_SESSION_ID 幽灵层是形态完备-功能休眠模式在 artifacts 层的同构复现",
        "心跳墓园的三层结构验证",
    ]
    result = None
    for idx, issue in enumerate(issues, 1):
        result = tracker.update(idx, issue, had_progress=True)

    assert result["action"] == "close_template"
    assert "同构饱和" in result["message"]
    assert "已饱和解释模板" in tracker.format_for_prompt()
    assert "非同构问题" in tracker.get_saturation_focus()


def test_topic_tracker_seeds_from_recent_reports(tmp_path, monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import TopicTracker, _seed_topic_tracker_from_reports
    import json

    reports = tmp_path / "auto_reports" / "s1"
    reports.mkdir(parents=True)
    issues = [
        "Evidence Assessor 防御性休眠机制定性",
        "技能层孤儿工厂的三层断裂验证",
        "GENESIS_SESSION_ID 幽灵层是形态完备-功能休眠模式在 artifacts 层的同构复现",
        "心跳墓园的三层结构验证",
    ]
    for idx, issue in enumerate(issues, 1):
        (reports / f"round_{idx:03d}.json").write_text(json.dumps({
            "status": "completed",
            "activity_detected": True,
            "response_full": f"本轮探索已完成收束。\n\n**核心发现：{issue}**",
        }, ensure_ascii=False), encoding="utf-8")

    tracker = TopicTracker()
    seeded = _seed_topic_tracker_from_reports(tracker, tmp_path / "auto_reports")

    assert seeded == 4
    assert "已饱和解释模板" in tracker.format_for_prompt()
    assert "非同构问题" in tracker.get_saturation_focus()


def test_auto_progress_summary_marks_activity_as_proxy(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _classify_auto_round_progress

    profile = _classify_auto_round_progress(
        response="read result",
        round_events=[{"type": "tool_result", "name": "read_file", "args": {"path": "genesis/x.py"}, "result_preview": "x"}],
        kb_changed=True,
        outcome_detected=False,
    )
    summary = profile["activity_summary"]
    assert "progress_signal_kind=tool_result_activity_proxy" in summary
    assert "semantic_progress=unknown" in summary
    assert "tools(source=tool_event)=read_file" in summary
    assert "kb(source=vault_delta)" in summary

    outcome_profile = _classify_auto_round_progress(
        response="",
        round_events=[],
        kb_changed=False,
        outcome_detected=True,
    )
    assert "progress_signal_kind=sandbox_diff_outcome" in outcome_profile["activity_summary"]
    assert "outcome✓(source=sandbox_diff_snapshot)" in outcome_profile["activity_summary"]


def test_action_history_prompt_is_tool_repetition_not_user_input(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import ActionHistory

    history = ActionHistory()
    event = {"type": "tool_result", "name": "read_file", "args": {"path": "genesis/auto_mode.py"}}
    history.record_round(1, [event])
    history.record_round(2, [event])

    prompt = history.format_for_prompt()
    assert "source=tool_result_args" in prompt
    assert "不代表用户输入重复" in prompt
    assert "工具动作已多次执行" in prompt
    assert "结果已知" not in prompt


def test_cross_round_observations_include_proxy_signal_kinds(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _compute_cross_round_observations

    class FakeSelfEvolution:
        apply_history = [{"status": "success"}, {"status": "test_failed", "reason": "unit failed"}]
        file_cooldowns = {
            "a.py": {"stable_count": 0},
            "b.py": {"stable_count": 2},
            "c.py": {"stable_count": 5},
        }

    obs = _compute_cross_round_observations(
        [
            {"outcome_detected": False, "kb_changed": True, "c_phase_summary": {"supplements": 1}, "progress_class": "soft"},
            {"outcome_detected": True, "kb_changed": False, "c_phase_summary": {"supplements": 0}, "progress_class": "evidence"},
        ],
        FakeSelfEvolution(),
    )

    assert obs["signal_kind"] == "cross_round_outcome_proxy"
    assert obs["semantic_progress"] == "unknown"
    assert obs["outcome_signal_kind"] == "sandbox_diff_snapshot"
    assert obs["auto_apply_signal_kind"] == "rolling_apply_history_state"
    assert obs["kb_change_signal_kind"] == "vault_delta"
    assert obs["sandbox_stability_signal_kind"] == "self_evolution_cooldown_state"


def test_rolling_knowledge_state_demotes_stale_fact_language(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _build_auto_knowledge_state, _format_knowledge_state
    from genesis.v4.prompt_factory import FactoryManager

    state = _build_auto_knowledge_state(
        {
            "candidate_issue": "继续观察",
            "observations": ["KB(source=vault_delta) +1新/0更新"],
            "carry_warnings": [],
            "next_checks": [],
        },
        [],
        raw_state={
            "verified_facts": ["已确认: 旧状态中的强事实表述"],
            "failed_attempts": ["已连续3轮有活动但无持久产出(progress=soft)"],
            "next_checks": ["在已确认事实基础上探索新的概念切片", "避免重复验证已知事实或把代码证据当成默认目标"],
        },
    )
    rendered = _format_knowledge_state(state)
    factory = FactoryManager.__new__(FactoryManager)
    factory_rendered = factory.render_knowledge_state(state)
    prompt = factory.build_gp_prompt(knowledge_state=factory_rendered, gp_tool_names=[])

    combined = "\n".join([rendered, factory_rendered, prompt])
    assert "observations(source=rolling_state_proxy, non_verification)" in combined
    assert "avoid_repeating(source=rolling_state_proxy)" in combined
    assert "不是验证证明" in combined
    assert "候选观察(source=rolling_state_proxy)" in combined
    assert "未观察到 sandbox tracked diff 变化" in combined
    assert "已写入观察" in combined
    assert "已写入节点" in combined
    assert "verified_facts:" not in combined
    assert "可以直接当作已证实事实" not in combined
    assert "已确认:" not in combined
    assert "已确认事实" not in combined
    assert "已知事实" not in combined
    assert "有活动但无持久产出" not in combined


def test_user_correction_extraction_requires_explicit_marker(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _extract_user_correction_from_directive

    plain_directive = "继续围绕 PLS 探索；不要把普通用户方向误判成 correction"
    assert _extract_user_correction_from_directive(plain_directive) == ""
    assert _extract_user_correction_from_directive("用户修正：不要继续把 topic saturation 当作事实") == "不要继续把 topic saturation 当作事实"
    assert _extract_user_correction_from_directive("[user_correction]\nStop treating auto directive as human correction.\n\n## next") == "Stop treating auto directive as human correction."
    assert _extract_user_correction_from_directive("[operator_correction]\nline one\nline two\n## next") == "line one line two"


def test_auto_continue_prompt_marks_rolling_state_as_snapshot(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import AUTO_PROMPT_CONTINUE

    prompt = AUTO_PROMPT_CONTINUE.format(
        directive="继续",
        knowledge_state="issue: old",
        frontier_state="frontier",
        history="history",
        signals="signals",
        chapter_state="chapter",
    )

    assert "上一轮工作记忆（rolling_state_proxy 快照，非实时状态/非验证证明）" in prompt
    assert "上一轮工作记忆：" not in prompt


def test_round_log_retention_policy_marks_json_as_audit_source(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _ROUND_LOG_KEEP, _round_log_retention_policy

    policy = _round_log_retention_policy()

    assert policy["schema"] == "genesis.round_log_retention.v1"
    assert policy["in_memory_keep_full_rounds"] == _ROUND_LOG_KEEP
    assert policy["in_memory_compaction_scope"] == "old_round_log_records_only"
    assert policy["persistent_round_json_is_audit_source"] is True
    assert "response_full" in policy["in_memory_compacted_fields"]
    assert "knowledge_state" in policy["in_memory_compacted_fields"]


def test_kb_delta_counts_survive_round_log_compaction(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _ROUND_LOG_HEAVY_KEYS, _kb_delta_counts, _round_kb_delta_count

    record = {
        "kb_delta": {
            "new_nodes": [{"node_id": "P_A"}, {"node_id": "P_B"}],
            "updated_nodes": [{"node_id": "P_C"}],
            "error": None,
        }
    }
    record["kb_delta_counts"] = _kb_delta_counts(record["kb_delta"])
    for key in _ROUND_LOG_HEAVY_KEYS:
        record.pop(key, None)

    assert "kb_delta" not in record
    assert _round_kb_delta_count(record, "new_nodes") == 2
    assert _round_kb_delta_count(record, "updated_nodes") == 1


def test_self_evolution_restart_marker_records_privileged_review(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis import auto_mode

    monkeypatch.setattr(auto_mode, "SELF_EVOLUTION_REVIEW_MODE", "shadow")
    monkeypatch.setattr(auto_mode, "SELF_EVOLUTION_CANARY_ROUNDS", 3)

    marker = auto_mode.SelfEvolution._build_restart_marker(
        rollback_commit="abc123",
        applied_commit="def456",
        review_decision="REJECT",
        review_comment="unsafe change",
    )

    review = marker["privileged_promotion_review"]
    assert marker["rollback_commit"] == "abc123"
    assert marker["applied_commit"] == "def456"
    assert marker["canary_rounds"] == 3
    assert marker["review_mode"] == "shadow"
    assert marker["review_decision"] == "REJECT"
    assert marker["review_warning"] == "Twin-Review returned REJECT in shadow mode before privileged restart"
    assert review["action"] == "self_evolution_restart"
    assert review["command"] == "sudo systemctl restart yogg-auto.service"
    assert review["service_target"] == "yogg-auto.service"
    assert review["runner_user"] == "yoga"
    assert review["sudo_scope"] == "/usr/bin/systemctl restart yogg-auto.service"
    assert review["rollback_mechanism"] == "git reset --hard abc123"
    assert review["canary_rounds"] == 3
    assert review["crash_guard_threshold"] == 3
    assert review["manual_override_path"] == "human operator disables or stops yogg-auto.service with password-gated sudo"
    assert review["audit_record_path"]
    assert review["reviewer_decision"] == "REJECT"
    assert review["reviewer_identity"] == "twin_review_llm"
    assert review["review_timestamp"] == marker["timestamp"]
    assert review["review_mode"] == "shadow"
    assert review["review_comment_preview"] == "unsafe change"


def test_self_evolution_canary_preserves_review_metadata(tmp_path, monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis import auto_mode

    monkeypatch.setattr(auto_mode, "SELF_EVOLUTION_REVIEW_MODE", "shadow")
    monkeypatch.setattr(auto_mode, "SELF_EVOLUTION_CANARY_ROUNDS", 3)
    marker_path = tmp_path / ".self_evolution_restart"
    monkeypatch.setattr(auto_mode.SelfEvolution, "_RESTART_MARKER", marker_path)

    marker = auto_mode.SelfEvolution._build_restart_marker(
        rollback_commit="abc123",
        applied_commit="def456",
        review_decision="REJECT",
        review_comment="unsafe change",
    )
    marker_path.write_text(auto_mode.json.dumps(marker, ensure_ascii=False), encoding="utf-8")

    assert auto_mode.SelfEvolution.check_and_rollback_if_needed() is False
    persisted = auto_mode.json.loads(marker_path.read_text(encoding="utf-8"))
    assert persisted["canary_rounds"] == 2
    assert persisted["review_decision"] == "REJECT"
    assert persisted["review_mode"] == "shadow"
    assert persisted["privileged_promotion_review"]["review_decision"] == "REJECT"
