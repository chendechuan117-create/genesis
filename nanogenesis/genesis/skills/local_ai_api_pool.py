import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool


class LocalAIAPIPoolTool(Tool):
    @property
    def name(self):
        return "local_ai_api_pool"
    
    @property
    def description(self):
        return "本地AI API池，使用Ollama或本地模型，完全免费"
    
    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "输入提示"},
                "backend": {"type": "string", "enum": ["ollama", "localai", "transformers"], "default": "ollama", "description": "后端选择"},
                "model": {"type": "string", "description": "模型名称", "default": "llama2"},
                "max_tokens": {"type": "integer", "default": 100, "description": "最大token数"}
            },
            "required": ["prompt"]
        }
    
    async def execute(self, prompt, backend="ollama", model="llama2", max_tokens=100):
        import subprocess
        import json
        
        if backend == "ollama":
            try:
                # 调用Ollama本地API
                cmd = ["ollama", "run", model, prompt]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return result.stdout if result.stdout else "Ollama响应为空"
            except Exception as e:
                return f"Ollama调用失败: {str(e)}"
        else:
            return f"{backend}后端暂未实现，建议使用ollama"
