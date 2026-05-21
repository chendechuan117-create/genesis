import os
import json
import sqlite3
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Any

DEFAULT_NODEVAULT_DB = Path.home() / ".nanogenesis" / "workshop_v4.sqlite"
DEFAULT_VOCAB_PATH = Path(__file__).resolve().parents[2] / "runtime" / "v6_label_vocabulary.json"

TARGET_FIELDS = ["error_kind", "framework", "task_kind", "runtime", "target_kind"]

class DatasetCompiler:
    def __init__(self, db_path: Path = DEFAULT_NODEVAULT_DB, vocab_path: Path = DEFAULT_VOCAB_PATH):
        self.db_path = db_path
        self.vocab_path = vocab_path
        self.label_to_index: Dict[str, int] = {}
        self.index_to_label: List[str] = []

    def load_raw_samples(self) -> List[Dict[str, Any]]:
        """从 SQLite 数据库加载具有嵌入和元标签的原始节点数据"""
        if not self.db_path.exists():
            raise FileNotFoundError(f"NodeVault DB not found at: {self.db_path}")
            
        conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT node_id, embedding, metadata_signature 
                FROM knowledge_nodes 
                WHERE embedding IS NOT NULL 
                  AND TRIM(embedding) != ''
                  AND metadata_signature IS NOT NULL
                  AND TRIM(metadata_signature) != ''
                  AND TRIM(metadata_signature) != '{}'
                  AND node_id NOT LIKE 'MEM_CONV%'
                """
            ).fetchall()
            
            samples = []
            for r in rows:
                try:
                    embedding = json.loads(r["embedding"])
                    sig = json.loads(r["metadata_signature"])
                    if len(embedding) == 512 and isinstance(sig, dict):
                        samples.append({
                            "node_id": r["node_id"],
                            "embedding": embedding,
                            "signature": sig
                        })
                except Exception:
                    continue
            return samples
        finally:
            conn.close()

    def build_vocabulary(self, samples: List[Dict[str, Any]], min_count: int = 3) -> None:
        """从高频的 5 个关键特征标签中构建扁平的 102 维稳定词表并持久化保存"""
        from collections import Counter
        counts = Counter()
        
        for s in samples:
            sig = s["signature"]
            for field in TARGET_FIELDS:
                val = sig.get(field)
                if val:
                    if isinstance(val, list):
                        for v in val:
                            counts[f"{field}:{str(v).strip().lower()}"] += 1
                    else:
                        counts[f"{field}:{str(val).strip().lower()}"] += 1
                        
        # 筛选稳定标签
        stable_labels = sorted([l for l, c in counts.items() if c >= min_count])
        
        self.label_to_index = {label: i for i, label in enumerate(stable_labels)}
        self.index_to_label = stable_labels
        
        # 保存词表字典
        self.vocab_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.vocab_path, "w", encoding="utf-8") as f:
            json.dump({
                "label_to_index": self.label_to_index,
                "index_to_label": self.index_to_label,
                "fields_tracked": TARGET_FIELDS,
                "total_labels": len(stable_labels)
            }, f, ensure_ascii=False, indent=2)

    def load_vocabulary(self) -> bool:
        """从本地 JSON 加载词表（如果已存在）"""
        if not self.vocab_path.exists():
            return False
        with open(self.vocab_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.label_to_index = data["label_to_index"]
            self.index_to_label = data["index_to_label"]
        return True

    def compile(self, samples: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
        """将加载的样本和词表编译成 NumPy 训练张量 [X_state, Y_target]"""
        if not self.label_to_index:
            self.build_vocabulary(samples)
            
        N = len(samples)
        V = len(self.index_to_label)
        
        X = np.zeros((N, 512), dtype=np.float32)
        Y = np.zeros((N, V), dtype=np.float32)
        
        for i, s in enumerate(samples):
            X[i] = np.array(s["embedding"], dtype=np.float32)
            
            sig = s["signature"]
            for field in TARGET_FIELDS:
                val = sig.get(field)
                if val:
                    vals = val if isinstance(val, list) else [val]
                    for v in vals:
                        label_key = f"{field}:{str(v).strip().lower()}"
                        if label_key in self.label_to_index:
                            Y[i, self.label_to_index[label_key]] = 1.0
                            
        return X, Y

def compile_now() -> Tuple[np.ndarray, np.ndarray]:
    compiler = DatasetCompiler()
    samples = compiler.load_raw_samples()
    X, Y = compiler.compile(samples)
    print(f"Dataset compiled: X.shape={X.shape}, Y.shape={Y.shape}")
    return X, Y

if __name__ == "__main__":
    compile_now()
