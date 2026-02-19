
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
            # 1. Create Table if not exists
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
            
            # 2. Migration: Check for missing columns (for existing DBs)
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
            # Log error but don't crash, though table creation failure is critical
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
