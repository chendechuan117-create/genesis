import asyncio
import json
import sqlite3
from types import SimpleNamespace

from genesis.core.base import PerformanceMetrics
from genesis.core.tracer import Tracer
from genesis.v4.c_phase import CPhaseMixin
from genesis.v4.loop import V4Loop


def test_tracer_log_llm_call_persists_zero_cache_hit_tokens(tmp_path, monkeypatch):
    db_dir = tmp_path / "runtime"
    db_path = db_dir / "traces.db"
    monkeypatch.setattr("genesis.core.tracer._DB_DIR", db_dir)
    monkeypatch.setattr("genesis.core.tracer._DB_PATH", db_path)

    tracer = Tracer()
    trace_id = tracer.start_trace("cache probe")
    tracer.log_llm_call(
        trace_id,
        phase="GP",
        model="deepseek-v4-flash",
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_hit_tokens=0,
        duration_ms=12.5,
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT cache_hit_tokens, metadata_json FROM spans WHERE trace_id = ? AND span_type = 'llm_call'",
        (trace_id,),
    ).fetchone()
    conn.close()

    assert row["cache_hit_tokens"] == 0
    assert json.loads(row["metadata_json"])["cache_hit_tokens"] == 0


def test_v4_loop_cache_stats_split_gp_first_and_warm_buckets():
    loop = V4Loop.__new__(V4Loop)
    loop.metrics = PerformanceMetrics()
    loop._cache_phase_stats = {}
    loop._cache_bucket_stats = {}

    first = SimpleNamespace(input_tokens=100, output_tokens=10, total_tokens=110, prompt_cache_hit_tokens=0)
    warm = SimpleNamespace(input_tokens=200, output_tokens=20, total_tokens=220, prompt_cache_hit_tokens=150)
    c_phase = SimpleNamespace(input_tokens=50, output_tokens=5, total_tokens=55, prompt_cache_hit_tokens=25)

    loop._update_metrics(first, phase="GP")
    loop._update_metrics(warm, phase="GP")
    loop._update_metrics(c_phase, phase="C")

    by_phase = loop._summarize_cache_stats(loop._cache_phase_stats)
    by_bucket = loop._summarize_cache_stats(loop._cache_bucket_stats)

    assert by_phase["gp"]["calls"] == 2
    assert by_phase["gp"]["input_tokens"] == 300
    assert by_phase["gp"]["cache_hit_tokens"] == 150
    assert by_phase["gp"]["cache_hit_rate"] == 0.5
    assert by_phase["gp"]["zero_hit_calls"] == 1
    assert by_bucket["gp_first"]["cache_hit_tokens"] == 0
    assert by_bucket["gp_first"]["zero_hit_calls"] == 1
    assert by_bucket["gp_warm"]["cache_hit_tokens"] == 150
    assert by_bucket["gp_warm"]["cache_hit_rate"] == 0.75
    assert by_bucket["c"]["cache_hit_rate"] == 0.5
    assert loop.metrics.prompt_cache_hit_tokens == 175
    assert loop.metrics.g_tokens == 330
    assert loop.metrics.c_tokens == 55


def test_emit_llm_call_end_includes_cache_rate_and_bucket():
    loop = V4Loop.__new__(V4Loop)
    events = []

    async def run_case():
        async def callback(event, payload):
            events.append((event, payload))

        response = SimpleNamespace(
            finish_reason="stop",
            tool_calls=[],
            content="done",
            reasoning_content="think",
            input_tokens=200,
            output_tokens=30,
            total_tokens=230,
            prompt_cache_hit_tokens=120,
        )
        await loop._emit_llm_call_end(
            callback,
            "GP_PHASE",
            "gp_1",
            1,
            100.0,
            stream=True,
            response=response,
        )

    asyncio.run(run_case())

    assert events[0][0] == "llm_call_end"
    payload = events[0][1]
    assert payload["cache_hit_tokens"] == 120
    assert payload["cache_hit_rate"] == 0.6
    assert payload["cache_bucket"] == "gp_warm"


def test_c_phase_optional_ablation_and_pruning_failures_do_not_crash():
    class FailingVault:
        def sync_vector_matrix_incremental(self):
            return None

        def check_ablation_candidates(self, *args, **kwargs):
            raise RuntimeError("ablation unavailable")

        def get_ablation_observing_nodes(self, *args, **kwargs):
            raise RuntimeError("observation unavailable")

        def check_proactive_pruning_candidates(self, *args, **kwargs):
            raise RuntimeError("pruning unavailable")

    class FakeLoop(CPhaseMixin):
        C_PHASE_MAX_ITER = {"SKIP": 0}

        def __init__(self):
            self.vault = FailingVault()
            self.execution_active_nodes = []
            self.execution_active_node_roles = {}
            self._op_tool_outcomes = []
            self.blackboard = None
            self.inferred_signature = {}
            self.trace_id = None
            self.c_messages = []
            self.events = []

        async def _safe_callback(self, callback, event, data):
            self.events.append((event, data))

    loop = FakeLoop()
    asyncio.run(loop._run_c_phase(step_callback=None, mode="SKIP", g_final_response="done"))

    assert loop.events[0][0] == "c_phase_done"
    assert loop.events[0][1]["mode"] == "SKIP"
