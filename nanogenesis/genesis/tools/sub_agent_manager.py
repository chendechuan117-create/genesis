import asyncio
import threading
from typing import Dict, Any

class SubAgentManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.tasks = {}
                cls._instance.results = {}
                # Create a dedicated background event loop that survives Streamlit re-runs
                cls._instance._loop = asyncio.new_event_loop()
                cls._instance._thread = threading.Thread(
                    target=cls._instance._run_loop,
                    name="Genesis-SubAgent-Daemon",
                    daemon=True
                )
                cls._instance._thread.start()
            return cls._instance

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        
    def register_task(self, task_id: str, coro) -> None:
        """
        Registers a coroutine to run on the persistent background event loop.
        Uses run_coroutine_threadsafe to safely schedule from any thread.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        self.tasks[task_id] = future
        
    def get_status(self, task_id: str) -> Dict[str, Any]:
        if task_id in self.results:
            return {"status": "completed", "result": self.results[task_id]}
            
        future = self.tasks.get(task_id)
        if not future:
            return {"status": "not_found", "message": f"Task {task_id} does not exist."}
            
        if future.done():
            try:
                result = future.result()
                self.results[task_id] = result
                return {"status": "completed", "result": result}
            except Exception as e:
                self.results[task_id] = f"Error: {e}"
                return {"status": "failed", "error": str(e)}
        else:
            return {"status": "running", "message": f"Task {task_id} is still executing..."}
