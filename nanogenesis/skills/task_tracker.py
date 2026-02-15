import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

class TaskTracker:
    """任务跟踪工具，用于记录、查询和管理任务状态"""
    
    def __init__(self, data_file: str = "tasks.json"):
        self.data_file = data_file
        self.tasks = self._load_tasks()
    
    def _load_tasks(self) -> List[Dict]:
        """从文件加载任务数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def _save_tasks(self):
        """保存任务数据到文件"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=2)
    
    def save_task(self, title: str, description: str, status: str = "pending", 
                  category: str = "general", tags: List[str] = None) -> Dict:
        """保存新任务"""
        task_id = len(self.tasks) + 1
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "status": status,
            "category": category,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        self.tasks.append(task)
        self._save_tasks()
        return task
    
    def get_last_task(self) -> Optional[Dict]:
        """获取最后一个任务"""
        if self.tasks:
            return self.tasks[-1]
        return None
    
    def get_task_by_id(self, task_id: int) -> Optional[Dict]:
        """根据ID获取任务"""
        for task in self.tasks:
            if task.get("id") == task_id:
                return task
        return None
    
    def list_tasks(self, status: str = None, category: str = None, 
                   limit: int = 10) -> List[Dict]:
        """列出任务，支持过滤"""
        filtered_tasks = self.tasks
        
        if status:
            filtered_tasks = [t for t in filtered_tasks if t.get("status") == status]
        
        if category:
            filtered_tasks = [t for t in filtered_tasks if t.get("category") == category]
        
        return filtered_tasks[-limit:] if limit else filtered_tasks
    
    def update_task_status(self, task_id: int, status: str, notes: str = None) -> Optional[Dict]:
        """更新任务状态"""
        for task in self.tasks:
            if task.get("id") == task_id:
                task["status"] = status
                task["updated_at"] = datetime.now().isoformat()
                if notes:
                    task["notes"] = task.get("notes", []) + [{
                        "timestamp": datetime.now().isoformat(),
                        "content": notes
                    }]
                self._save_tasks()
                return task
        return None
    
    def search_tasks(self, keyword: str) -> List[Dict]:
        """搜索任务"""
        results = []
        keyword_lower = keyword.lower()
        
        for task in self.tasks:
            if (keyword_lower in task.get("title", "").lower() or 
                keyword_lower in task.get("description", "").lower() or
                any(keyword_lower in tag.lower() for tag in task.get("tags", []))):
                results.append(task)
        
        return results

# 工具类定义
class TaskTrackerTool:
    name = "task_tracker"
    description = "任务跟踪工具，用于记录、查询和管理任务状态"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "get_last", "list", "update", "search", "get_by_id"],
                "description": "操作类型"
            },
            "title": {
                "type": "string",
                "description": "任务标题（仅save需要）"
            },
            "description": {
                "type": "string",
                "description": "任务描述（仅save需要）"
            },
            "status": {
                "type": "string",
                "description": "任务状态（save/update需要）",
                "default": "pending"
            },
            "category": {
                "type": "string",
                "description": "任务分类",
                "default": "general"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "任务标签"
            },
            "task_id": {
                "type": "integer",
                "description": "任务ID（update/get_by_id需要）"
            },
            "keyword": {
                "type": "string",
                "description": "搜索关键词（search需要）"
            },
            "notes": {
                "type": "string",
                "description": "更新备注（update需要）"
            },
            "limit": {
                "type": "integer",
                "description": "返回数量限制",
                "default": 10
            }
        },
        "required": ["action"]
    }
    
    def __init__(self):
        self.tracker = TaskTracker()
    
    def execute(self, action: str, **kwargs) -> Dict:
        """执行任务跟踪操作"""
        try:
            if action == "save":
                return self._save_task(**kwargs)
            elif action == "get_last":
                return self._get_last_task()
            elif action == "list":
                return self._list_tasks(**kwargs)
            elif action == "update":
                return self._update_task(**kwargs)
            elif action == "search":
                return self._search_tasks(**kwargs)
            elif action == "get_by_id":
                return self._get_task_by_id(**kwargs)
            else:
                return {"error": f"未知操作: {action}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _save_task(self, title: str, description: str, **kwargs) -> Dict:
        status = kwargs.get("status", "pending")
        category = kwargs.get("category", "general")
        tags = kwargs.get("tags", [])
        
        task = self.tracker.save_task(title, description, status, category, tags)
        return {
            "success": True,
            "message": f"任务已保存 (ID: {task['id']})",
            "task": task
        }
    
    def _get_last_task(self) -> Dict:
        task = self.tracker.get_last_task()
        if task:
            return {"success": True, "task": task}
        return {"success": False, "message": "暂无任务记录"}
    
    def _list_tasks(self, **kwargs) -> Dict:
        status = kwargs.get("status")
        category = kwargs.get("category")
        limit = kwargs.get("limit", 10)
        
        tasks = self.tracker.list_tasks(status, category, limit)
        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks
        }
    
    def _update_task(self, task_id: int, status: str, **kwargs) -> Dict:
        notes = kwargs.get("notes")
        task = self.tracker.update_task_status(task_id, status, notes)
        if task:
            return {
                "success": True,
                "message": f"任务 {task_id} 状态已更新为 {status}",
                "task": task
            }
        return {"success": False, "message": f"未找到任务 ID: {task_id}"}
    
    def _search_tasks(self, keyword: str, **kwargs) -> Dict:
        tasks = self.tracker.search_tasks(keyword)
        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks
        }
    
    def _get_task_by_id(self, task_id: int, **kwargs) -> Dict:
        task = self.tracker.get_task_by_id(task_id)
        if task:
            return {"success": True, "task": task}
        return {"success": False, "message": f"未找到任务 ID: {task_id}"}