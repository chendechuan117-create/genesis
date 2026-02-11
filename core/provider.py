"""
LLM 提供商实现
"""

from typing import List, Dict, Any, Optional
import json
import logging

from .base import LLMProvider as BaseLLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)

try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.debug("litellm 未安装，LLM 功能将不可用")


class NativeHTTPProvider(BaseLLMProvider):
    """基于原生 HTTP 的提供商 - 无需外部依赖"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://api.deepseek.com/v1",
        default_model: str = "deepseek-chat"
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/') if base_url else "https://api.deepseek.com/v1"
        self.default_model = default_model
    
    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求 (CURL Primary)"""
        import json
        
        model = model or self.default_model
        if model.startswith("deepseek/"):
            model = model.replace("deepseek/", "")
            
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "NanoGenesis/1.0"
        }
        
        # 直接使用 curl，绕过 Python 的代理兼容性问题
        data = json.dumps(payload).encode('utf-8')
        return self._chat_with_curl(url, headers, data)

    def _parse_response(self, resp_data: Dict) -> LLMResponse:
        """解析 API 响应"""
        choice = resp_data['choices'][0]
        message = choice['message']
        finish_reason = choice.get('finish_reason')
        
        # 提取工具调用
        tool_calls = []
        if 'tool_calls' in message and message['tool_calls']:
            for tc in message['tool_calls']:
                tool_calls.append(ToolCall(
                    id=tc['id'],
                    name=tc['function']['name'],
                    arguments=json.loads(tc['function']['arguments'])
                ))
        
        # 提取使用量
        usage = resp_data.get('usage', {})
        
        return LLMResponse(
            content=message.get('content') or "",
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=usage.get('prompt_tokens', 0),
            output_tokens=usage.get('completion_tokens', 0),
            total_tokens=usage.get('total_tokens', 0)
        )

    def _chat_with_curl(self, url: str, headers: Dict, data: bytes) -> LLMResponse:
        """使用 curl 命令发送请求（直连 DeepSeek 国内端点，绕过 SOCKS5 代理）"""
        import subprocess
        import shlex
        
        # 构建 curl 命令 — 使用 --noproxy 绕过 all_proxy 环境变量
        # DeepSeek 是国内服务（116.205.40.113），不需要走代理
        cmd = ['curl', '-k', '-s', '--noproxy', '*', '--connect-timeout', '15', '-X', 'POST', url]
        
        for k, v in headers.items():
            cmd.extend(['-H', f'{k}: {v}'])
            
        cmd.extend(['-d', data.decode('utf-8')])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                raise Exception(f"curl 失败: {result.stderr}")
                
            resp_data = json.loads(result.stdout)
            return self._parse_response(resp_data)
            
        except Exception as e:
            logger.error(f"curl 调用也失败了: {e}")
            raise

class LiteLLMProvider(BaseLLMProvider):
    """基于 LiteLLM 的提供商 - 支持多种 LLM"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "deepseek/deepseek-chat"
    ):
        if not LITELLM_AVAILABLE:
            raise ImportError("请安装 litellm: pip install litellm")
        
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        
        # 配置 LiteLLM
        if api_key:
            litellm.api_key = api_key
        if base_url:
            litellm.api_base = base_url
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求"""
        
        model = model or self.default_model
        
        # 构建请求参数
        request_params = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"
        
        try:
            # 调用 LiteLLM
            response = await litellm.acompletion(**request_params)
            
            # 解析响应
            message = response.choices[0].message
            finish_reason = getattr(response.choices[0], "finish_reason", None)
            
            # 提取工具调用
            tool_calls = []
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments)
                    ))
            
            # 提取使用量
            prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0
            total_tokens = getattr(response.usage, "total_tokens", 0) or 0

            return LLMResponse(
                content=message.content or "",
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                total_tokens=total_tokens
            )
        
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise
    
    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM 提供商 - 用于测试"""
    
    def __init__(self):
        self.call_count = 0
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """模拟 LLM 响应"""
        
        self.call_count += 1
        
        return LLMResponse(
            content=f"Mock response #{self.call_count}",
            tool_calls=[],
            finish_reason="stop",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150
        )
    
    def get_default_model(self) -> str:
        return "mock-model"
