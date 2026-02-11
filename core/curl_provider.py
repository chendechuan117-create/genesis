"""
Curl Provider - 使用 curl 调用 API（不依赖 LiteLLM）
"""

import subprocess
import json
from typing import List, Dict, Any, Optional
import logging
from .base import LLMProvider, LLMResponse


logger = logging.getLogger(__name__)


class CurlProvider(LLMProvider):
    """基于 curl 的 LLM Provider"""
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        default_model: str = "deepseek-chat"
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.default_model = default_model
    
    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> LLMResponse:
        """调用 API"""
        
        model = model or self.default_model
        
        # 构建请求数据
        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        
        if tools:
            data["tools"] = tools
        
        # 使用 curl 调用
        cmd = [
            'curl', '-s', '-X', 'POST',
            f'{self.base_url}/v1/chat/completions',
            '-H', f'Authorization: Bearer {self.api_key}',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(data)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"API 调用失败: {result.stderr}")
            raise Exception(f"API 调用失败: {result.stderr}")
        
        # 解析响应
        try:
            response_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"API 响应解析失败: {result.stdout[:200]}")
            raise Exception(f"API 响应解析失败: {result.stdout[:200]}")
        
        # 检查错误
        if 'error' in response_data:
            logger.error(f"API 返回错误: {response_data['error']}")
            raise Exception(f"API 返回错误: {response_data['error']}")
        
        if 'choices' not in response_data:
            logger.error(f"API 响应格式错误: {response_data}")
            raise Exception(f"API 响应格式错误: {response_data}")
        
        choice = response_data['choices'][0]
        message = choice['message']
        
        # 解析工具调用
        tool_calls = None
        if 'tool_calls' in message and message['tool_calls']:
            tool_calls = message['tool_calls']
        
        # 统计 token
        usage = response_data.get('usage', {})
        
        return LLMResponse(
            content=message.get('content', ''),
            tool_calls=tool_calls,
            finish_reason=choice.get('finish_reason'),
            input_tokens=usage.get('prompt_tokens', 0),
            output_tokens=usage.get('completion_tokens', 0),
            total_tokens=usage.get('total_tokens', 0)
        )
