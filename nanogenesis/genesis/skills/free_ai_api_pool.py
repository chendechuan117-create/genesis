import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool


class FreeAIAPIPool(Tool):
    @property
    def name(self):
        return "free_ai_api_pool"
    
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
        # API配置
        apis = {
            "huggingface": {
                "url": "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1",
                "headers": {"Authorization": "Bearer YOUR_HF_TOKEN"},
                "payload": {"inputs": prompt, "parameters": {"max_length": max_tokens}}
            },
            "openrouter": {
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "headers": {"Authorization": "Bearer YOUR_OPENROUTER_KEY"},
                "payload": {
                    "model": "mistralai/mistral-7b-instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens
                }
            }
        }
        
        # 根据偏好选择API
        if api_preference == "auto":
            # 自动选择逻辑（简单轮询）
            import random
            selected = random.choice(list(apis.keys()))
        else:
            selected = api_preference
        
        try:
            import aiohttp
            import json
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    apis[selected]["url"],
                    headers=apis[selected]["headers"],
                    json=apis[selected]["payload"]
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return f"✅ {selected} API响应: {str(result)[:500]}"
                    else:
                        return f"❌ {selected} API失败: {response.status}"
        except Exception as e:
            return f"⚠️ API调用错误: {str(e)}"
