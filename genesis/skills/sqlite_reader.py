import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import sqlite3
import json

class SqliteReader(Tool):
    @property
    def name(self) -> str:
        return "sqlite_reader"
        
    @property
    def description(self) -> str:
        return "读取SQLite数据库文件并执行查询"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "SQLite数据库文件路径"},
                "query": {"type": "string", "description": "SQL查询语句"}
            },
            "required": ["db_path", "query"]
        }
        
    async def execute(self, db_path: str, query: str) -> str:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(query)
            
            # 获取列名
            column_names = [description[0] for description in cursor.description]
            
            # 获取所有行
            rows = cursor.fetchall()
            
            conn.close()
            
            # 格式化结果
            result = []
            for row in rows:
                row_dict = {}
                for i, col in enumerate(column_names):
                    row_dict[col] = row[i]
                result.append(row_dict)
            
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            return f"查询错误: {str(e)}"