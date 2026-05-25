from genesis.v4.blackboard import Blackboard


class DummyVault:
    def get_node_briefs(self, node_ids):
        return {
            node_id: {
                "node_id": node_id,
                "ntype": "LESSON",
                "trust_tier": "REFLECTION",
            }
            for node_id in node_ids
        }

    def get_incoming_line_counts_batch(self, node_ids):
        return {node_id: 3 for node_id in node_ids}


def test_blackboard_shared_anchor_is_not_reported_as_diversity_void():
    board = Blackboard()
    board.add_evidence("INTJ", "same anchor from architecture lens", ["P_SHARED"], "inspect genesis/v4/blackboard.py")
    board.add_evidence("INTP", "same anchor from logic lens", ["P_SHARED"], "inspect genesis/v4/blackboard.py")
    board.add_evidence("ENFP", "same anchor from exploration lens", ["P_SHARED"], "inspect genesis/v4/blackboard.py")

    board.collapse(DummyVault())

    sources = [item["source"] for item in board.search_voids]
    assert "shared_anchor_detection" in sources
    assert "convergence_detection" not in sources


def test_blackboard_single_persona_repetition_still_reports_sparse_independent_evidence():
    board = Blackboard()
    board.add_evidence("INTJ", "first repeat", ["P_REPEAT"], "inspect genesis/v4/blackboard.py")
    board.add_evidence("INTJ", "second repeat", ["P_REPEAT"], "inspect genesis/v4/blackboard.py")
    board.add_evidence("INTJ", "third repeat", ["P_REPEAT"], "inspect genesis/v4/blackboard.py")

    board.collapse(DummyVault())

    sources = [item["source"] for item in board.search_voids]
    assert "convergence_detection" in sources
    assert "shared_anchor_detection" not in sources
