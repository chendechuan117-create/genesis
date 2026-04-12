#!/usr/bin/env python3
"""
Patch LLM physics nodes: downgrade confidence and add uncertainty markers
to prevent Genesis from treating hypotheses as axioms.
"""
import sqlite3
import json
from pathlib import Path

DB_PATH = Path.home() / ".genesis" / "workshop_v4.sqlite"

PATCHES = {
    # Technical facts - keep high confidence
    "LESSON_LLM_PHYSICS_LAW4_CONTEXT_IS_REALITY": {
        "confidence_score": 0.90,
        "prefix": "[技术事实] ",
    },
    "LESSON_LLM_PHYSICS_LAW5_ABSOLUTE_DEATH": {
        "confidence_score": 0.90,
        "prefix": "[技术事实] ",
    },
    # Data-backed observation
    "LESSON_CURRENT_METADATA_CHIMERA": {
        "confidence_score": 0.80,
        "prefix": "[数据支撑的观察] ",
    },
    # Reasonable hypotheses - need verification
    "LESSON_LLM_PHYSICS_LAW1_TOKEN_EQUALITY": {
        "confidence_score": 0.55,
        "prefix": "[待验证假说·反例存在：位置编码和system prompt权重差异说明token不完全平等] ",
    },
    "LESSON_LLM_PHYSICS_LAW2_PARALLEL_PERCEPTION": {
        "confidence_score": 0.50,
        "prefix": "[待验证假说·反例存在：LLM存在recency bias和primacy bias，顺序确实有影响] ",
    },
    "LESSON_LLM_PHYSICS_LAW3_COOCCURRENCE": {
        "confidence_score": 0.55,
        "prefix": "[待验证假说·争议点：CoT推理表现暗示LLM可能有超越纯共现的能力] ",
    },
    "LESSON_LLM_PHYSICS_LAW6_OBSERVATION_OVER_REFLECTION": {
        "confidence_score": 0.50,
        "prefix": "[单次观察·样本量=1·需更多数据验证] ",
    },
    # Philosophical framings / proposals
    "LESSON_LLM_ECHO_MODEL": {
        "confidence_score": 0.40,
        "prefix": "[哲学框架·不可证伪·仅作思考方向参考] ",
    },
    "LESSON_METADATA_FIELD_MODEL": {
        "confidence_score": 0.35,
        "prefix": "[未验证提案·需要从基础定律严格推导验证是否成立] ",
    },
    "LESSON_LLM_SPECIES_WEAKNESSES": {
        "confidence_score": 0.45,
        "prefix": "[单次对话观察·可能是上下文特殊表现·需跨会话验证] ",
    },
}


def main():
    conn = sqlite3.connect(str(DB_PATH))
    patched = 0

    for node_id, patch in PATCHES.items():
        row = conn.execute(
            "SELECT title, human_translation FROM knowledge_nodes WHERE node_id = ?",
            [node_id],
        ).fetchone()
        if not row:
            print(f"  ⚠️ Not found: {node_id}")
            continue

        title, content = row
        new_content = patch["prefix"] + content
        sig = json.dumps({
            "validation_status": "unverified" if patch["confidence_score"] < 0.7 else "validated",
            "knowledge_state": "current",
        })

        conn.execute(
            "UPDATE knowledge_nodes SET human_translation=?, confidence_score=?, metadata_signature=? WHERE node_id=?",
            [new_content, patch["confidence_score"], sig, node_id],
        )
        patched += 1
        status = "事实" if patch["confidence_score"] >= 0.8 else "假说" if patch["confidence_score"] >= 0.5 else "框架"
        print(f"  📝 {status} (conf={patch['confidence_score']:.2f}): {node_id}")

    conn.commit()
    conn.close()
    print(f"\n📊 Patched {patched} nodes")


if __name__ == "__main__":
    main()
