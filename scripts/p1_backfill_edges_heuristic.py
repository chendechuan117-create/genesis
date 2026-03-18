#!/usr/bin/env python3
import sys
import os
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from genesis.v4.manager import NodeVault

logging.basicConfig(level=logging.INFO, format='%(message)s')

def backfill():
    vault = NodeVault()
    nodes = vault._conn.execute("SELECT node_id, type, title, resolves, prerequisites, metadata_signature FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'").fetchall()
    
    nodes_dict = {n['node_id']: dict(n) for n in nodes}
    edges_created = 0
    
    for n_id, n in nodes_dict.items():
        # 1. 尝试匹配 prerequisites -> REQUIRES 边
        reqs = n.get('prerequisites')
        if reqs:
            for req_id in [r.strip() for r in reqs.split(',') if r.strip()]:
                if req_id in nodes_dict:
                    vault.add_edge(n_id, req_id, 'REQUIRES', 1.0)
                    edges_created += 1
                    print(f"Edge: {n_id} -[REQUIRES]-> {req_id}")
                    
        # 2. 尝试匹配 resolves -> RESOLVES 边（双向启发）
        res = n.get('resolves')
        if res:
            # 找到其他相同 resolves 的节点，建立 RELATED_TO
            for other_id, other_n in nodes_dict.items():
                if other_id != n_id and other_n.get('resolves') == res:
                    vault.add_edge(n_id, other_id, 'RELATED_TO', 0.8)
                    edges_created += 1
                    print(f"Edge: {n_id} -[RELATED_TO]-> {other_id} (same resolves)")
                    
    # 3. 按照 tags 和 signature 建立弱关联
    for i, (n1_id, n1) in enumerate(nodes_dict.items()):
        sig1 = json.loads(n1['metadata_signature']) if n1.get('metadata_signature') else {}
        for j, (n2_id, n2) in enumerate(nodes_dict.items()):
            if i >= j: continue
            
            sig2 = json.loads(n2['metadata_signature']) if n2.get('metadata_signature') else {}
            
            # 如果 framework 或 error_kind 一样，建立 RELATED_TO 弱关联
            matched = False
            for key in ['framework', 'error_kind', 'task_kind', 'target_kind']:
                v1 = sig1.get(key)
                v2 = sig2.get(key)
                if v1 and v2 and v1 == v2 and v1 not in ['unknown', 'general']:
                    matched = True
                    break
            
            if matched:
                vault.add_edge(n1_id, n2_id, 'RELATED_TO', 0.3)
                edges_created += 1
                print(f"Edge: {n1_id} -[RELATED_TO]-> {n2_id} (shared signature)")

    print(f"\nDone! Heuristic backfill created {edges_created} edges.")

if __name__ == '__main__':
    backfill()
