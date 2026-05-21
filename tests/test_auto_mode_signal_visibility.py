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
