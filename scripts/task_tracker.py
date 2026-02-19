import json
import os
from datetime import datetime

class TaskTracker:
    def __init__(self, data_file="tasks.json"):
        self.data_file = data_file
        self.tasks = self._load_tasks()
    
    def _load_tasks(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_tasks(self):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=2)
    
    def save_task(self, title, description, status="pending", category="general", tags=None):
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
    
    def get_last_task(self):
        if self.tasks:
            return self.tasks[-1]
        return None
    
    def list_tasks(self, status=None, category=None, limit=10):
        filtered = self.tasks
        
        if status:
            filtered = [t for t in filtered if t.get("status") == status]
        
        if category:
            filtered = [t for t in filtered if t.get("category") == category]
        
        return filtered[-limit:] if limit else filtered

# 创建实例并记录当前任务
tracker = TaskTracker()
tracker.save_task(
    title="询问上个任务",
    description="用户询问'说说上个任务'，系统正在创建任务跟踪工具来解决跨会话记忆问题",
    status="in_progress",
    category="system",
    tags=["记忆", "任务跟踪", "系统升级"]
)

print("任务跟踪系统已初始化")
print(f"当前任务: {tracker.get_last_task()['title']}")