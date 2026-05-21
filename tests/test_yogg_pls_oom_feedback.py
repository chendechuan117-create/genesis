import sqlite3

from genesis.v4.knowledge_query import KnowledgeQuery
from genesis.v4.c_phase import CPhaseMixin
from genesis.v4.loop import V4Loop
from genesis.v4.prompt_factory import FactoryManager, NodeManagementTools
from genesis.v4.signature_engine import SignatureEngine


class DummyVault:
    def __init__(self):
        self.used = []
        self.outcomes = []

    def sync_vector_matrix_incremental(self):
        return None

    def increment_usage(self, node_ids):
        self.used.extend(node_ids)

    def record_usage_outcome(self, node_ids, success):
        self.outcomes.append((list(node_ids), success))


class DummyLoop(V4Loop):
    def __init__(self):
        pass


def _make_signature_engine():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE knowledge_nodes (node_id TEXT, metadata_signature TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE learned_signature_markers (dim_key TEXT, marker_value TEXT, source_persona TEXT, hit_count INTEGER DEFAULT 1, PRIMARY KEY (dim_key, marker_value))")
    conn.commit()
    engine = SignatureEngine(conn, vault=None)
    engine.initialize()
    return engine


def _make_memory_query(contents):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE knowledge_nodes (node_id TEXT PRIMARY KEY, created_at TEXT)")
    conn.execute("CREATE TABLE node_contents (node_id TEXT PRIMARY KEY, full_content TEXT)")
    for idx, content in enumerate(contents):
        node_id = f"MEM_CONV_{idx}"
        conn.execute("INSERT INTO knowledge_nodes (node_id, created_at) VALUES (?, ?)", (node_id, f"2026-05-14 00:0{idx}:00"))
        conn.execute("INSERT INTO node_contents (node_id, full_content) VALUES (?, ?)", (node_id, content))
    conn.commit()
    return KnowledgeQuery(conn)


def test_signature_normalize_flattens_stringified_environment_scope():
    engine = _make_signature_engine()
    nested = {
        "environment_scope": ["genesis_yogg", "['genesis_yogg', '[\\\"remote\\\"]']"],
        "applies_to_environment_scope": "['genesis_yogg', '[\\\"remote\\\"]']",
        "language": "python, shell, python",
    }
    normalized = engine.normalize(nested)
    assert normalized["environment_scope"] == "genesis_yogg"
    assert normalized["applies_to_environment_scope"] == "genesis_yogg"
    assert normalized["language"] == ["python", "shell"]
    assert "[" not in normalized["environment_scope"]


def test_signature_merge_keeps_environment_scope_scalar():
    engine = _make_signature_engine()
    merged = engine.merge(
        {"environment_scope": "genesis_yogg"},
        {"environment_scope": "['genesis_yogg']"},
        {"applies_to_environment_scope": ["genesis_yogg", "['remote']"]},
    )
    assert merged["environment_scope"] == "genesis_yogg"
    assert merged["applies_to_environment_scope"] == "genesis_yogg"


def test_signature_environment_scope_preserves_first_valid_value():
    engine = _make_signature_engine()
    normalized = engine.normalize({"environment_scope": ["remote", "genesis_yogg"]})
    assert normalized["environment_scope"] == "remote"


def test_auto_memory_storage_sanitizes_full_prompt():
    tools = NodeManagementTools(vault=object())
    auto_prompt = """[GENESIS_USER_REQUEST_START]
继续自主概念探索。上一轮留下的是痕迹，不是答案。

## 用户方向
继续围绕 Genesis/Yogg 概念整体探索一个缺口

上一轮工作记忆：
- issue: 本轮已收束

当前信号（仅供参考）：
[PLS 地形摘要] 大量内容
"""
    sanitized = tools._sanitize_memory_user_msg(auto_prompt)
    assert sanitized.startswith("[auto_session]")
    assert "source: auto_mode_injection" in sanitized
    assert "继续围绕 Genesis/Yogg" in sanitized
    assert "[PLS 地形摘要]" not in sanitized
    assert "当前信号" not in sanitized


def test_auto_memory_store_uses_autosession_slot_not_user_slot():
    class CaptureVault:
        def __init__(self):
            self.created = None

        def create_node(self, **kwargs):
            self.created = kwargs

        def delete_node(self, node_id):
            return None

        @property
        def _conn(self):
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE knowledge_nodes (node_id TEXT, created_at TEXT)")
            return conn

    vault = CaptureVault()
    tools = NodeManagementTools(vault=vault)
    tools.store_conversation("[GENESIS_USER_REQUEST_START]\n## 用户方向\n继续自主概念探索", "完成")
    content = vault.created["full_content"]
    assert content.startswith("AutoSession:")
    assert "source: auto_mode_injection" in content
    assert "\n用户:" not in content


def test_recent_memory_returns_digest_not_full_auto_prompt():
    full = "用户: [GENESIS_USER_REQUEST_START]\n继续自主概念探索。\n\n## 用户方向\n继续围绕 Genesis/Yogg 概念整体探索\n\n当前信号（仅供参考）：\n" + "X" * 5000 + "\nGenesis: ## 收束\n本轮确认了资格自证问题。"
    query = _make_memory_query([full])
    recent = query.get_recent_memory(limit=1)
    assert len(recent) < 900
    assert "X" * 100 not in recent
    assert "继续围绕 Genesis/Yogg" in recent
    assert "资格自证" in recent


def test_recent_memory_preserves_autosession_source_label():
    full = "AutoSession:\n[auto_session]\nsource: auto_mode_injection\ndirective: 继续自主概念探索\nGenesis: ## 收束\n本轮确认了 MEM_CONV 剧本化石。"
    query = _make_memory_query([full])
    recent = query.get_recent_memory(limit=1)
    assert "source: auto_mode_injection" in recent
    assert "继续自主概念探索" in recent
    assert "MEM_CONV 剧本化石" in recent


def test_tool_result_is_full_for_first_followup_then_receipt_after_consumed():
    loop = DummyLoop()
    large = "header\n" + "A" * 7000 + "\n[建议挂载] P_A, P_B\n" + "tail" * 1000
    from genesis.core.base import Message, MessageRole
    loop.g_messages = [
        Message(role=MessageRole.SYSTEM, content="s"),
        Message(role=MessageRole.ASSISTANT, content="", tool_calls=[{"id": "1", "name": "search_knowledge_nodes", "arguments": {}}]),
        Message(role=MessageRole.TOOL, content=large, tool_call_id="1", name="search_knowledge_nodes"),
    ]
    first = loop._messages_for_provider()
    assert first[-1]["content"] == large
    loop.g_messages.append(Message(role=MessageRole.ASSISTANT, content="看完了，继续"))
    second = loop._messages_for_provider()
    assert second[2]["content"] != large
    assert "[已消费工具结果收据：search_knowledge_nodes]" in second[2]["content"]
    assert "[建议挂载] P_A, P_B" in second[2]["content"]


def test_knowledge_state_normalization_is_not_destructive():
    loop = DummyLoop()
    long_fact = "关键事实 " + "Z" * 900
    raw_state = {
        "issue": "当前焦点 " + "I" * 500,
        "verified_facts": [long_fact] + [f"fact-{idx}" for idx in range(8)],
        "failed_attempts": ["NONE", "失败路径 " + "F" * 700],
        "next_checks": [f"check-{idx}" for idx in range(7)],
    }
    normalized = loop._normalize_knowledge_state(raw_state)
    assert normalized["issue"].endswith("I" * 500)
    assert normalized["verified_facts"][0] == long_fact
    assert len(normalized["verified_facts"]) == 9
    assert normalized["failed_attempts"] == ["失败路径 " + "F" * 700]
    assert len(normalized["next_checks"]) == 7
    rendered = FactoryManager(vault=object()).render_knowledge_state(normalized)
    assert long_fact in rendered


def test_phase_trace_signature_is_bounded():
    loop = DummyLoop()
    loop.vault = type("Vault", (), {"signature": _make_signature_engine()})()
    signature = {"environment_scope": ["genesis_yogg", "['genesis_yogg']"], "custom": "Z" * 20000}
    compact = loop._compact_signature_for_trace(signature)
    assert len(str(compact)) < 7000
    assert compact["environment_scope"] == "genesis_yogg"


def test_cursor_exports_only_non_preloaded_nodes():
    loop = DummyLoop()
    loop.execution_active_nodes = []
    loop.execution_active_node_roles = {}
    loop.metrics = type("Metrics", (), {"total_tokens": 0})()
    loop.user_input = "继续探索 cursor"
    loop._gp_reached_max_iterations = False
    loop._mark_active_nodes(["P_PRE"], "preloaded")
    cursor = loop.export_knowledge_cursor()
    assert cursor["active_node_ids"] == []
    loop._mark_active_nodes(["P_SEARCH"], "search_suggested")
    cursor = loop.export_knowledge_cursor()
    assert cursor["active_node_ids"] == ["P_SEARCH"]


def test_cursor_suppressed_after_timeout():
    loop = DummyLoop()
    loop.execution_active_nodes = ["P_SEARCH"]
    loop.execution_active_node_roles = {"P_SEARCH": {"search_suggested"}}
    loop.metrics = type("Metrics", (), {"total_tokens": 0})()
    loop.user_input = "继续探索 cursor"
    loop._gp_reached_max_iterations = True
    cursor = loop.export_knowledge_cursor()
    assert cursor["active_node_ids"] == []
    assert cursor["cursor_suppressed"] is True


def test_arena_ignores_preloaded_only_nodes():
    class ArenaLoop(CPhaseMixin):
        def __init__(self):
            self.execution_active_node_roles = {"P_PRE": {"preloaded"}, "P_SEARCH": {"search_suggested"}}

    loop = ArenaLoop()
    assert loop._eligible_arena_nodes(["P_PRE", "P_SEARCH"]) == ["P_SEARCH"]
