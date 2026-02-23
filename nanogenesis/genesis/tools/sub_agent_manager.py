import asyncio
from typing import Dict, Any

class SubAgentManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.tasks = {}
            cls._instance.results = {}
        return cls._instance
        
    def register_task(self, task_id: str, coro_task: asyncio.Task):
        self.tasks[task_id] = coro_task
        
    def get_status(self, task_id: str) -> Dict[str, Any]:
        if task_id in self.results:
            return {"status": "completed", "result": self.results[task_id]}
            
        task = self.tasks.get(task_id)
        if not task:
            return {"status": "not_found", "message": f"Task {task_id} does not exist."}
            
        if task.done():
            try:
                result = task.result()
                self.results[task_id] = result
                return {"status": "completed", "result": result}
            except Exception as e:
                self.results[task_id] = f"Error: {e}"
                return {"status": "failed", "error": str(e)}
        else:
            return {"status": "running", "message": f"Task {task_id} is still executing..."}
