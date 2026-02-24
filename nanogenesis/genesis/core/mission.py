
import sqlite3
import json
import uuid
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class Mission:
    id: str
    objective: str
    status: str
    created_at: str
    updated_at: str
    context_snapshot: Dict[str, Any]
    parent_id: Optional[str] = None
    root_id: str = ""
    depth: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    children: List[str] = None # Runtime hydration only

    def __post_init__(self):
        if self.children is None:
            self.children = []

class MissionManager:
    """
    Manages high-level missions for the Agent.
    Handles persistence in the 'missions' table.
    Now supports Mission Context Tree (MCT) - Hierarchical Tasks.
    """
    
    def __init__(self, db_path: str = None):
        from pathlib import Path
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".nanogenesis" / "brain.sqlite"
            
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Ensure schema exists and is migrated"""
        conn = self._get_conn()
        try:
            # 1. Create missions table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    objective TEXT,
                    status TEXT,
                    context_snapshot TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    error_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    parent_id TEXT,
                    root_id TEXT,
                    depth INTEGER DEFAULT 0
                )
            """)
            
            # 2. Create decision_log table — records anchor selection decisions for deep reflection
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT,
                    created_at TEXT,
                    problem_type TEXT,
                    anchor_options TEXT,   -- JSON list of candidate anchors
                    chosen_anchor TEXT,    -- which anchor was selected
                    outcome TEXT,          -- 'success' | 'failed' | 'backtracked' | 'pending'
                    reasoning TEXT         -- brief note on why this anchor was chosen
                )
            """)
            
            # 3. Migration: Check for missing columns (for existing DBs)
            cursor = conn.execute("PRAGMA table_info(missions)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'parent_id' not in columns:
                conn.execute("ALTER TABLE missions ADD COLUMN parent_id TEXT")
            if 'root_id' not in columns:
                conn.execute("ALTER TABLE missions ADD COLUMN root_id TEXT")
            if 'depth' not in columns:
                conn.execute("ALTER TABLE missions ADD COLUMN depth INTEGER DEFAULT 0")
                
            conn.commit()
        except Exception as e:
            print(f"DB Init Error: {e}")
            pass
        finally:
            conn.close()


    def create_mission(self, objective: str, parent_id: str = None) -> Mission:
        """Create a new active mission (Root or Branch)"""
        mission_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        root_id = mission_id
        depth = 0
        
        if parent_id:
            parent = self.get_mission(parent_id)
            if parent:
                root_id = parent.root_id or parent.id
                depth = parent.depth + 1
        
        mission = Mission(
            id=mission_id,
            objective=objective,
            status="active",
            created_at=now,
            updated_at=now,
            context_snapshot={},
            parent_id=parent_id,
            root_id=root_id,
            depth=depth,
            error_count=0,
            last_error=None
        )
        
        conn = self._get_conn()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO missions (
                        id, objective, status, context_snapshot, 
                        created_at, updated_at, error_count, last_error,
                        parent_id, root_id, depth
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mission.id, mission.objective, mission.status, json.dumps(mission.context_snapshot), 
                    mission.created_at, mission.updated_at, mission.error_count, mission.last_error,
                    mission.parent_id, mission.root_id, mission.depth
                ))
        finally:
            conn.close()
            
        return mission

    def update_mission(self, mission_id: str, **kwargs):
        """Update specific fields of a mission"""
        if not kwargs:
            return
            
        # Ensure updated_at is set if not provided
        if "updated_at" not in kwargs:
             kwargs["updated_at"] = datetime.now().isoformat()

        # Construct SQL
        columns = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(mission_id)
        
        query = f"UPDATE missions SET {columns} WHERE id = ?"
        
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(query, values)
        finally:
            conn.close()

    def get_mission(self, mission_id: str) -> Optional[Mission]:
        """Get a specific mission by ID"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_mission(row)
            return None
        finally:
            conn.close()

    def get_active_mission(self) -> Optional[Mission]:
        """Get the current active mission (if any)"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM missions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                return self._row_to_mission(row)
            return None
        finally:
            conn.close()

    def get_mission_lineage(self, mission_id: str) -> List[Mission]:
        """Get the full path from Root to Current Mission"""
        lineage = []
        current_id = mission_id
        
        while current_id:
            mission = self.get_mission(current_id)
            if not mission:
                break
            lineage.insert(0, mission)
            current_id = mission.parent_id
            
        return lineage

    def _row_to_mission(self, row: sqlite3.Row) -> Mission:
        """Helper to convert DB row to Mission object"""
        # Handle potential missing columns during migration/legacy data
        keys = row.keys()
        return Mission(
            id=row['id'],
            objective=row['objective'],
            status=row['status'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            context_snapshot=json.loads(row['context_snapshot'] or '{}'),
            parent_id=row['parent_id'] if 'parent_id' in keys else None,
            root_id=row['root_id'] if 'root_id' in keys else (row['id'] if not row.get('parent_id') else ""),
            depth=row['depth'] if 'depth' in keys else 0,
            error_count=row['error_count'] or 0,
            last_error=row['last_error']
        )

    def list_missions(self, limit: int = 5) -> List[Mission]:
        """List recent missions"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM missions ORDER BY updated_at DESC LIMIT ?", (limit,))
            return [self._row_to_mission(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def backtrack_to_parent(self, failed_mission_id: str, error_summary: str = "") -> Optional[Mission]:
        """
        任务树回溯：将当前失败的任务标记为 failed，并重新激活父节点任务。
        
        这是贝叶斯回溯的核心行为：
          当前路径失败 → 爬回父节点 → 父节点重新 active → agent 用另一条路重试
        
        Args:
            failed_mission_id : 失败任务的 ID
            error_summary     : 错误摘要，写入 last_error 供下次 strategy_phase 参考
        
        Returns:
            父节点 Mission，如果是根节点则返回 None（无法再回溯）
        """
        failed = self.get_mission(failed_mission_id)
        if not failed:
            return None

        # 1. 标记当前任务为失败，记录原因
        self.update_mission(
            failed_mission_id,
            status="failed",
            last_error=error_summary[:500] if error_summary else "STRATEGIC_INTERRUPT",
            error_count=failed.error_count + 1
        )

        # 2. 尝试爬回父节点
        if not failed.parent_id:
            return None  # 已是根节点，无法再回溯

        parent = self.get_mission(failed.parent_id)
        if not parent:
            return None

        # 3. 重新激活父节点，让 agent 在父节点上下文中重新 strategy_phase
        self.update_mission(
            parent.id,
            status="active",
            last_error=f"子任务失败回溯: {failed.objective[:100]} → {error_summary[:200]}"
        )

        return self.get_mission(parent.id)

    def get_failed_children(self, parent_mission_id: str) -> List[str]:
        """返回指定父节点下所有已失败的子任务目标（供 strategy_phase 排除这些路径）"""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT objective FROM missions WHERE parent_id = ? AND status = 'failed'",
                (parent_mission_id,)
            )
            return [row['objective'] for row in cursor.fetchall()]
        finally:
            conn.close()

    # ── 决策日志 (Decision Log) ────────────────────────────────────────────

    def log_decision(
        self,
        mission_id: str,
        problem_type: str,
        anchor_options: List[str],
        chosen_anchor: str,
        reasoning: str = "",
    ) -> int:
        """
        记录一个 strategy_phase 的锚点选择决策。

        Args:
            mission_id    : 当前任务 ID
            problem_type  : 任务类型（code / system / media / web / general）
            anchor_options: 候选锚点列表（来自知识存量盘点）
            chosen_anchor : 实际选择的锚点/方法摘要
            reasoning     : 为什么选这个锚点（可选）

        Returns:
            新插入记录的 rowid
        """
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO decision_log
                        (mission_id, created_at, problem_type, anchor_options, chosen_anchor, outcome, reasoning)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        mission_id,
                        datetime.now().isoformat(),
                        problem_type,
                        json.dumps(anchor_options, ensure_ascii=False),
                        chosen_anchor[:300],
                        reasoning[:300],
                    ),
                )
                return cursor.lastrowid
        finally:
            conn.close()

    def update_decision_outcome(self, decision_id: int, outcome: str) -> None:
        """
        更新决策结果。

        Args:
            decision_id: log_decision() 返回的 rowid
            outcome    : 'success' | 'failed' | 'backtracked'
        """
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(
                    "UPDATE decision_log SET outcome = ? WHERE id = ?",
                    (outcome, decision_id),
                )
        finally:
            conn.close()

    def get_recent_decisions(self, limit: int = 20) -> List[Dict]:
        """
        读取最近 N 条决策记录，用于深度反思。
        只返回已有结果（非 pending）的记录，因为 pending 还无法用于学习。
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """
                SELECT id, mission_id, created_at, problem_type,
                       anchor_options, chosen_anchor, outcome, reasoning
                FROM decision_log
                WHERE outcome != 'pending'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "mission_id": r["mission_id"],
                    "created_at": r["created_at"],
                    "problem_type": r["problem_type"],
                    "anchor_options": json.loads(r["anchor_options"] or "[]"),
                    "chosen_anchor": r["chosen_anchor"],
                    "outcome": r["outcome"],
                    "reasoning": r["reasoning"],
                }
                for r in rows
            ]
        finally:
            conn.close()
