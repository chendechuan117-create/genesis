import asyncio
import json
import os


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


def create_basic_node(vault, node_id):
    vault.create_node(
        node_id=node_id,
        ntype="CONTEXT",
        title=node_id,
        human_translation=node_id,
        tags="test",
        full_content=node_id,
    )


def test_record_line_reports_hidden_endpoint_reason(tmp_path):
    from genesis.tools.node_tools import RecordLineTool

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "PLS_CHILD_ACTIVE")
        create_basic_node(vault, "PLS_BASIS_HIDDEN")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("PLS_BASIS_HIDDEN",),
        )
        vault._conn.commit()

        tool = RecordLineTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(
            new_point_id="PLS_CHILD_ACTIVE",
            basis_point_id="PLS_BASIS_HIDDEN",
            reasoning="hidden basis should be rejected explicitly",
        ))

        assert result.startswith("Error: 推理线写入被拒绝")
        assert "basis_hidden(ablation_active=2)" in result
        assert "请确认两个节点都存在且不是自引用" not in result
        assert not vault._conn.execute(
            "SELECT 1 FROM reasoning_lines WHERE new_point_id = ? AND basis_point_id = ?",
            ("PLS_CHILD_ACTIVE", "PLS_BASIS_HIDDEN"),
        ).fetchone()
    finally:
        reset_vault()


def test_create_node_edge_reports_hidden_endpoint_failure(tmp_path):
    from genesis.tools.node_tools import CreateNodeEdgeTool

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "PLS_EDGE_SOURCE")
        create_basic_node(vault, "PLS_EDGE_TARGET_HIDDEN")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("PLS_EDGE_TARGET_HIDDEN",),
        )
        vault._conn.commit()

        tool = CreateNodeEdgeTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(
            source_id="PLS_EDGE_SOURCE",
            target_id="PLS_EDGE_TARGET_HIDDEN",
            relation="RELATED_TO",
        ))

        assert result.startswith("Error: 边建立被拒绝")
        assert "target_hidden(ablation_active=2)" in result
        assert not vault._conn.execute(
            "SELECT 1 FROM node_edges WHERE source_id = ? AND target_id = ?",
            ("PLS_EDGE_SOURCE", "PLS_EDGE_TARGET_HIDDEN"),
        ).fetchone()
    finally:
        reset_vault()


def test_search_exact_hidden_node_id_reports_visibility_without_void(tmp_path):
    from genesis.tools.search_tool import SearchKnowledgeNodesTool

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_VOID_HIDDEN_EXACT")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("P_VOID_HIDDEN_EXACT",),
        )
        vault._conn.commit()

        tool = SearchKnowledgeNodesTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(keywords=["P_VOID_HIDDEN_EXACT"]))

        assert "节点存在但未作为活跃知识返回" in result
        assert "P_VOID_HIDDEN_EXACT" in result
        assert "ablation_active=2" in result
        assert "知识空洞" in result
        assert not vault._conn.execute(
            "SELECT 1 FROM void_tasks WHERE query = ?",
            ("P_VOID_HIDDEN_EXACT",),
        ).fetchone()
    finally:
        reset_vault()


def test_search_exact_hidden_node_id_reports_visibility_even_with_other_hits(tmp_path):
    from genesis.tools.search_tool import SearchKnowledgeNodesTool

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_VOID_HIDDEN_WITH_HITS")
        create_basic_node(vault, "P_ACTIVE_OTHER_HIT")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("P_VOID_HIDDEN_WITH_HITS",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET tags = ? WHERE node_id = ?",
            ("shared_visible_token", "P_ACTIVE_OTHER_HIT"),
        )
        vault._conn.commit()

        tool = SearchKnowledgeNodesTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(keywords=["P_VOID_HIDDEN_WITH_HITS", "shared_visible_token"]))

        assert "节点存在但未作为活跃知识返回" in result
        assert "P_VOID_HIDDEN_WITH_HITS" in result
        assert "ablation_active=2" in result
        assert "P_ACTIVE_OTHER_HIT" in result
        assert not vault._conn.execute(
            "SELECT 1 FROM void_tasks WHERE query = ?",
            ("P_VOID_HIDDEN_WITH_HITS shared_visible_token",),
        ).fetchone()
    finally:
        reset_vault()


def test_search_exact_active_node_id_does_not_create_density_void(tmp_path):
    from genesis.tools.search_tool import SearchKnowledgeNodesTool

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_ACTIVE_EXACT_LOW_DENSITY")

        tool = SearchKnowledgeNodesTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(keywords=["P_ACTIVE_EXACT_LOW_DENSITY"]))

        assert "P_ACTIVE_EXACT_LOW_DENSITY" in result
        assert "节点存在但未作为活跃知识返回" not in result
        assert not vault._conn.execute(
            "SELECT 1 FROM void_tasks WHERE query = ?",
            ("P_ACTIVE_EXACT_LOW_DENSITY",),
        ).fetchone()
    finally:
        reset_vault()


def test_search_exact_contradicted_node_id_reports_visibility_without_void(tmp_path):
    from genesis.tools.node_tools import CreateNodeEdgeTool
    from genesis.tools.search_tool import SearchKnowledgeNodesTool

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_VOID_CONTRADICTOR")
        create_basic_node(vault, "P_VOID_CONTRADICTED")

        edge_tool = CreateNodeEdgeTool()
        edge_tool.vault = vault
        edge_result = asyncio.run(edge_tool.execute(
            source_id="P_VOID_CONTRADICTOR",
            target_id="P_VOID_CONTRADICTED",
            relation="CONTRADICTS",
        ))
        assert "P_VOID_CONTRADICTOR" in edge_result

        search_tool = SearchKnowledgeNodesTool()
        search_tool.vault = vault
        result = asyncio.run(search_tool.execute(keywords=["P_VOID_CONTRADICTED"]))

        assert "节点存在但未作为活跃知识返回" in result
        assert "P_VOID_CONTRADICTED" in result
        assert "CONTRADICTS-filtered" in result
        assert "知识空洞" in result
        assert not vault._conn.execute(
            "SELECT 1 FROM void_tasks WHERE query = ?",
            ("P_VOID_CONTRADICTED",),
        ).fetchone()
    finally:
        reset_vault()


def test_c_gardener_does_not_count_rejected_edge(tmp_path):
    from genesis.v4.c_phase import CPhaseMixin

    class ToolCall:
        name = "create_node_edge"
        arguments = {
            "source_id": "PLS_C_SOURCE",
            "target_id": "PLS_C_TARGET_HIDDEN",
            "relation": "RELATED_TO",
        }

    class ProviderResponse:
        tool_calls = [ToolCall()]
        total_tokens = 7

    class Provider:
        async def chat(self, *args, **kwargs):
            return ProviderResponse()

    class Runner(CPhaseMixin):
        def _update_metrics(self, response, phase="C"):
            pass

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "PLS_C_SOURCE")
        create_basic_node(vault, "PLS_C_TARGET_HIDDEN")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("PLS_C_TARGET_HIDDEN",),
        )
        vault._conn.commit()

        runner = Runner()
        runner.vault = vault
        runner.provider = Provider()
        runner.user_input = "test"
        runner.g_messages = []
        runner.execution_active_nodes = ["PLS_C_SOURCE", "PLS_C_TARGET_HIDDEN"]
        runner.blackboard = None
        runner.inferred_signature = {}
        runner.loop_config = {}
        runner.trace_id = "tr-c"

        result = asyncio.run(runner._run_reflection("x" * 220))

        assert result["edges_added"] == 0
        assert result["edges"] == []
        assert not vault._conn.execute(
            "SELECT 1 FROM node_edges WHERE source_id = ? AND target_id = ?",
            ("PLS_C_SOURCE", "PLS_C_TARGET_HIDDEN"),
        ).fetchone()
    finally:
        reset_vault()


def test_validated_concept_without_evidence_refs_is_downgraded(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault.create_node(
            node_id="P_VALIDATED_NO_EVIDENCE",
            ntype="CONTEXT",
            title="validated without evidence",
            human_translation="validated without evidence",
            tags="test",
            full_content="concept-only claim",
            source="gp_point",
            metadata_signature={
                "validation_status": "validated",
                "target_kind": "concept_plane",
                "task_kind": "concept_exploration",
            },
            verification_source="reflection",
            trust_tier="REFLECTION",
        )
        row = vault._conn.execute(
            "SELECT metadata_signature, last_verified_at FROM knowledge_nodes WHERE node_id = ?",
            ("P_VALIDATED_NO_EVIDENCE",),
        ).fetchone()
        signature = json.loads(row["metadata_signature"])
        assert signature["validation_status"] == "partial"
        assert signature["knowledge_state"] == "unverified"
        assert signature["validation_gate"] == "missing_hard_evidence"
        assert row["last_verified_at"] is None
    finally:
        reset_vault()


def test_validated_concept_with_evidence_refs_keeps_validation(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault.create_node(
            node_id="P_VALIDATED_WITH_EVIDENCE",
            ntype="CONTEXT",
            title="validated with evidence",
            human_translation="validated with evidence",
            tags="test",
            full_content="evidence-backed claim",
            source="gp_point",
            metadata_signature={
                "validation_status": "validated",
                "target_kind": "concept_plane",
                "task_kind": "concept_exploration",
            },
            evidence_refs=[
                {
                    "type": "file",
                    "ref": "genesis/v4/manager.py",
                    "excerpt": "create_node validates metadata",
                    "observed_at": "2026-05-13 17:00:00",
                }
            ],
            verification_source="reflection",
            trust_tier="REFLECTION",
        )
        row = vault._conn.execute(
            "SELECT metadata_signature, last_verified_at FROM knowledge_nodes WHERE node_id = ?",
            ("P_VALIDATED_WITH_EVIDENCE",),
        ).fetchone()
        signature = json.loads(row["metadata_signature"])
        assert signature["validation_status"] == "validated"
        assert signature["knowledge_state"] == "current"
        assert signature["evidence_ref_count"] == "1"
        assert signature["evidence_refs"][0]["type"] == "file"
        assert row["last_verified_at"] is not None
        profile_row = vault._conn.execute(
            "SELECT * FROM knowledge_nodes WHERE node_id = ?",
            ("P_VALIDATED_WITH_EVIDENCE",),
        ).fetchone()
        profile = vault.build_reliability_profile(profile_row)
        assert profile["validation_status"] == "validated"
        assert profile["verification_is_event"] is True
        assert profile["evidence_signal_kind"] == "artifact_type_only"
        assert profile["evidence_artifact_types"] == ["file"]
        assert profile["source_identity_status"] == "absent"
    finally:
        reset_vault()


def test_legacy_verified_fields_without_evidence_are_read_as_claim_not_event(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault.create_node(
            node_id="P_LEGACY_VERIFIED_CLAIM",
            ntype="CONTEXT",
            title="legacy verified claim",
            human_translation="legacy verified claim",
            tags="test",
            full_content="legacy claim",
            source="gp_point",
            metadata_signature={
                "validation_status": "partial",
                "knowledge_state": "unverified",
            },
            trust_tier="REFLECTION",
        )
        legacy_signature = {
            "validation_status": "validated",
            "knowledge_state": "current",
            "valid_from": "2000-01-01",
        }
        vault._conn.execute(
            "UPDATE knowledge_nodes SET metadata_signature = ?, last_verified_at = ?, verification_source = ?, updated_at = ? WHERE node_id = ?",
            (
                json.dumps(legacy_signature),
                "2099-01-01 00:00:00",
                "command_output",
                "2000-01-01 00:00:00",
                "P_LEGACY_VERIFIED_CLAIM",
            ),
        )
        vault._conn.commit()

        row = vault._conn.execute(
            "SELECT * FROM knowledge_nodes WHERE node_id = ?",
            ("P_LEGACY_VERIFIED_CLAIM",),
        ).fetchone()
        profile = vault.build_reliability_profile(row)

        assert profile["verification_is_event"] is False
        assert profile["verification_claim_status"] == "validated"
        assert profile["validation_status"] == "partial"
        assert profile["knowledge_state"] == "unverified"
        assert profile["freshness_label"] == "stale"
        assert profile["confidence_score"] == 0.55
    finally:
        reset_vault()


def test_reliability_profile_marks_usage_as_arena_feedback_signal(tmp_path):
    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_USAGE_SIGNAL_KIND")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET usage_count = 3, usage_success_count = 2, usage_fail_count = 1 WHERE node_id = ?",
            ("P_USAGE_SIGNAL_KIND",),
        )
        vault._conn.commit()
        row = vault._conn.execute(
            "SELECT * FROM knowledge_nodes WHERE node_id = ?",
            ("P_USAGE_SIGNAL_KIND",),
        ).fetchone()
        profile = vault.build_reliability_profile(row)
        assert profile["usage_signal_kind"] == "arena_environment_feedback"
    finally:
        reset_vault()


def test_kb_entropy_uses_arena_feedback_wording_not_proven_usage(tmp_path):
    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_USAGE_ENTROPY_POSITIVE")
        create_basic_node(vault, "P_USAGE_ENTROPY_NEGATIVE")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET usage_count = 3, usage_success_count = 3 WHERE node_id = ?",
            ("P_USAGE_ENTROPY_POSITIVE",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET usage_count = 3, usage_success_count = 1, usage_fail_count = 2 WHERE node_id = ?",
            ("P_USAGE_ENTROPY_NEGATIVE",),
        )
        vault._conn.commit()

        entropy = vault.get_kb_entropy()

        assert entropy["usage_signal_kind"] == "arena_environment_feedback"
        assert "arena_positive_feedback_pct" in entropy
        assert "arena_negative_feedback_pct" in entropy
        assert "no_usage_feedback_pct" in entropy
        assert "proven_pct" not in entropy
        assert "failing_pct" not in entropy
        assert "untested_pct" not in entropy
    finally:
        reset_vault()


def test_network_health_report_demotes_verification_usage_and_health_claims(tmp_path):
    from genesis.v4.network_health import NetworkHealthMonitor

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_HEALTH_VERIFICATION_CLAIM")
        create_basic_node(vault, "P_HEALTH_RISK_BASIS")
        create_basic_node(vault, "P_HEALTH_CHILD_A")
        create_basic_node(vault, "P_HEALTH_CHILD_B")
        create_basic_node(vault, "P_HEALTH_CONTRADICTOR")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET last_verified_at = CURRENT_TIMESTAMP, verification_source = ? WHERE node_id = ?",
            ("command_output", "P_HEALTH_VERIFICATION_CLAIM"),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET usage_count = 10, usage_success_count = 0, usage_fail_count = 10 WHERE node_id = ?",
            ("P_HEALTH_RISK_BASIS",),
        )
        vault._conn.commit()
        vault.create_reasoning_line("P_HEALTH_CHILD_A", "P_HEALTH_RISK_BASIS", reasoning="basis A")
        vault.create_reasoning_line("P_HEALTH_CHILD_B", "P_HEALTH_RISK_BASIS", reasoning="basis B")
        vault.create_node_edge("P_HEALTH_CONTRADICTOR", "P_HEALTH_RISK_BASIS", relation="CONTRADICTS")

        report = NetworkHealthMonitor(vault).generate_health_report()

        assert "overall_observability" in report
        assert "overall_health" not in report
        assert report["overall_observability"]["score_signal_kind"] == "topology_observability_proxy"
        assert "visible_nodes" in report["overall_observability"]
        assert "active_nodes" not in report["overall_observability"]
        assert report["knowledge_distribution"]["type_signal_kind"] == "tool_shaped_schema_field"
        assert report["knowledge_distribution"]["trust_tier_signal_kind"] == "legacy_claim_or_default_field"
        assert "by_trust_tier_claim" in report["knowledge_distribution"]
        assert "by_trust_tier" not in report["knowledge_distribution"]

        growth = report["write_claim_metrics"]
        assert growth["nodes_with_recent_verification_claim"] == 1
        assert growth["verification_signal_kind"] == "legacy_claim_timestamp"
        assert growth["write_activity_signal_kind"] == "write_activity_proxy_not_health"
        assert "nodes_verified_last_week" not in growth
        assert "growth_rate" not in growth

        connection = report["connection_markers"]
        assert connection["contradiction_marker_count"] == 1
        assert connection["contradiction_signal_kind"] == "edge_claim_not_falsification"
        assert "contradiction_count" not in connection

        risks = report["topology_risk_markers"]
        assert risks["risk_marker_count"] == 1
        assert risks["risk_signal_kind"] == "topology_marker_not_node_failure"
        assert "trap_count" not in risks
        assert "trap_nodes" not in risks
    finally:
        reset_vault()


def test_network_health_dashboard_uses_proxy_wording_not_health_or_verified_claims(tmp_path):
    from genesis.v4.network_health import NetworkHealthMonitor

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_HEALTH_DASH_VERIFICATION_CLAIM")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET last_verified_at = CURRENT_TIMESTAMP, verification_source = ? WHERE node_id = ?",
            ("manual_check", "P_HEALTH_DASH_VERIFICATION_CLAIM"),
        )
        vault._conn.commit()

        dashboard = NetworkHealthMonitor(vault).render_health_dashboard()

        assert "知识网络观测代理报告" in dashboard
        assert "代理评分" in dashboard
        assert "写入/声明指标" in dashboard
        assert "验证声明时间戳" in dashboard
        assert "本周验证" not in dashboard
        assert "知识网络健康仪表板" not in dashboard
        assert "网络健康状态良好" not in dashboard
        assert "陷阱节点" not in dashboard
    finally:
        reset_vault()


def test_digest_demotes_high_incoming_to_basis_candidate_not_verification(tmp_path):
    vault = make_vault(tmp_path)
    try:
        for node_id in [
            "P_DIGEST_ACTIVE_BASIS",
            "P_DIGEST_ACTIVE_CHILD_A",
            "P_DIGEST_ACTIVE_CHILD_B",
            "P_DIGEST_HIDDEN_BASIS",
            "P_DIGEST_HIDDEN_CHILD_A",
            "P_DIGEST_HIDDEN_CHILD_B",
            "P_DIGEST_VIRTUAL_BASIS",
            "P_DIGEST_VIRTUAL_CHILD_A",
            "P_DIGEST_VIRTUAL_CHILD_B",
            "P_DIGEST_SAME_ROUND_BASIS",
            "P_DIGEST_SAME_ROUND_CHILD_A",
            "P_DIGEST_SAME_ROUND_CHILD_B",
        ]:
            create_basic_node(vault, node_id)
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("P_DIGEST_HIDDEN_BASIS",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET is_virtual = 1 WHERE node_id = ?",
            ("P_DIGEST_VIRTUAL_BASIS",),
        )
        vault._conn.commit()
        vault.create_reasoning_line("P_DIGEST_ACTIVE_CHILD_A", "P_DIGEST_ACTIVE_BASIS", reasoning="active A")
        vault.create_reasoning_line("P_DIGEST_ACTIVE_CHILD_B", "P_DIGEST_ACTIVE_BASIS", reasoning="active B")
        vault.create_reasoning_line("P_DIGEST_HIDDEN_CHILD_A", "P_DIGEST_HIDDEN_BASIS", reasoning="hidden A", allow_hidden=True)
        vault.create_reasoning_line("P_DIGEST_HIDDEN_CHILD_B", "P_DIGEST_HIDDEN_BASIS", reasoning="hidden B", allow_hidden=True)
        vault.create_reasoning_line("P_DIGEST_VIRTUAL_CHILD_A", "P_DIGEST_VIRTUAL_BASIS", reasoning="virtual A", allow_virtual=True)
        vault.create_reasoning_line("P_DIGEST_VIRTUAL_CHILD_B", "P_DIGEST_VIRTUAL_BASIS", reasoning="virtual B", allow_virtual=True)
        vault.create_reasoning_line("P_DIGEST_SAME_ROUND_CHILD_A", "P_DIGEST_SAME_ROUND_BASIS", reasoning="same A")
        vault.create_reasoning_line("P_DIGEST_SAME_ROUND_CHILD_B", "P_DIGEST_SAME_ROUND_BASIS", reasoning="same B")
        vault._conn.execute(
            "UPDATE reasoning_lines SET same_round = 1 WHERE basis_point_id = ?",
            ("P_DIGEST_SAME_ROUND_BASIS",),
        )
        vault._conn.commit()

        digest = vault.get_digest(top_k=10)

        assert "基础候选（被频繁作为 basis 引用，非验证证明）" in digest
        assert "前沿候选（尚未被后续作为 basis 引用，非验证状态）" in digest
        assert "P_DIGEST_ACTIVE_BASIS" in digest
        assert "P_DIGEST_HIDDEN_BASIS" not in digest
        assert "P_DIGEST_VIRTUAL_BASIS" not in digest
        assert "P_DIGEST_SAME_ROUND_BASIS" not in digest
        assert "已被反复验证" not in digest
        assert "尚未被验证" not in digest
        assert "(入线:" not in digest
    finally:
        reset_vault()


def test_generate_map_demotes_basis_and_frontier_labels(tmp_path):
    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_MAP_ACTIVE_BASIS")
        create_basic_node(vault, "P_MAP_ACTIVE_CHILD_A")
        create_basic_node(vault, "P_MAP_ACTIVE_CHILD_B")
        vault.create_reasoning_line("P_MAP_ACTIVE_CHILD_A", "P_MAP_ACTIVE_BASIS", reasoning="map A")
        vault.create_reasoning_line("P_MAP_ACTIVE_CHILD_B", "P_MAP_ACTIVE_BASIS", reasoning="map B")

        knowledge_map = vault.generate_map(max_clusters_per_type=2, titles_per_cluster=1)

        assert "基础候选（频繁被引用，非验证证明）" in knowledge_map
        assert "前沿候选（尚未被后续作为 basis 引用，非验证状态）" in knowledge_map
        assert "P_MAP_ACTIVE_BASIS" in knowledge_map
        assert "已被反复验证" not in knowledge_map
        assert "尚未被验证" not in knowledge_map
        assert " ⚔️矛盾" not in knowledge_map
    finally:
        reset_vault()


def test_l1_digest_hides_numeric_scores_and_uses_proxy_safe_labels(tmp_path):
    vault = make_vault(tmp_path)
    try:
        for node_id in [
            "P_L1_ACTIVE_BASIS",
            "P_L1_ACTIVE_CHILD_A",
            "P_L1_ACTIVE_CHILD_B",
            "P_L1_CONTRADICTOR",
            "P_L1_HIDDEN_BASIS",
            "P_L1_HIDDEN_CHILD_A",
            "P_L1_HIDDEN_CHILD_B",
            "P_L1_VIRTUAL_BASIS",
            "P_L1_VIRTUAL_CHILD_A",
            "P_L1_VIRTUAL_CHILD_B",
            "P_L1_SAME_ROUND_BASIS",
            "P_L1_SAME_ROUND_CHILD_A",
            "P_L1_SAME_ROUND_CHILD_B",
        ]:
            create_basic_node(vault, node_id)
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("P_L1_HIDDEN_BASIS",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET is_virtual = 1 WHERE node_id = ?",
            ("P_L1_VIRTUAL_BASIS",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET usage_count = 9, usage_success_count = 1, usage_fail_count = 8 WHERE node_id = ?",
            ("P_L1_ACTIVE_BASIS",),
        )
        vault._conn.commit()
        vault.create_reasoning_line("P_L1_ACTIVE_CHILD_A", "P_L1_ACTIVE_BASIS", reasoning="active A")
        vault.create_reasoning_line("P_L1_ACTIVE_CHILD_B", "P_L1_ACTIVE_BASIS", reasoning="active B")
        vault.create_reasoning_line("P_L1_HIDDEN_CHILD_A", "P_L1_HIDDEN_BASIS", reasoning="hidden A", allow_hidden=True)
        vault.create_reasoning_line("P_L1_HIDDEN_CHILD_B", "P_L1_HIDDEN_BASIS", reasoning="hidden B", allow_hidden=True)
        vault.create_reasoning_line("P_L1_VIRTUAL_CHILD_A", "P_L1_VIRTUAL_BASIS", reasoning="virtual A", allow_virtual=True)
        vault.create_reasoning_line("P_L1_VIRTUAL_CHILD_B", "P_L1_VIRTUAL_BASIS", reasoning="virtual B", allow_virtual=True)
        vault.create_reasoning_line("P_L1_SAME_ROUND_CHILD_A", "P_L1_SAME_ROUND_BASIS", reasoning="same A")
        vault.create_reasoning_line("P_L1_SAME_ROUND_CHILD_B", "P_L1_SAME_ROUND_BASIS", reasoning="same B")
        vault._conn.execute(
            "UPDATE reasoning_lines SET same_round = 1 WHERE basis_point_id = ?",
            ("P_L1_SAME_ROUND_BASIS",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET updated_at = ? WHERE node_id = ?",
            ("2099-01-01 00:00:00", "P_L1_SAME_ROUND_BASIS"),
        )
        vault.create_node_edge("P_L1_CONTRADICTOR", "P_L1_ACTIVE_BASIS", relation="CONTRADICTS")
        vault._conn.execute(
            "INSERT INTO void_tasks (void_id, query, status) VALUES (?, ?, ?)",
            ("VOID_L1_PROXY", "proxy-safe l1", "open"),
        )
        vault._conn.commit()

        digest = vault.generate_l1_digest(max_nodes=20)
        active_basis_line = next(line for line in digest.splitlines() if "P_L1_ACTIVE_BASIS" in line)
        same_round_line = next(line for line in digest.splitlines() if "P_L1_SAME_ROUND_BASIS" in line)

        assert "proxy-safe summary" in digest
        assert "type=工具塑形schema字段，非语义角色/验证状态" in digest
        assert "VOID队列存在" in digest
        assert "基础候选=引用代理，非验证证明" in digest
        assert "P_L1_ACTIVE_BASIS" in digest
        assert "基础候选" in active_basis_line
        assert "CONTRADICTS标记" in active_basis_line
        assert "前沿候选" in same_round_line
        assert "P_L1_HIDDEN_BASIS" not in digest
        assert "P_L1_VIRTUAL_BASIS" not in digest
        assert "usage_success_count" not in digest
        assert "usage_fail_count" not in digest
        assert "1W/8L" not in digest
        assert "⚔️" not in digest
        assert "LESSON (" not in digest
        assert "CONTEXT (" not in digest
        assert "... +" not in digest
        assert " top " not in digest
        assert " by freshness" not in digest
    finally:
        reset_vault()


def test_type_labels_are_rendered_as_schema_fields_not_semantic_truth(tmp_path):
    from genesis.tools.search_tool import SearchKnowledgeNodesTool

    vault = make_vault(tmp_path)
    try:
        vault.create_node(
            node_id="P_TYPE_SCHEMA_CONTEXT",
            ntype="CONTEXT",
            title="type schema context",
            human_translation="type schema context",
            tags="type-ecology",
            full_content="type is a tool-shaped schema field",
            source="gp_point",
        )
        vault.create_node(
            node_id="P_TYPE_SCHEMA_LESSON",
            ntype="LESSON",
            title="type schema lesson",
            human_translation="type schema lesson",
            tags="type-ecology",
            full_content="lesson type does not prove validation",
            source="gp_point",
        )
        vault.create_node(
            node_id="ASSET_TYPE_SCHEMA",
            ntype="ASSET",
            title="type schema asset",
            human_translation="type schema asset",
            tags="type-ecology",
            full_content="asset type does not prove runtime existence",
            source="reflection_meta",
        )
        digest = vault.get_digest()
        l1_digest = vault.generate_l1_digest(max_nodes=10)
        tool = SearchKnowledgeNodesTool()
        tool.vault = vault
        search_output = asyncio.run(tool.execute(keywords=["type schema"]))

        for output in (digest, l1_digest, search_output):
            assert "type=工具塑形schema字段，非语义角色/验证状态" in output
            assert "LESSON=已验证" not in output
            assert "ASSET=已存在" not in output
            assert "CONTEXT=事实" not in output
    finally:
        reset_vault()


def test_prompts_demote_basis_nodes_to_candidates_not_verified_truth():
    from pathlib import Path

    prompt_factory_source = Path(__file__).resolve().parents[1].joinpath("genesis", "v4", "prompt_factory.py").read_text()
    auto_mode_source = Path(__file__).resolve().parents[1].joinpath("genesis", "auto_mode.py").read_text()

    assert "基础候选" in prompt_factory_source
    assert "不是验证证明" in prompt_factory_source
    assert "已被反复验证" not in prompt_factory_source
    assert "直接作为推理基础使用" not in prompt_factory_source
    assert "基础节点**可直接依赖" not in auto_mode_source
    assert "基础候选" in auto_mode_source
    assert "不是验证证明" in auto_mode_source


def test_search_usage_labels_are_arena_feedback_not_success_claims(tmp_path):
    from genesis.tools.search_tool import SearchKnowledgeNodesTool

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_USAGE_SEARCH_LABEL")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET usage_success_count = 2, usage_fail_count = 1 WHERE node_id = ?",
            ("P_USAGE_SEARCH_LABEL",),
        )
        vault._conn.commit()
        tool = SearchKnowledgeNodesTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(keywords=["P_USAGE_SEARCH_LABEL"]))

        assert "Arena反馈混合" in result
        assert "有成功记录" not in result
        assert "有失败记录" not in result
        assert "有实战记录" not in result
    finally:
        reset_vault()


def test_search_evidence_ref_type_is_artifact_not_source_identity(tmp_path):
    from genesis.tools.search_tool import SearchKnowledgeNodesTool

    vault = make_vault(tmp_path)
    try:
        vault.create_node(
            node_id="P_EVIDENCE_ARTIFACT_ONLY",
            ntype="CONTEXT",
            title="evidence artifact only",
            human_translation="evidence artifact only",
            tags="evidence",
            full_content="evidence ref type is artifact metadata, not author identity",
            source="gp_point",
            metadata_signature={
                "validation_status": "validated",
                "target_kind": "concept_plane",
            },
            evidence_refs=[
                {
                    "type": "file",
                    "ref": "genesis/v4/arena_mixin.py",
                    "excerpt": "evidence type is an artifact classifier",
                }
            ],
            verification_source="reflection",
            trust_tier="REFLECTION",
        )

        tool = SearchKnowledgeNodesTool()
        tool.vault = vault
        result = asyncio.run(tool.execute(keywords=["P_EVIDENCE_ARTIFACT_ONLY"]))

        assert "evidence:artifact_type_only=file" in result
        assert "source_identity:absent" in result
        assert "source_identity:file" not in result
        assert "author:file" not in result
    finally:
        reset_vault()


def test_trace_query_cross_reference_uses_arena_feedback_wording(tmp_path, monkeypatch):
    from genesis.tools.trace_query_tool import TraceQueryTool
    from genesis.v4.trace_pipeline.entity_extractor import TraceEntity
    from genesis.v4.trace_pipeline.entity_store import TraceEntityStore
    from genesis.v4.trace_pipeline.relationship_builder import TraceRelationshipBuilder
    import genesis.v4.manager as manager

    vault = make_vault(tmp_path)
    try:
        create_basic_node(vault, "P_TRACE_USAGE_LABEL")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET usage_success_count = 4, usage_fail_count = 1 WHERE node_id = ?",
            ("P_TRACE_USAGE_LABEL",),
        )
        vault._conn.commit()
        monkeypatch.setattr(manager, "DB_PATH", vault.db_path)

        tool = TraceQueryTool()
        store = TraceEntityStore(db_path=tmp_path / "trace.sqlite")
        rb = TraceRelationshipBuilder(db_path=tmp_path / "trace.sqlite")
        try:
            store.store_entities([
                TraceEntity(
                    entity_type="PACKAGE",
                    value="P_TRACE_USAGE_LABEL",
                    confidence=1.0,
                    source_span_id="span-usage",
                    source_trace_id="tr-usage",
                    source_tool="test",
                    extraction_rule="test",
                    raw_fragment="P_TRACE_USAGE_LABEL",
                )
            ], trace_id="tr-usage")
            output = tool._do_recall(store, rb, "P_TRACE_USAGE_LABEL", 10)
        finally:
            rb.close()
            store.close()

        assert "Arena反馈 +4/-1" in output
        assert "win=" not in output
    finally:
        reset_vault()


def test_heartbeat_snapshot_is_demoted_when_stale_or_pid_dead(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault._conn.execute(
            "INSERT OR REPLACE INTO process_heartbeat (process_name, status, last_heartbeat, last_summary, pid, extra) VALUES (?, ?, ?, ?, ?, ?)",
            ("dead_daemon", "running", "2000-01-01 00:00:00", "old snapshot", 99999999, None),
        )
        vault._conn.commit()

        beats = vault.get_heartbeats()
        beat = next(b for b in beats if b["process_name"] == "dead_daemon")
        summary = vault.get_daemon_status_summary()

        assert beat["status"] == "running"
        assert beat["effective_status"] == "stale_snapshot"
        assert beat["heartbeat_stale"] is True
        assert beat["pid_alive"] is False
        assert beat["state_signal_kind"] == "heartbeat_snapshot"
        assert "dead_daemon: stale_snapshot" in summary
        assert "pid_not_alive" in summary
    finally:
        reset_vault()


def test_fresh_heartbeat_preserves_effective_status(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault.heartbeat("fresh_loop", "running", "fresh")
        beat = next(b for b in vault.get_heartbeats() if b["process_name"] == "fresh_loop")

        assert beat["pid"] == os.getpid()
        assert beat["effective_status"] == "running"
        assert beat["heartbeat_stale"] is False
        assert beat["pid_alive"] is True
    finally:
        reset_vault()


def test_stale_persona_stats_are_not_loaded_as_online_learning(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault._conn.execute(
            "INSERT OR REPLACE INTO persona_stats (persona, task_kind, wins, losses, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("OLD_PERSONA", "", 20, 1, "2000-01-01 00:00:00"),
        )
        vault._conn.execute(
            "INSERT OR REPLACE INTO persona_stats (persona, task_kind, wins, losses, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ("CURRENT_PERSONA", "", 2, 3),
        )
        vault._conn.execute(
            "INSERT OR REPLACE INTO persona_stats (persona, task_kind, wins, losses, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ("CURRENT_PERSONA", "debug", 4, 1),
        )
        vault._conn.commit()

        global_stats, task_stats = vault.load_persona_stats()

        assert "OLD_PERSONA" not in global_stats
        assert global_stats["CURRENT_PERSONA"] == {"wins": 2, "losses": 3}
        assert task_stats["CURRENT_PERSONA:debug"] == {"wins": 4, "losses": 1}
    finally:
        reset_vault()


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


def test_surface_push_only_evicts_nodes_that_frontier_can_replace():
    from genesis.v4.surface import SurfaceExpander

    expander = SurfaceExpander(vault=None)
    fill_nodes = [
        ("PLS_BASIS_A", "基础"),
        ("PLS_FILL_LOW_A", "探索"),
        ("PLS_FILL_LOW_B", "探索"),
    ]
    incoming_counts = {
        "PLS_BASIS_A": 5,
        "PLS_FILL_LOW_A": 0,
        "PLS_FILL_LOW_B": 0,
    }

    retained, pushed = expander._push_phase(
        fill_nodes,
        ["PLS_FRONTIER_A"],
        incoming_counts,
        budget=3,
    )

    assert len(retained) == 2
    assert len(pushed) == 1
    assert len(retained) + len(pushed) == len(fill_nodes)


def test_surface_co_presence_collects_unconsumed_low_incoming_points():
    from genesis.v4.surface import SurfaceExpander

    expander = SurfaceExpander(vault=None)
    evicted_fill = [
        ("PLS_LOW_EDGE", "探索"),
    ]
    neighbor_map = {
        "PLS_SEED": [
            ("PLS_BASIS_A", 1.5),
            ("PLS_SIDE_A", 2.0),
            ("PLS_SIDE_B", 1.0),
        ],
    }
    incoming_counts = {
        "PLS_BASIS_A": 5,
        "PLS_LOW_EDGE": 0,
        "PLS_SIDE_A": 0,
        "PLS_SIDE_B": 1,
    }

    co_presence = expander._co_presence_phase(
        evicted_fill,
        neighbor_map,
        incoming_counts,
        budget=2,
        used_ids={"PLS_BASIS_A"},
        excluded_ids=set(),
        basis_threshold=2,
    )

    assert co_presence == [
        ("PLS_LOW_EDGE", "游离"),
        ("PLS_SIDE_A", "游离"),
    ]


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
        point_types = {
            r["node_id"]: r["type"]
            for r in vault._conn.execute(
                "SELECT node_id, type FROM knowledge_nodes WHERE node_id IN (?,?)",
                ("PLS_BASIS_NEW", "PLS_CHILD_NEW"),
            ).fetchall()
        }
        assert point_types == {"PLS_BASIS_NEW": "CONTEXT", "PLS_CHILD_NEW": "CONTEXT"}
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


def test_potential_samples_are_triaged_without_crystallizing(tmp_path):
    vault = make_vault(tmp_path)
    try:
        count = vault.record_potential_samples([
            {
                "type": "missing_basis",
                "title": "当前面缺少基础锚点",
                "detail": "需要复查 basis",
                "node_ids": ["PLS_MISSING_BASIS"],
                "evidence": {"fill_count": 0},
            },
            {
                "type": "saturation",
                "title": "饱和势：R37",
                "detail": "路径重叠频繁",
                "node_ids": [],
                "evidence": {"area_hint": "R37"},
            },
        ], source="test")

        assert count == 2
        actionable = vault.get_open_potential_samples(triage_category="actionable")
        structural = vault.get_open_potential_samples(triage_category="structural")
        assert actionable[0]["triage_category"] == "actionable"
        assert actionable[0]["triage_note"].startswith("可验证势")
        assert structural == []
        saturation = vault._conn.execute(
            "SELECT triage_category, status, target_basin FROM potential_samples WHERE potential_type = ?",
            ("saturation",),
        ).fetchone()
        assert saturation["triage_category"] == "structural"
        assert saturation["status"] == "observed"
        assert saturation["target_basin"] == "R37"
        assert not vault._conn.execute(
            "SELECT 1 FROM knowledge_nodes WHERE node_id = ?",
            ("PLS_MISSING_BASIS",),
        ).fetchone()

        report = vault.get_potential_triage_report()
        categories = {r["triage_category"] for r in report["distribution"]}
        assert {"actionable", "structural"} <= categories
    finally:
        reset_vault()


def test_potential_samples_dedupe_repeated_saturation_across_sources(tmp_path):
    vault = make_vault(tmp_path)
    try:
        first = vault.record_potential_samples([
            {
                "type": "saturation",
                "title": "饱和势：R37",
                "detail": "路径重叠频繁",
                "node_ids": [],
                "evidence": {"area_hint": "R37", "count": 1},
            },
        ], trace_id="tr-1", source="knowledge_routing")
        second = vault.record_potential_samples([
            {
                "type": "saturation",
                "title": "饱和势：R37",
                "detail": "路径仍然重叠",
                "node_ids": [],
                "evidence": {"area_hint": "R37", "count": 9},
            },
        ], trace_id="tr-2", source="search_knowledge_nodes")

        assert first == 1
        assert second == 0
        rows = vault._conn.execute(
            "SELECT source, status, occurrence_count, last_seen_trace_id, last_seen_source, dedupe_key FROM potential_samples"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["source"] == "knowledge_routing"
        assert rows[0]["status"] == "observed"
        assert rows[0]["occurrence_count"] == 2
        assert rows[0]["last_seen_trace_id"] == "tr-2"
        assert rows[0]["last_seen_source"] == "search_knowledge_nodes"
        assert rows[0]["dedupe_key"]
    finally:
        reset_vault()


def test_potential_query_reports_occurrence_and_dedupe(tmp_path):
    from genesis.tools.pls_query_tool import PLSQueryTool

    vault = make_vault(tmp_path)
    try:
        sample = {
            "type": "saturation",
            "title": "饱和势：R37",
            "detail": "路径重叠频繁",
            "node_ids": [],
            "evidence": {"area_hint": "R37"},
        }
        assert vault.record_potential_samples([sample], source="knowledge_routing") == 1
        assert vault.record_potential_samples([sample], source="search_knowledge_nodes") == 0

        output = PLSQueryTool()._potential(vault._conn, "", 5)
        assert "rows=1 seen=2" in output
        assert "seen=2" in output
        assert "dedupe:" in output
    finally:
        reset_vault()


def test_existing_node_upsert_does_not_crystallize_matching_potential(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault.create_node(
            node_id="PLS_EXISTING",
            ntype="LESSON",
            title="existing",
            human_translation="existing",
            tags="test",
            full_content="existing content",
        )
        assert vault.record_potential_samples([
            {
                "type": "missing_basis",
                "title": "当前面缺少基础锚点",
                "detail": "需要复查 existing",
                "node_ids": ["PLS_EXISTING"],
                "evidence": {"fill_count": 0},
            },
        ], source="test") == 1

        vault.create_node(
            node_id="PLS_EXISTING",
            ntype="LESSON",
            title="existing updated",
            human_translation="existing updated",
            tags="test",
            full_content="updated content",
        )

        row = vault._conn.execute(
            "SELECT status, resolution_node_id FROM potential_samples WHERE potential_type = ?",
            ("missing_basis",),
        ).fetchone()
        assert row["status"] == "open"
        assert row["resolution_node_id"] is None
    finally:
        reset_vault()


def test_new_node_crystallizes_only_actionable_open_potentials(tmp_path):
    vault = make_vault(tmp_path)
    try:
        assert vault.record_potential_samples([
            {
                "type": "missing_basis",
                "title": "当前面缺少基础锚点",
                "detail": "需要复查 basis",
                "node_ids": ["PLS_NEW"],
                "evidence": {"fill_count": 0},
            },
            {
                "type": "co_presence",
                "title": "游离点共场形成“或许？”",
                "detail": "弱关系感",
                "node_ids": ["PLS_NEW"],
                "evidence": {"co_presence_count": 1},
            },
        ], source="test") == 2

        vault.create_node(
            node_id="PLS_NEW",
            ntype="LESSON",
            title="new",
            human_translation="new",
            tags="test",
            full_content="new content",
        )

        statuses = {
            r["potential_type"]: (r["triage_category"], r["status"], r["resolution_node_id"])
            for r in vault._conn.execute(
                "SELECT potential_type, triage_category, status, resolution_node_id FROM potential_samples"
            ).fetchall()
        }
        assert statuses["missing_basis"] == ("actionable", "crystallized", "PLS_NEW")
        assert statuses["co_presence"] == ("exit", "observed", None)
    finally:
        reset_vault()


def test_potential_status_contract_separates_actionable_from_terrain(tmp_path):
    vault = make_vault(tmp_path)
    try:
        assert vault.record_potential_samples([
            {
                "type": "missing_basis",
                "title": "当前面缺少基础锚点",
                "detail": "需要复查 basis",
                "node_ids": ["PLS_CONTRACT"],
                "evidence": {"fill_count": 0},
            },
            {
                "type": "saturation",
                "title": "饱和势：R37",
                "detail": "路径重叠频繁",
                "node_ids": [],
                "evidence": {"area_hint": "R37"},
            },
            {
                "type": "co_presence",
                "title": "游离点共场形成“或许？”",
                "detail": "弱关系感",
                "node_ids": ["PLS_CONTRACT"],
                "evidence": {"co_presence_count": 1},
            },
            {
                "type": "frontier_pressure",
                "title": "基础与前沿同时在场",
                "detail": "适合沿当前问题推进",
                "node_ids": ["PLS_CONTRACT"],
                "evidence": {"fill_count": 1, "push_count": 4},
            },
        ], source="test") == 4

        statuses = {
            r["potential_type"]: (r["triage_category"], r["status"], r["resolved_at"])
            for r in vault._conn.execute(
                "SELECT potential_type, triage_category, status, resolved_at FROM potential_samples"
            ).fetchall()
        }
        assert statuses["missing_basis"] == ("actionable", "open", None)
        assert statuses["saturation"] == ("structural", "observed", None)
        assert statuses["co_presence"] == ("exit", "observed", None)
        assert statuses["frontier_pressure"] == ("exit", "observed", None)
        open_samples = vault.get_open_potential_samples()
        assert [r["potential_type"] for r in open_samples] == ["missing_basis"]
    finally:
        reset_vault()


def test_observed_potential_is_not_treated_as_resolved(tmp_path):
    vault = make_vault(tmp_path)
    try:
        assert vault.record_potential_samples([
            {
                "type": "saturation",
                "title": "饱和势：R37",
                "detail": "路径重叠频繁",
                "node_ids": [],
                "evidence": {"area_hint": "R37"},
            },
        ], source="test") == 1

        row = vault._conn.execute(
            "SELECT sample_id, status, resolved_at, resolution_node_id FROM potential_samples"
        ).fetchone()
        assert row["status"] == "observed"
        assert row["resolved_at"] is None
        assert row["resolution_node_id"] is None
        assert vault.resolve_potential_sample(row["sample_id"], "resolved")
        resolved = vault._conn.execute(
            "SELECT status, resolved_at FROM potential_samples WHERE sample_id = ?",
            (row["sample_id"],),
        ).fetchone()
        assert resolved["status"] == "resolved"
        assert resolved["resolved_at"] is not None
    finally:
        reset_vault()


def test_preview_potential_sample_maintenance_is_read_only(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault._conn.executemany(
            "INSERT INTO potential_samples "
            "(source, potential_type, triage_category, title, detail, node_ids, evidence, status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [
                ("legacy", "saturation", "structural", "饱和势：R37", "old", "[]", "{\"area_hint\":\"R37\"}", "open"),
                ("legacy", "saturation", "structural", "饱和势：R37", "old", "[]", "{\"area_hint\":\"R37\"}", "open"),
                ("legacy", "missing_basis", "actionable", "当前面缺少基础锚点", "old", "[\"PLS_A\"]", "{\"fill_count\":0}", "open"),
            ],
        )
        vault._conn.commit()
        before = vault._conn.execute("SELECT COUNT(*) FROM potential_samples").fetchone()[0]

        preview = vault.preview_potential_sample_maintenance(limit=5)

        after = vault._conn.execute("SELECT COUNT(*) FROM potential_samples").fetchone()[0]
        assert after == before
        assert preview["summary"]["total_rows"] == 3
        assert preview["summary"]["missing_dedupe_total"] == 3
        assert preview["summary"]["active_open_total"] == 3
        assert preview["summary"]["active_open_actionable"] == 1
        assert preview["summary"]["active_open_non_actionable"] == 2
        assert preview["non_actionable_open"][0]["potential_type"] == "saturation"
        assert preview["non_actionable_open"][0]["rows"] == 2
        assert preview["duplicate_hotspots"][0]["potential_type"] == "saturation"
        assert preview["duplicate_hotspots"][0]["rows"] == 2
        assert preview["actionable_open_recent"][0]["potential_type"] == "missing_basis"
    finally:
        reset_vault()


def test_dependency_impact_report_is_read_only_recheck_hint(tmp_path):
    vault = make_vault(tmp_path)
    try:
        for nid in ["PLS_ROOT", "PLS_CHILD", "PLS_GRANDCHILD"]:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )
        vault.create_reasoning_line("PLS_CHILD", "PLS_ROOT", reasoning="direct")
        vault.create_reasoning_line("PLS_GRANDCHILD", "PLS_CHILD", reasoning="transitive")

        report = vault.get_dependency_impact_report("PLS_ROOT")
        statuses = {item["node_id"]: item["status"] for item in report["impacts"]}
        assert statuses["PLS_CHILD"] == "needs_recheck"
        assert statuses["PLS_GRANDCHILD"] == "dependency_risk"
        assert vault._conn.execute("SELECT COUNT(*) FROM knowledge_nodes WHERE node_id LIKE 'PLS_%'").fetchone()[0] == 3
        assert vault._conn.execute("SELECT COUNT(*) FROM reasoning_lines WHERE new_point_id LIKE 'PLS_%'").fetchone()[0] == 2
    finally:
        reset_vault()


def test_surface_diversity_guard_deduplicates_basis_overlap_only():
    from genesis.v4.surface import SurfaceExpander

    class GuardVault:
        def get_basis_set_for_node(self, node_id, include_same_round=False):
            return {
                "PLS_FRONTIER_A": {"PLS_BASIS_A", "PLS_BASIS_B"},
                "PLS_FRONTIER_B": {"PLS_BASIS_A", "PLS_BASIS_B"},
                "PLS_FRONTIER_C": {"PLS_BASIS_C"},
                "PLS_FRONTIER_D": set(),
            }.get(node_id, set())

    selected = SurfaceExpander(GuardVault())._surface_diversity_guard([
        "PLS_FRONTIER_A",
        "PLS_FRONTIER_B",
        "PLS_FRONTIER_C",
        "PLS_FRONTIER_D",
    ])

    assert selected == ["PLS_FRONTIER_A", "PLS_FRONTIER_C", "PLS_FRONTIER_D"]


def test_route_surface_filters_ablation_seeds_before_routing():
    from genesis.v4.loop import V4Loop

    class RoutingVault:
        def __init__(self):
            self.prefetched = []

        def get_excluded_ids(self, node_ids):
            return {"PLS_HIDDEN"} & set(node_ids)

        def get_neighbor_map(self, node_ids, include_reverse_reasoning=True, weighted=True):
            self.prefetched.extend(node_ids)
            return {nid: [] for nid in node_ids}

        def get_incoming_line_counts_batch(self, node_ids):
            return {nid: 0 for nid in node_ids}

        def get_incoming_count_percentile(self, percentile):
            return 2

        def get_virtual_saturation(self, node_ids):
            return []

        def get_frontier_node_ids(self, limit=50):
            return []

    loop = object.__new__(V4Loop)
    loop.vault = RoutingVault()
    loop.trace_id = "tr-filter"
    loop._surface_potential_sample_count = 0

    routed_ids, surface_roles, surface_result = loop._expand_route_surface(
        ["PLS_HIDDEN", "PLS_VISIBLE"],
        context_budget=4,
    )

    assert "PLS_HIDDEN" not in routed_ids
    assert routed_ids == ["PLS_VISIBLE"]
    assert set(surface_roles) == {"PLS_VISIBLE"}
    assert surface_result["surface_nodes"] == [("PLS_VISIBLE", "探索")]
    assert loop.vault.prefetched == ["PLS_VISIBLE"]


def test_increment_usage_skips_ablation_nodes(tmp_path):
    vault = make_vault(tmp_path)
    try:
        for nid in ["PLS_VISIBLE", "PLS_HIDDEN"]:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("PLS_HIDDEN",),
        )
        before = {
            r["node_id"]: r["usage_count"]
            for r in vault._conn.execute(
                "SELECT node_id, usage_count FROM knowledge_nodes WHERE node_id IN (?, ?)",
                ("PLS_VISIBLE", "PLS_HIDDEN"),
            ).fetchall()
        }
        vault.increment_usage(["PLS_VISIBLE", "PLS_HIDDEN"])

        after = {
            r["node_id"]: r["usage_count"]
            for r in vault._conn.execute(
                "SELECT node_id, usage_count FROM knowledge_nodes WHERE node_id IN (?, ?)",
                ("PLS_VISIBLE", "PLS_HIDDEN"),
            ).fetchall()
        }
        assert after["PLS_VISIBLE"] == before["PLS_VISIBLE"] + 1
        assert after["PLS_HIDDEN"] == before["PLS_HIDDEN"]
    finally:
        reset_vault()


def test_pls_active_only_counts_and_neighbors_exclude_hidden_virtual(tmp_path):
    vault = make_vault(tmp_path)
    try:
        for nid in [
            "PLS_ACTIVE_NEW",
            "PLS_ACTIVE_BASIS",
            "PLS_HIDDEN_BASIS",
            "PLS_VIRTUAL_BASIS",
        ]:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("PLS_HIDDEN_BASIS",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET is_virtual = 1 WHERE node_id = ?",
            ("PLS_VIRTUAL_BASIS",),
        )
        vault._conn.commit()
        vault.create_reasoning_line("PLS_ACTIVE_NEW", "PLS_ACTIVE_BASIS", reasoning="active")
        vault.create_reasoning_line("PLS_ACTIVE_NEW", "PLS_HIDDEN_BASIS", reasoning="hidden", allow_hidden=True)
        vault.create_reasoning_line("PLS_ACTIVE_NEW", "PLS_VIRTUAL_BASIS", reasoning="virtual", allow_virtual=True)
        vault.add_edge("PLS_ACTIVE_NEW", "PLS_HIDDEN_BASIS", "RELATED_TO", allow_hidden=True)
        vault.add_edge("PLS_ACTIVE_NEW", "PLS_VIRTUAL_BASIS", "RELATED_TO", allow_virtual=True)

        assert vault.get_incoming_line_count("PLS_ACTIVE_BASIS") == 1
        assert vault.get_incoming_line_count("PLS_HIDDEN_BASIS") == 0
        assert vault.get_incoming_line_count("PLS_HIDDEN_BASIS", include_hidden=True) == 1
        assert vault.get_incoming_line_count("PLS_VIRTUAL_BASIS") == 0
        assert vault.get_incoming_line_count("PLS_VIRTUAL_BASIS", include_virtual=True) == 1
        assert vault.get_incoming_line_counts_batch([
            "PLS_ACTIVE_BASIS",
            "PLS_HIDDEN_BASIS",
            "PLS_VIRTUAL_BASIS",
        ]) == {
            "PLS_ACTIVE_BASIS": 1,
            "PLS_HIDDEN_BASIS": 0,
            "PLS_VIRTUAL_BASIS": 0,
        }
        assert vault.get_basis_set_for_node("PLS_ACTIVE_NEW") == {"PLS_ACTIVE_BASIS"}
        assert vault.get_basis_set_for_node("PLS_ACTIVE_NEW", include_hidden=True, include_virtual=True) == {
            "PLS_ACTIVE_BASIS",
            "PLS_HIDDEN_BASIS",
            "PLS_VIRTUAL_BASIS",
        }
        default_neighbors = vault.get_neighbor_map(["PLS_ACTIVE_NEW"])
        assert default_neighbors["PLS_ACTIVE_NEW"] == ["PLS_ACTIVE_BASIS"]
        assert "PLS_HIDDEN_BASIS" not in default_neighbors
        assert "PLS_VIRTUAL_BASIS" not in default_neighbors
        expanded_neighbors = set(vault.get_neighbor_map(
            ["PLS_ACTIVE_NEW"],
            include_hidden=True,
            include_virtual=True,
        )["PLS_ACTIVE_NEW"])
        assert {"PLS_ACTIVE_BASIS", "PLS_HIDDEN_BASIS", "PLS_VIRTUAL_BASIS"}.issubset(expanded_neighbors)
    finally:
        reset_vault()


def test_pls_query_basis_defaults_to_active_only(tmp_path):
    from genesis.tools.pls_query_tool import PLSQueryTool

    vault = make_vault(tmp_path)
    try:
        node_ids = [
            "PLS_ACTIVE_BASIS_Q",
            "PLS_HIDDEN_BASIS_Q",
            "PLS_ACTIVE_CHILD_Q1",
            "PLS_ACTIVE_CHILD_Q2",
            "PLS_ACTIVE_CHILD_Q3",
        ]
        for nid in node_ids:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("PLS_HIDDEN_BASIS_Q",),
        )
        vault._conn.commit()
        vault.create_reasoning_line("PLS_ACTIVE_CHILD_Q1", "PLS_HIDDEN_BASIS_Q", reasoning="hidden high", allow_hidden=True)
        vault.create_reasoning_line("PLS_ACTIVE_CHILD_Q2", "PLS_HIDDEN_BASIS_Q", reasoning="hidden high", allow_hidden=True)
        vault.create_reasoning_line("PLS_ACTIVE_CHILD_Q3", "PLS_ACTIVE_BASIS_Q", reasoning="active low")

        default_output = asyncio.run(
            PLSQueryTool().execute(
                mode="basis",
                limit=5,
                db_path=str(vault.db_path),
            )
        )
        include_hidden_output = asyncio.run(
            PLSQueryTool().execute(
                mode="basis",
                limit=5,
                include_hidden=True,
                db_path=str(vault.db_path),
            )
        )

        assert "PLS_ACTIVE_BASIS_Q" in default_output
        assert "PLS_HIDDEN_BASIS_Q" not in default_output
        assert "PLS_HIDDEN_BASIS_Q" in include_hidden_output
    finally:
        reset_vault()


def test_pls_write_contract_rejects_inactive_endpoints_by_default(tmp_path):
    vault = make_vault(tmp_path)
    try:
        for nid in [
            "PLS_WRITE_VISIBLE",
            "PLS_WRITE_HIDDEN",
            "PLS_WRITE_VIRTUAL",
        ]:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("PLS_WRITE_HIDDEN",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET is_virtual = 1 WHERE node_id = ?",
            ("PLS_WRITE_VIRTUAL",),
        )
        vault._conn.commit()

        assert vault.create_reasoning_line("PLS_WRITE_VISIBLE", "PLS_WRITE_HIDDEN", reasoning="hidden") is False
        assert vault.create_reasoning_line("PLS_WRITE_VISIBLE", "PLS_WRITE_VIRTUAL", reasoning="virtual") is False
        assert vault.add_edge("PLS_WRITE_VISIBLE", "PLS_WRITE_HIDDEN", "RELATED_TO") is False
        assert vault.add_edge("PLS_WRITE_VISIBLE", "PLS_WRITE_VIRTUAL", "RELATED_TO") is False
        assert vault.create_node_edge("PLS_WRITE_VISIBLE", "PLS_WRITE_HIDDEN", "RELATED_TO") is False
        assert vault.create_reasoning_line(
            "PLS_WRITE_VISIBLE",
            "PLS_WRITE_HIDDEN",
            reasoning="explicit audit",
            allow_hidden=True,
        ) is True
        assert vault.add_edge(
            "PLS_WRITE_VISIBLE",
            "PLS_WRITE_VIRTUAL",
            "RELATED_TO",
            allow_virtual=True,
        ) is True
    finally:
        reset_vault()


def test_spiral_pioneer_raw_edge_path_rejects_inactive_endpoints(tmp_path):
    import sqlite3
    import sys
    import types

    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)
    from genesis.auto_mode import SpiralPioneer

    vault = make_vault(tmp_path)
    try:
        for nid in [
            "PLS_SPIRAL_VISIBLE",
            "PLS_SPIRAL_HIDDEN",
            "PLS_SPIRAL_VIRTUAL",
        ]:
            vault.create_node(
                node_id=nid,
                ntype="LESSON",
                title=nid,
                human_translation=nid,
                tags="test",
                full_content=nid,
            )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("PLS_SPIRAL_HIDDEN",),
        )
        vault._conn.execute(
            "UPDATE knowledge_nodes SET is_virtual = 1 WHERE node_id = ?",
            ("PLS_SPIRAL_VIRTUAL",),
        )
        vault._conn.commit()
        conn = sqlite3.connect(str(vault.db_path))
        try:
            pioneer = object.__new__(SpiralPioneer)
            assert pioneer._insert_edge_if_valid(conn, "PLS_SPIRAL_VISIBLE", "PLS_SPIRAL_HIDDEN", "RELATED_TO", 0.8) == 0
            assert pioneer._insert_edge_if_valid(conn, "PLS_SPIRAL_VISIBLE", "PLS_SPIRAL_VIRTUAL", "RELATED_TO", 0.8) == 0
            assert pioneer._insert_edge_if_valid(conn, "PLS_SPIRAL_VISIBLE", "PLS_SPIRAL_VISIBLE", "RELATED_TO", 0.8) == 0
            assert conn.execute("SELECT COUNT(*) FROM node_edges WHERE source_id = ?", ("PLS_SPIRAL_VISIBLE",)).fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        reset_vault()
