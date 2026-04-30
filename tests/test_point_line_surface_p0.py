import asyncio


class FakeVectorEngine:
    is_ready = True

    def search(self, query_text, top_k=3, threshold=0.75):
        return [("PLS_EXISTING", 0.9)]

    def encode(self, text):
        return []

    def add_to_matrix(self, node_id, vec):
        pass

    def add_to_matrix_batch(self, items):
        pass


def make_vault(tmp_path):
    from genesis.v4.manager import NodeVault

    NodeVault._instance = None
    db_path = tmp_path / "vault.sqlite"
    db_path.touch()
    return NodeVault(db_path=db_path, skip_vector_engine=True)


def reset_vault():
    from genesis.v4.manager import NodeVault

    if NodeVault._instance is not None:
        try:
            NodeVault._instance._conn.close()
        except Exception:
            pass
    NodeVault._instance = None


def test_surface_push_preserves_high_incoming_basis_nodes():
    from genesis.v4.surface import SurfaceExpander

    expander = SurfaceExpander(vault=None)
    fill_nodes = [
        ("PLS_BASIS_A", "基础"),
        ("PLS_BASIS_B", "基础"),
        ("PLS_FILL_LOW_A", "探索"),
        ("PLS_FILL_LOW_B", "探索"),
    ]
    incoming_counts = {
        "PLS_BASIS_A": 5,
        "PLS_BASIS_B": 3,
        "PLS_FILL_LOW_A": 0,
        "PLS_FILL_LOW_B": 0,
    }

    retained, pushed = expander._push_phase(
        fill_nodes,
        ["PLS_FRONTIER_A", "PLS_FRONTIER_B"],
        incoming_counts,
        budget=2,
    )

    retained_ids = {nid for nid, _ in retained}
    pushed_ids = {nid for nid, _ in pushed}
    assert retained_ids == {"PLS_BASIS_A", "PLS_BASIS_B"}
    assert pushed_ids == {"PLS_FRONTIER_A", "PLS_FRONTIER_B"}


def test_virtual_point_creation_uses_valid_schema(tmp_path):
    vault = make_vault(tmp_path)
    try:
        for nid in ["PLS_BASIS_A", "PLS_BASIS_B"]:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )

        vid = vault.ensure_virtual_point("same area", ["PLS_BASIS_A", "PLS_BASIS_B"])
        assert vid.startswith("VIRT_")

        row = vault._conn.execute(
            "SELECT node_id, type, title, human_translation, is_virtual, usage_count FROM knowledge_nodes WHERE node_id = ?",
            (vid,),
        ).fetchone()
        assert dict(row) == {
            "node_id": vid,
            "type": "CONTEXT",
            "title": "饱和:same area",
            "human_translation": "饱和:same area",
            "is_virtual": 1,
            "usage_count": 1,
        }
        content = vault._conn.execute("SELECT full_content FROM node_contents WHERE node_id = ?", (vid,)).fetchone()
        assert content[0] == "饱和:same area"

        assert vault.ensure_virtual_point("same area", ["PLS_BASIS_A"]) == vid
        usage = vault._conn.execute("SELECT usage_count FROM knowledge_nodes WHERE node_id = ?", (vid,)).fetchone()[0]
        assert usage == 2
    finally:
        reset_vault()


def test_trace_round_marks_same_round_without_time_window(tmp_path):
    from genesis.tools.node_tools import RecordLessonNodeTool

    vault = make_vault(tmp_path)
    try:
        for nid in ["PLS_OLD", "PLS_SIBLING"]:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )
        vault.create_reasoning_line("PLS_SIBLING", "PLS_OLD", reasoning="same trace", trace_id="tr-a", round_seq=7)

        assert vault.get_same_round_ids(["PLS_SIBLING"], trace_id="tr-a", round_seq=7) == {"PLS_SIBLING"}
        assert vault.get_same_round_ids(["PLS_SIBLING"], trace_id="tr-b", round_seq=7) == set()
        assert vault.get_same_round_ids(["PLS_SIBLING"]) == set()

        tool = RecordLessonNodeTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(
            node_id="PLS_NEW",
            title="new point",
            trigger_verb="verify",
            trigger_noun="same_round",
            trigger_context="test",
            action_steps=["write line"],
            because_reason="round identity",
            resolves="same round",
            reasoning_basis=[{"basis_node_id": "PLS_SIBLING", "reasoning": "same GP round"}],
            _trace_id="tr-a",
            _round_seq=7,
        ))
        assert "推理线" in result

        row = vault._conn.execute(
            "SELECT same_round, trace_id, round_seq FROM reasoning_lines WHERE new_point_id = ? AND basis_point_id = ?",
            ("PLS_NEW", "PLS_SIBLING"),
        ).fetchone()
        assert dict(row) == {"same_round": 1, "trace_id": "tr-a", "round_seq": 7}
        assert vault.get_incoming_line_count("PLS_SIBLING") == 0
    finally:
        reset_vault()


def test_record_point_context_creation_drives_same_round_detection(tmp_path):
    from genesis.tools.node_tools import RecordContextNodeTool, RecordLineTool, RecordPointTool

    vault = make_vault(tmp_path)
    try:
        point_tool = RecordPointTool()
        context_tool = RecordContextNodeTool()
        line_tool = RecordLineTool()
        point_tool.vault = vault
        context_tool.vault = vault
        line_tool.vault = vault

        asyncio.run(point_tool.execute(
            title="basis point",
            content="basis",
            node_id="PLS_BASIS_NEW",
            _trace_id="tr-create",
            _round_seq=1,
        ))
        asyncio.run(point_tool.execute(
            title="child point",
            content="child",
            node_id="PLS_CHILD_NEW",
            _trace_id="tr-create",
            _round_seq=1,
        ))
        result = asyncio.run(line_tool.execute(
            new_point_id="PLS_CHILD_NEW",
            basis_point_id="PLS_BASIS_NEW",
            reasoning="same GP turn",
            _trace_id="tr-create",
            _round_seq=1,
        ))
        assert "同轮" in result
        assert vault.get_incoming_line_count("PLS_BASIS_NEW") == 0

        asyncio.run(context_tool.execute(
            node_id="CTX_SAME_ROUND",
            title="same round ctx",
            state_description="ctx",
            _trace_id="tr-ctx",
            _round_seq=3,
        ))
        asyncio.run(point_tool.execute(
            title="ctx child",
            content="ctx child",
            node_id="PLS_CTX_CHILD",
            _trace_id="tr-ctx",
            _round_seq=3,
        ))
        result = asyncio.run(line_tool.execute(
            new_point_id="PLS_CTX_CHILD",
            basis_point_id="CTX_SAME_ROUND",
            reasoning="same GP turn context anchor",
            _trace_id="tr-ctx",
            _round_seq=3,
        ))
        assert "同轮" in result
        assert vault.get_incoming_line_count("CTX_SAME_ROUND") == 0

        vault.create_node(
            node_id="CTX_OLD_ANCHOR",
            ntype="CONTEXT",
            title="old anchor",
            human_translation="old anchor",
            tags="test",
            full_content="old",
        )
        asyncio.run(context_tool.execute(
            node_id="CTX_OLD_ANCHOR",
            title="old anchor updated",
            state_description="updated",
            _trace_id="tr-old",
            _round_seq=4,
        ))
        asyncio.run(point_tool.execute(
            title="old anchor child",
            content="old anchor child",
            node_id="PLS_OLD_ANCHOR_CHILD",
            _trace_id="tr-old",
            _round_seq=4,
        ))
        result = asyncio.run(line_tool.execute(
            new_point_id="PLS_OLD_ANCHOR_CHILD",
            basis_point_id="CTX_OLD_ANCHOR",
            reasoning="existing anchor remains old basis",
            _trace_id="tr-old",
            _round_seq=4,
        ))
        assert "异轮" in result
        assert vault.get_incoming_line_count("CTX_OLD_ANCHOR") == 1
    finally:
        reset_vault()


def test_semantic_similarity_with_different_lines_creates_related_point(tmp_path):
    from genesis.tools.node_tools import RecordLessonNodeTool

    vault = make_vault(tmp_path)
    try:
        for nid in ["PLS_BASIS_A", "PLS_BASIS_B"]:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )
        vault.create_node(
            node_id="PLS_EXISTING",
            ntype="LESSON",
            title="existing",
            human_translation="existing",
            tags="test",
            full_content="existing content",
        )
        vault.create_reasoning_line("PLS_EXISTING", "PLS_BASIS_A", reasoning="old basis")
        vault.vector_engine = FakeVectorEngine()

        tool = RecordLessonNodeTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(
            node_id="PLS_NEW_DISTINCT_LINE",
            title="existing",
            trigger_verb="verify",
            trigger_noun="dedup",
            trigger_context="test",
            action_steps=["preserve new line"],
            because_reason="different basis",
            resolves="dedup",
            reasoning_basis=[{"basis_node_id": "PLS_BASIS_B", "reasoning": "different causal basis"}],
        ))

        assert "写入成功" in result
        assert "已建立 RELATED_TO" in result
        assert vault._conn.execute("SELECT 1 FROM knowledge_nodes WHERE node_id = ?", ("PLS_NEW_DISTINCT_LINE",)).fetchone()
        assert vault._conn.execute(
            "SELECT 1 FROM node_edges WHERE source_id = ? AND target_id = ? AND relation = 'RELATED_TO'",
            ("PLS_NEW_DISTINCT_LINE", "PLS_EXISTING"),
        ).fetchone()
        assert vault.get_incoming_line_count("PLS_BASIS_B") == 1
    finally:
        reset_vault()
