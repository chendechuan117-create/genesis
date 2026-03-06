"""
Genesis V4 - 认知装配师 (The Factory Manager G)
核心概念：用元信息装配 Op，并对外输出 B面 翻译。
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / '.nanogenesis' / 'workshop_v4.sqlite'

class NodeVault:
    """万物皆节点库 (Node System)"""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._ensure_db()
        
    def _ensure_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                node_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                machine_payload TEXT NOT NULL,
                human_translation TEXT NOT NULL,
                tags TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            conn.commit()

    def get_all_machine_nodes(self) -> str:
        """把所有节点的 A 面提取出来，喂给 G 看 (极度压缩)"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT node_id, type, machine_payload, tags FROM knowledge_nodes ORDER BY usage_count DESC").fetchall()
            
        # Format as compact string to save tokens
        lines = ["[AVAILABLE_NODES]"]
        for r in rows:
            lines.append(f"<{r['type']}> [{r['node_id']}] Tags:{r['tags']} | Payload:{r['machine_payload']}")
        return "\n".join(lines)
        
    def translate_nodes(self, node_ids: List[str]) -> Dict[str, str]:
        """根据传来的节点 ID，返回人类可读的 B 面 (human_translation)"""
        if not node_ids:
            return {}
            
        placeholders = ','.join('?' * len(node_ids))
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT node_id, human_translation FROM knowledge_nodes WHERE node_id IN ({placeholders})", tuple(node_ids)).fetchall()
            
        return {r['node_id']: r['human_translation'] for r in rows}

    def increment_usage(self, node_ids: List[str]):
        """增加节点权重（适者生存）"""
        if not node_ids:
            return
        placeholders = ','.join('?' * len(node_ids))
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(f"UPDATE knowledge_nodes SET usage_count = usage_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id IN ({placeholders})", tuple(node_ids))
            conn.commit()

class FactoryManager:
    """厂长 G"""
    def __init__(self):
        self.vault = NodeVault()
        
    def build_system_prompt(self) -> str:
        """G 的出厂设定"""
        node_catalog = self.vault.get_all_machine_nodes()
        
        return f"""You are Genesis Factory Manager (V4 Glassbox Architecture).
Your core purpose is NOT to answer the user directly, but to ASSEMBLE cognitive nodes into an operation pipeline (Op).
You must output a single JSON block outlining your assembly plan BEFORE taking any action.

{node_catalog}

[INSTRUCTION]
When the user gives a request:
1. Select the necessary nodes from [AVAILABLE_NODES] (Combine TOOLs, CONTEXTs, and LESSONs).
2. Formulate a sequence of execution steps using these nodes.
3. Output ONLY the following JSON structure:
{{
    "op_intent": "Brief description of the overall goal",
    "active_nodes": ["SYS_TOOL_WEB", "CTX_USER_STYLE"], 
    "execution_plan": [
        "1. [SYS_TOOL_WEB] Search for XYZ",
        "2. [INTERNAL] Apply CTX_USER_STYLE to format results"
    ]
}}
Do NOT output anything outside of the JSON block.
"""

    def render_blueprint_for_human(self, plan_json: str) -> str:
        """解析 G 输出的 JSON，并渲染成极具启发性的 B面 玻璃盒 UI"""
        try:
            plan = json.loads(plan_json)
            nodes = plan.get("active_nodes", [])
            translations = self.vault.translate_nodes(nodes)
            
            output = [
                "🔧 **[厂长已完成装配]**",
                f"**目标：** {plan.get('op_intent', '未定义')}",
                "",
                "**已加载认知节点：**"
            ]
            
            for node_id in nodes:
                trans = translations.get(node_id, "未知节点定义")
                prefix = "🔌" if "TOOL" in node_id else "🧠" if "CTX" in node_id else "📖"
                output.append(f"{prefix} `[{node_id}]` {trans}")
                
            output.append("")
            output.append("**执行管线 (Op Sequence)：**")
            for step in plan.get("execution_plan", []):
                output.append(f"  ⚡ {step}")
                
            return "\n".join(output)
            
        except json.JSONDecodeError:
            return "⚠️ 装配图纸解析失败。厂长输出了非标准 JSON 格式。"
        except Exception as e:
            return f"⚠️ 渲染图纸时发生内部异常: {e}"
