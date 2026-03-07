import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import aiohttp
import json
from typing import Dict, Any, Optional

class N8nApiClientTool(Tool):
    @property
    def name(self) -> str:
        return "n8n_api_client"
        
    @property
    def description(self) -> str:
        return "n8n API客户端，用于测试连接、获取工作流信息和管理工作流"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "n8n实例的基础URL，例如 https://your-n8n-instance.com"},
                "api_key": {"type": "string", "description": "API密钥或JWT令牌"},
                "endpoint": {"type": "string", "description": "API端点，例如 /api/v1/workflows"},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "description": "HTTP方法", "default": "GET"},
                "data": {"type": "string", "description": "JSON格式的请求数据", "default": "{}"}
            },
            "required": ["base_url", "api_key", "endpoint"]
        }
        
    async def execute(self, base_url: str, api_key: str, endpoint: str, method: str = "GET", data: str = "{}") -> str:
        try:
            url = base_url.rstrip('/') + endpoint
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers) as response:
                        status = response.status
                        response_text = await response.text()
                elif method == "POST":
                    async with session.post(url, headers=headers, data=data) as response:
                        status = response.status
                        response_text = await response.text()
                elif method == "PUT":
                    async with session.put(url, headers=headers, data=data) as response:
                        status = response.status
                        response_text = await response.text()
                elif method == "DELETE":
                    async with session.delete(url, headers=headers) as response:
                        status = response.status
                        response_text = await response.text()
                else:
                    return f"错误: 不支持的HTTP方法: {method}"
                
                result = {
                    "status_code": status,
                    "url": url,
                    "response": response_text
                }
                
                # 尝试解析JSON响应
                try:
                    result["json_response"] = json.loads(response_text)
                except:
                    result["json_response"] = None
                
                return json.dumps(result, indent=2, ensure_ascii=False)
                
        except Exception as e:
            return f"调用n8n API时出错: {str(e)}"