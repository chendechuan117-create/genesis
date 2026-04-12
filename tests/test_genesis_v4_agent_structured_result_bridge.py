from genesis.core.base import PerformanceMetrics
from genesis.v4.unified_response import ExecutionStatus
from genesis.v4.agent import GenesisV4


class DummyTracer:
    def start_trace(self, user_input):
        return "trace-123"

    def end_trace(self, *args, **kwargs):
        return None


class FakeLoop:
    def __init__(self, *args, **kwargs):
        self._cursor = {"frontier": ["structured"]}

    async def run(self, **kwargs):
        metrics = PerformanceMetrics(success=True, iterations=3, total_time=0.5)
        return (
            "final text",
            metrics,
            {
                "summary": "structured summary",
                "findings": "structured findings",
                "changes_made": ["genesis/v4/agent.py"],
                "artifacts": ["runtime/report.txt"],
                "open_questions": ["next step?"],
            },
        )

    def export_knowledge_cursor(self):
        return self._cursor

    def get_phase_trace(self):
        return {"gp": [], "c": []}

    def get_knowledge_state(self):
        return {"verified_facts": ["structured result surfaced"]}


async def _run_case(monkeypatch):
    import genesis.v4.agent as agent_module

    monkeypatch.setattr(agent_module, "V4Loop", FakeLoop)
    monkeypatch.setattr(agent_module.Tracer, "get_instance", lambda: DummyTracer())

    agent = GenesisV4(tools=object(), provider=object(), max_iterations=10)
    response = await agent.process("bridge structured result")

    assert response.status == ExecutionStatus.SUCCESS
    assert response.response == "final text"
    assert response.summary == "structured summary"
    assert response.findings == "structured findings"
    assert response.changes_made == ["genesis/v4/agent.py"]
    assert response.artifacts == ["runtime/report.txt"]
    assert response.open_questions == ["next step?"]
    assert response.trace_id == "trace-123"
    assert response.knowledge_state == {"verified_facts": ["structured result surfaced"]}


def test_genesis_v4_process_surfaces_structured_loop_result(monkeypatch):
    import asyncio

    asyncio.run(_run_case(monkeypatch))
