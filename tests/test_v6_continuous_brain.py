import os
import json
import shutil
import tempfile
import sqlite3
import numpy as np
import pytest
from pathlib import Path

from genesis.v6.dataset_compiler import DatasetCompiler
from genesis.v6.brain import ContinuousBrain
from genesis.v4.surface import SurfaceExpander

class MockVault:
    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        
    def get_incoming_line_counts_batch(self, node_ids):
        return {nid: 2 for nid in node_ids}
        
    def get_incoming_count_percentile(self, percentile):
        return 2
        
    def get_excluded_ids(self, candidate_ids):
        return set()
        
    def get_virtual_saturation(self, node_ids):
        return []

@pytest.fixture
def temp_workspace():
    # Setup temporary directories and files
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test_workshop.sqlite"
    vocab_path = temp_dir / "v6_vocab.json"
    weights_path = temp_dir / "v6_brain_weights.npz"
    
    # Initialize a mock database
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE knowledge_nodes (
            node_id TEXT PRIMARY KEY,
            type TEXT,
            title TEXT,
            human_translation TEXT,
            tags TEXT,
            resolves TEXT,
            embedding TEXT,
            metadata_signature TEXT
        )
    """)
    
    # Insert mock nodes
    embedding_512 = [0.01 * (i % 10) for i in range(512)]
    conn.execute(
        "INSERT INTO knowledge_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "P_TEST_NODE_1", "CONTEXT", "FastAPI setup", "FastAPI setup", 
            "auto_managed", "api, setup", json.dumps(embedding_512), 
            json.dumps({"task_kind": "debug", "runtime": "python", "framework": "fastapi"})
        )
    )
    conn.execute(
        "INSERT INTO knowledge_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "P_TEST_NODE_2", "CONTEXT", "Playwright test fail", "Playwright test", 
            "auto_managed", "test", json.dumps(embedding_512), 
            json.dumps({"task_kind": "debug", "runtime": "node", "framework": "playwright", "error_kind": "network"})
        )
    )
    # Adding extra nodes so that label counts >= 3 threshold is reachable or we test min_count=1
    for i in range(3, 10):
        conn.execute(
            "INSERT INTO knowledge_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"P_TEST_NODE_{i}", "CONTEXT", "Docker config", "Docker setup", 
                "auto_managed", "docker", json.dumps(embedding_512), 
                json.dumps({"task_kind": "debug", "runtime": "python", "framework": "fastapi", "error_kind": "network"})
            )
        )
    conn.commit()
    conn.close()
    
    yield db_path, vocab_path, weights_path
    
    shutil.rmtree(temp_dir)

def test_v6_dataset_compiler(temp_workspace):
    db_path, vocab_path, _ = temp_workspace
    compiler = DatasetCompiler(db_path=db_path, vocab_path=vocab_path)
    
    # Load raw
    samples = compiler.load_raw_samples()
    assert len(samples) == 9
    assert samples[0]["node_id"] == "P_TEST_NODE_1"
    assert len(samples[0]["embedding"]) == 512
    
    # Build vocab (with min_count=1 to make sure all labels are included in test)
    compiler.build_vocabulary(samples, min_count=1)
    assert vocab_path.exists()
    assert len(compiler.index_to_label) > 0
    assert "framework:fastapi" in compiler.label_to_index
    
    # Compile
    X, Y = compiler.compile(samples)
    assert X.shape == (9, 512)
    assert Y.shape == (9, len(compiler.index_to_label))
    assert Y[0, compiler.label_to_index["framework:fastapi"]] == 1.0

def test_v6_continuous_brain(temp_workspace):
    db_path, vocab_path, weights_path = temp_workspace
    compiler = DatasetCompiler(db_path=db_path, vocab_path=vocab_path)
    samples = compiler.load_raw_samples()
    compiler.build_vocabulary(samples, min_count=1)
    X, Y = compiler.compile(samples)
    
    # Initialize brain
    brain = ContinuousBrain(
        input_dim=512, 
        hidden_dim=32, 
        output_dim=Y.shape[1], 
        weights_path=weights_path
    )
    
    # Forward and Backward passes
    A2 = brain.forward(X)
    assert A2.shape == (9, Y.shape[1])
    
    loss_start = brain.backward(Y, lr=0.1, lambda_decay=0.001)
    assert isinstance(loss_start, float)
    
    # Train and verify Loss decreases
    losses = brain.fit(X, Y, epochs=10, lr=0.5, lambda_decay=0.0001, verbose=False)
    assert losses[-1] < loss_start
    
    # Save and load weights
    brain.save_weights()
    assert weights_path.exists()
    
    new_brain = ContinuousBrain(
        input_dim=512, 
        hidden_dim=32, 
        output_dim=Y.shape[1], 
        weights_path=weights_path
    )
    loaded = new_brain.load_weights()
    assert loaded is True
    assert np.allclose(brain.W1, new_brain.W1)

def test_surface_expander_active_gating_bypass(temp_workspace):
    db_path, vocab_path, weights_path = temp_workspace
    
    # Mocking environment variable to bypass
    os.environ["V6_ACTIVE_GATING"] = "0"
    
    vault = MockVault(db_path)
    expander = SurfaceExpander(vault)
    
    # Ensure it returns unmodified candidates when gating is disabled
    c_ids = {"P_TEST_NODE_1", "P_TEST_NODE_2"}
    filtered = expander._v6_gating_filter(c_ids, "FastAPI connection issues")
    assert filtered == c_ids
