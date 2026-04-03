import asyncio
import io
import json
import logging
import sys
import types
from unittest.mock import patch


def _stub_provider_stack():
    if "httpx" not in sys.modules:
        sys.modules["httpx"] = types.ModuleType("httpx")


def _stub_vector_stack():
    if "numpy" not in sys.modules:
        numpy_mod = types.ModuleType("numpy")
        numpy_mod.ndarray = list
        numpy_mod.array = lambda x, *a, **k: x
        numpy_mod.asarray = lambda x, *a, **k: x
        numpy_mod.float32 = float
        sys.modules["numpy"] = numpy_mod
    if "torch" not in sys.modules:
        torch_mod = types.ModuleType("torch")
        class _NoGrad:
            def __enter__(self): return None
            def __exit__(self, exc_type, exc, tb): return False
        torch_mod.no_grad = lambda: _NoGrad()
        torch_mod.cuda = types.SimpleNamespace(is_available=lambda: False)
        torch_mod.device = lambda name: name
        sys.modules["torch"] = torch_mod
    if "transformers" not in sys.modules:
        tr = types.ModuleType("transformers")
        class _Auto:
            @classmethod
            def from_pretrained(cls, *args, **kwargs): return cls()
            def to(self, *args, **kwargs): return self
            def eval(self): return self
            def __call__(self, *args, **kwargs): return types.SimpleNamespace(last_hidden_state=[])
        tr.AutoTokenizer = _Auto
        tr.AutoModel = _Auto
        tr.AutoModelForSequenceClassification = _Auto
        sys.modules["transformers"] = tr
    if "sentence_transformers" not in sys.modules:
        st = types.ModuleType("sentence_transformers")
        class _CrossEncoder:
            def __init__(self, *args, **kwargs): pass
            def predict(self, pairs): return [0.5 for _ in pairs]
        st.CrossEncoder = _CrossEncoder
        sys.modules["sentence_transformers"] = st


class _DummyVectorEngine:
    is_ready = False
    def search(self, *args, **kwargs): return []
    def rerank(self, query, rows): return rows


class _DummyVault:
    def __init__(self):
        self.vector_engine = _DummyVectorEngine()
        self.created = []
        self.updated = []
        self.edges = []
    def create_node(self, **kwargs): self.created.append(kwargs)
    def update_node_content(self, *args, **kwargs): self.updated.append((args, kwargs))
    def promote_node_confidence(self, *args, **kwargs): pass
    def get_node_briefs(self, ids): return {}
    def add_edge(self, *args, **kwargs): self.edges.append((args, kwargs))


FULL = {
    "node_id": "LESSON_DOCTOR_RUNTIME_FINGERPRINT_20260330",
    "title": "record_lesson_node runtime fingerprint match audit",
    "trigger_verb": "debug",
    "trigger_noun": "record_lesson_node",
    "trigger_context": "verify register execute identity closure",
    "action_steps": ["boot factory agent", "capture register fingerprint", "capture execute fingerprint", "compare object ids and signatures"],
    "because_reason": "same tool name may hide runtime surface drift; register and execute must be bound to the same live object before blaming worktree",
}


async def run_probe():
    _stub_provider_stack()
    _stub_vector_stack()
    from factory import create_agent

    log_stream = io.StringIO()
    registry_logger = logging.getLogger("genesis.core.registry")
    old_level = registry_logger.level
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)
    registry_logger.addHandler(handler)
    registry_logger.setLevel(logging.INFO)

    try:
        with patch("genesis.tools.node_tools.NodeVault", _DummyVault):
            agent = create_agent(api_key="x", base_url="http://127.0.0.1", model="dummy")
            reg = agent.tools
            result = await reg.execute("record_lesson_node", dict(FULL), source="pytest", trace_id="fp-test-001")
            tool = reg.get("record_lesson_node")
    finally:
        registry_logger.removeHandler(handler)
        registry_logger.setLevel(old_level)

    logs = log_stream.getvalue().splitlines()
    fp_lines = [line for line in logs if "[RECORD_LESSON_RUNTIME_IDENTITY]" in line]
    return {
        "result": result,
        "fingerprint_lines": fp_lines,
        "tool_object_id": id(tool),
        "tool_execute_signature": str(__import__("inspect").signature(tool.execute)),
    }


def test_record_lesson_runtime_fingerprint_register_execute_consistent():
    payload = asyncio.run(run_probe())
    assert payload["result"].startswith("✅ LESSON节点")
    assert len(payload["fingerprint_lines"]) >= 2
    register_line = next(line for line in payload["fingerprint_lines"] if "'phase': 'register'" in line)
    execute_line = next(line for line in payload["fingerprint_lines"] if "'phase': 'execute'" in line)
    assert f"'object_id': {payload['tool_object_id']}" in register_line
    assert f"'object_id': {payload['tool_object_id']}" in execute_line
    assert f"'execute_signature': '{payload['tool_execute_signature']}'" in register_line
    assert f"'execute_signature': '{payload['tool_execute_signature']}'" in execute_line
    assert "'normalization_path': 'direct'" in execute_line
    assert "stack_summary" in register_line
