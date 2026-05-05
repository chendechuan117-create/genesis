import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTORY = ROOT / "factory.py"
NODE_TOOLS = ROOT / "genesis" / "tools" / "node_tools.py"
DOCTOR = ROOT / "scripts" / "doctor.sh"
AUTO_MODE = ROOT / "genesis" / "auto_mode.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice_between(text: str, start: str, end: str) -> str:
    s = text.index(start)
    e = text.index(end, s)
    return text[s:e]


def _factory_node_tool_imports() -> set[str]:
    tree = ast.parse(_read(FACTORY))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "genesis.tools.node_tools":
            names.update(alias.name for alias in node.names)
    return names


def _node_tool_classes() -> set[str]:
    tree = ast.parse(_read(NODE_TOOLS))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def test_factory_node_tools_do_not_reference_phantom_record_context_point_tool():
    factory_text = _read(FACTORY)

    assert "RecordContextPointTool" not in factory_text
    assert _factory_node_tool_imports() <= _node_tool_classes()
    assert {"RecordPointTool", "RecordLineTool", "RecordLessonNodeTool"} <= _factory_node_tool_imports()


def test_doctor_host_managed_container_edits_are_visible_and_block_test_diff():
    text = _read(DOCTOR)
    host_managed_body = _slice_between(text, "_container_host_managed_status() {", "_sync_container_to_host() {")
    test_diff_body = _slice_between(text, "cmd_test_diff() {", "cmd_diff_status() {")
    file_status_body = _slice_between(text, "cmd_file_status() {", "cmd_diff() {")

    assert "HOST_MANAGED_SYNC_EXCLUDE" in text
    assert 'echo "H:${f}:host-managed"' in host_managed_body
    assert 'if [ "$container_hash" = "$host_wt_hash" ]; then' in host_managed_body
    assert "_container_host_managed_status" in file_status_body
    assert "HOST_MANAGED_BLOCKED" in test_diff_body
    assert "return 5" in test_diff_body
    assert test_diff_body.index("HOST_MANAGED_BLOCKED") < test_diff_body.index("local tracked_changed")


def test_self_evolution_cooldown_uses_persistent_attempt_sequence_not_session_round():
    text = _read(AUTO_MODE)
    death_guard = _slice_between(text, "recent = self.apply_history[-3:]", "if h_files:")

    assert "self.apply_attempt_seq: int = 0" in text
    assert 'data.get("apply_attempt_seq", 0)' in text
    assert '"apply_attempt_seq": self.apply_attempt_seq' in text
    assert "current_attempt_seq = self.apply_attempt_seq" in text
    assert '"attempt_seq": current_attempt_seq' in text
    assert "last_fail_attempt_seq" in death_guard
    assert "current_attempt_seq - int(last_fail_attempt_seq)" in death_guard
    assert "round_num - last_fail_round" not in death_guard


def test_self_evolution_blocks_host_managed_file_status_before_apply_flow():
    text = _read(AUTO_MODE)
    file_status_window = _slice_between(text, "async def _get_file_status", "async def _try_apply")
    apply_window = _slice_between(text, "async def _try_apply", "    def clear_restart_marker():")

    assert 'parts[0] in ("T", "U", "H")' in file_status_window
    assert 'v["type"] == "H"' in apply_window
    assert '"status": "host_managed_blocked"' in apply_window
    assert "需要人工审查" in apply_window
    assert apply_window.index("if h_files:") < apply_window.index("开始自进化应用流程")
