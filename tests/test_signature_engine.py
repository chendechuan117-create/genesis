"""
契约测试：SignatureEngine

验证（不依赖数据库/NodeVault——用 in-memory SQLite 隔离）：
1. 初始化不崩溃
2. normalize / parse / render / merge 基本契约
3. infer 从文本推断签名
4. infer_from_artifacts 从文件路径推断
5. signature_values 辅助函数
6. resolve_* 状态解析
"""

import sys
import os
import sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from genesis.v4.signature_engine import SignatureEngine


def _make_engine():
    """创建一个使用 in-memory SQLite 的测试引擎（无需 NodeVault）"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # 创建 SignatureEngine 依赖的最小表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_nodes (
            node_id TEXT PRIMARY KEY,
            type TEXT,
            title TEXT,
            metadata_signature TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS learned_signature_markers (
            dim_key TEXT,
            marker_value TEXT,
            source_persona TEXT DEFAULT '',
            hit_count INTEGER DEFAULT 1,
            PRIMARY KEY (dim_key, marker_value)
        )
    """)
    conn.commit()
    engine = SignatureEngine(conn, vault=None)
    engine.initialize()
    return engine


def test_initialize():
    engine = _make_engine()
    assert engine._dim_registry is not None
    assert engine._learned_markers is not None


def test_normalize_empty():
    engine = _make_engine()
    assert engine.normalize(None) == {}
    assert engine.normalize("") == {}
    assert engine.normalize({}) == {}


def test_normalize_preserves_known_fields():
    engine = _make_engine()
    sig = {"os_family": "arch", "language": "python"}
    result = engine.normalize(sig)
    assert result["os_family"] == "arch"
    assert result["language"] == "python"


def test_normalize_from_json_string():
    engine = _make_engine()
    result = engine.normalize('{"runtime": "docker"}')
    assert result["runtime"] == "docker"


def test_parse_is_alias_for_normalize():
    engine = _make_engine()
    sig = {"task_kind": "debug"}
    assert engine.parse(sig) == engine.normalize(sig)


def test_render_empty():
    engine = _make_engine()
    assert engine.render(None) == ""
    assert engine.render({}) == ""


def test_render_produces_pipe_separated():
    engine = _make_engine()
    result = engine.render({"os_family": "arch", "language": "python"})
    assert "|" in result
    assert "os_family=arch" in result
    assert "language=python" in result


def test_merge_combines_signatures():
    engine = _make_engine()
    result = engine.merge(
        {"os_family": "arch"},
        {"language": "python"},
        {"runtime": "docker"}
    )
    assert result.get("os_family") == "arch"
    assert result.get("language") == "python"
    assert result.get("runtime") == "docker"


def test_merge_deduplicates_values():
    engine = _make_engine()
    result = engine.merge(
        {"language": "python"},
        {"language": "python"}
    )
    assert result["language"] == "python"  # 不应变成列表


def test_signature_values_basic():
    engine = _make_engine()
    assert engine.signature_values({"key": "a"}, "key") == ["a"]
    assert engine.signature_values({"key": ["a", "b"]}, "key") == ["a", "b"]
    assert engine.signature_values({}, "key") == []
    assert engine.signature_values(None, "key") == []


def test_signature_values_splits_csv():
    engine = _make_engine()
    assert engine.signature_values({"key": "a, b, c"}, "key") == ["a", "b", "c"]


def test_infer_os_family():
    engine = _make_engine()
    result = engine.infer("我在 arch linux 上遇到了 pacman 的问题")
    assert result.get("os_family") == "arch"


def test_infer_runtime():
    engine = _make_engine()
    result = engine.infer("docker-compose up 之后容器报错")
    assert "docker" in str(result.get("runtime", ""))


def test_infer_language():
    engine = _make_engine()
    result = engine.infer("python pip install 失败")
    assert "python" in str(result.get("language", ""))


def test_infer_task_kind():
    engine = _make_engine()
    result = engine.infer("部署到 production 服务器")
    assert result.get("task_kind") == "deploy"


def test_infer_empty_input():
    engine = _make_engine()
    assert engine.infer("") == {}
    assert engine.infer("  ") == {}


def test_infer_from_artifacts_python():
    engine = _make_engine()
    result = engine.infer_from_artifacts(["requirements.txt", "main.py"])
    assert "python" in str(result.get("language", ""))


def test_infer_from_artifacts_docker():
    engine = _make_engine()
    result = engine.infer_from_artifacts(["Dockerfile", "docker-compose.yml"])
    assert "docker" in str(result.get("runtime", ""))


def test_infer_from_artifacts_empty():
    engine = _make_engine()
    assert engine.infer_from_artifacts([]) == {}
    assert engine.infer_from_artifacts(None) == {}


def test_resolve_validation_status():
    engine = _make_engine()
    assert engine.resolve_validation_status({"validation_status": "verified"}) == "validated"
    assert engine.resolve_validation_status({"validation_status": "unverified"}) == "unverified"


def test_resolve_knowledge_state():
    engine = _make_engine()
    assert engine.resolve_knowledge_state({"knowledge_state": "current"}) == "current"
    assert engine.resolve_knowledge_state({"knowledge_state": "historical"}) == "historical"


def test_learn_and_use_marker():
    engine = _make_engine()
    # Learn a new marker
    result = engine.learn_signature_marker("custom_dim", "mymarker", "test")
    assert result is True
    # Should now infer using the learned marker
    inferred = engine.infer("this text contains mymarker keyword")
    assert inferred.get("custom_dim") == "mymarker"


def test_learn_marker_rejects_bad_input():
    engine = _make_engine()
    assert engine.learn_signature_marker("", "val") is False
    assert engine.learn_signature_marker("key", "") is False
    assert engine.learn_signature_marker("key", "x") is False  # too short
    assert engine.learn_signature_marker("Bad Key!", "val") is False  # invalid chars


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  ✅ {t.__name__}")
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
