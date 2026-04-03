from genesis.core.base import PerformanceMetrics
from genesis.v4.unified_response import UnifiedResponse, ExecutionStatus


def test_from_op_result_accepts_dict_op_result_partial_status():
    metrics = PerformanceMetrics(success=True)

    response = UnifiedResponse.from_op_result(
        response_text="ok",
        metrics=metrics,
        op_result={
            "status": "PARTIAL",
            "summary": "partial summary",
            "findings": "found",
            "changes_made": ["a.py"],
            "artifacts": ["artifact.txt"],
            "open_questions": ["next?"],
        },
    )

    assert response.status == ExecutionStatus.PARTIAL
    assert response.success is True
    assert response.summary == "partial summary"
    assert response.findings == "found"
    assert response.changes_made == ["a.py"]
    assert response.artifacts == ["artifact.txt"]
    assert response.open_questions == ["next?"]


def test_from_op_result_tolerates_sparse_dict_op_result():
    metrics = PerformanceMetrics(success=True)

    response = UnifiedResponse.from_op_result(
        response_text="ok",
        metrics=metrics,
        op_result={"status": "SUCCESS"},
    )

    assert response.status == ExecutionStatus.SUCCESS
    assert response.summary is None
    assert response.findings is None
    assert response.changes_made is None
    assert response.artifacts is None
    assert response.open_questions is None
