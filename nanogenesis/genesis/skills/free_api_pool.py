import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool


class FreeAPIPoolTool(Tool):
    @property
    def name(self):
        return "free_api_pool"
    
    @property
    def description(self):
        return "免费AI API池，为子代理提供运行耗材"
    
    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "输入提示"},
                "api_preference": {"type": "string", "enum": ["huggingface", "openrouter", "replicate", "auto"], "default": "auto", "description": "API偏好"},
                "max_tokens": {"type": "integer", "default": 100, "description": "最大token数"}
            },
            "required": ["prompt"]
        }
    
    async def execute(self, prompt, api_preference="auto", max_tokens=100):
        # 这里实现多API调用逻辑
        # 1. 根据偏好选择API
        # 2. 调用对应API
        # 3. 返回结果
        
        if api_preference == "huggingface":
            # 调用Hugging Face API
            return "Hugging Face API响应（示例）"
        elif api_preference == "openrouter":
            # 调用OpenRouter API
            return "OpenRouter API响应（示例）"
        else:
            # 自动选择
            return "自动选择API响应（示例）"
