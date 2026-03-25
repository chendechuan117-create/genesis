"""
AIXJ Responses API Provider 实现

AIXJ 的 Responses API 使用不同的请求格式：
- 标准 OpenAI Chat Completions API: 使用 messages 数组
- AIXJ Responses API: 使用 input 字符串

这个 Provider 将 messages 转换为 input 格式，适配 AIXJ Responses API。
"""

from typing import List, Dict, Any, Optional, Union
import json
import asyncio
import logging
from genesis.core.provider import NativeHTTPProvider, LLMResponse


class AIXJResponsesProvider(NativeHTTPProvider):
    """AIXJ Responses API Provider
    
    适配 AIXJ 的 Responses API 格式，将 messages 转换为 input 字符串。
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://api.aixj.cn/v1",
        default_model: str = "gpt-5.4",
        connect_timeout: int = 30,
        request_timeout: int = 180,
        wall_clock_timeout: int = 300,
        stop_sequences: Optional[List[str]] = None,
        provider_name: str = "aixj_responses",
        use_proxy: bool = False,
        skip_content_type: bool = True
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            connect_timeout=connect_timeout,
            request_timeout=request_timeout,
            wall_clock_timeout=wall_clock_timeout,
            stop_sequences=stop_sequences,
            provider_name=provider_name,
            use_proxy=use_proxy,
            skip_content_type=skip_content_type
        )
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        stream: bool = False,
        stream_callback: Any = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求，将 messages 转换为 input 格式
        
        Args:
            messages: Chat Completions 格式的消息数组
            tools: 工具定义（AIXJ Responses API 可能不支持）
            model: 模型名称
            stream: 是否使用流式响应
            stream_callback: 流式回调函数
            **kwargs: 其他参数
            
        Returns:
            LLMResponse: 响应对象
        """
        # aixj.vip = 标准 OpenAI chat completions，直接用父类（已验证能跑）
        if "aixj.vip" in self.base_url:
            return await super().chat(messages, tools, model, stream, stream_callback, **kwargs)
        
        # ── 以下仅用于 api.aixj.cn responses 端点 ──
        messages = self._sanitize_messages(messages)
        
        endpoint = "/responses"
        input_data = self._messages_to_input(messages, "responses")
        request_params = {
            "model": model or self.default_model,
            "input": input_data,
            **kwargs
        }
        
        logger = logging.getLogger(__name__)
        
        url = f"{self.base_url}{endpoint}"
        
        # 移除冲突的参数
        if "messages" in request_params and "input" in request_params:
            # 根据端点保留正确的参数
            if endpoint == "/chat/completions":
                del request_params["input"]
            else:
                del request_params["messages"]
        
        # 处理 stop sequences
        stop_seqs = self.stop_sequences if "stop" not in kwargs else kwargs["stop"]
        if "stop" not in request_params and stop_seqs:
            request_params["stop"] = stop_seqs
        
        # 添加调试日志
        logger.debug(f"Using endpoint: {endpoint}")
        logger.debug(f"Request params before sending: {request_params}")
        
        # AIXJ Responses API 可能不支持 tools，这里暂时忽略
        # if tools:
        #     logger.warning("AIXJ Responses API may not support tools parameter")
        
        # 设置 headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "NanoGenesis/1.0"
        }
        if not self.skip_content_type:
            headers["Content-Type"] = "application/json"
        
        # 发送请求
        try:
            result = await self._chat_responses(url, headers, request_params)
            NativeHTTPProvider._stats_successful_calls += 1
            NativeHTTPProvider._record_stat("success")
            return result
        except asyncio.TimeoutError:
            NativeHTTPProvider._stats_timeouts += 1
            NativeHTTPProvider._record_stat("timeout")
            raise Exception(f"Request timeout after {self.wall_clock_timeout} seconds")
        except Exception as e:
            NativeHTTPProvider._stats_errors += 1
            NativeHTTPProvider._record_stat("error")
            raise
    
    def _messages_to_input(self, messages: List[Dict[str, Any]], endpoint_type: str = "responses") -> Union[List[Dict[str, Any]], str]:
        """将消息数组转换为适合不同端点的格式
        
        Args:
            messages: Chat Completions 格式的消息数组
            endpoint_type: 端点类型，支持 "responses" 或 "chat_completions"
            
        Returns:
            对于 chat_completions 端点：返回消息数组
            对于 responses 端点：返回连接后的字符串
        """
        if endpoint_type == "chat_completions":
            # 对于 OpenAI 兼容端点，保持消息数组格式
            processed_messages = []
            for msg in messages:
                processed_msg = msg.copy()
                role = processed_msg.get("role", "")
                content = processed_msg.get("content")
                # 修复空 content（API 要求非空）
                if content is None or content == "":
                    if role == "assistant":
                        # assistant 允许 null（有 tool_calls 时）
                        if not processed_msg.get("tool_calls"):
                            processed_msg["content"] = " "
                    elif role == "tool":
                        processed_msg["content"] = "(empty)"
                    else:
                        processed_msg["content"] = " "
                processed_messages.append(processed_msg)
            return processed_messages
        elif endpoint_type == "responses":
            # 对于 AIXJ Responses API，将消息内容连接成字符串
            contents = []
            for msg in messages:
                content = msg.get("content", "")
                if content:
                    contents.append(content)
            # 用换行符连接所有内容
            return "\n".join(contents)
        else:
            # 默认按 responses 处理，保持向后兼容性
            contents = []
            for msg in messages:
                content = msg.get("content", "")
                if content:
                    contents.append(content)
            return "\n".join(contents)
    
    async def _chat_responses(self, url, headers, params):
        """重写 _chat_with_httpx 以适配 Responses API 响应格式"""
        import httpx
        
        _logger = logging.getLogger(__name__)
        retries = 3
        last_exception = None
        client = self._get_http_client()  # 复用父类连接池（含代理设置）
        
        for attempt in range(retries):
            try:
                _logger.debug(f"Sending request to {url}")
                
                response = await client.post(
                    url,
                    headers=headers,
                    json=params,
                    timeout=self.request_timeout
                )
                
                _logger.debug(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    resp_data = response.json()
                    return self._parse_responses_api_response(resp_data)
                elif response.status_code == 429:
                    # 限流，等待后重试
                    retry_after = response.headers.get('Retry-After', '1')
                    try:
                        wait_time = float(retry_after)
                    except ValueError:
                        wait_time = 1.0
                    
                    _logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # 其他错误
                    error_text = response.text
                    _logger.error(f"HTTP Error {response.status_code}: {error_text}")
                    
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', {}).get('message', str(error_data))
                    except json.JSONDecodeError:
                        error_msg = error_text
                    
                    raise Exception(f"HTTP {response.status_code}: {error_msg}")
                    
            except httpx.TimeoutException as e:
                last_exception = e
                _logger.warning(f"Timeout on attempt {attempt + 1}/{retries}: {e}")
                if attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    await asyncio.sleep(1)
                    continue
                NativeHTTPProvider._stats_timeouts += 1
                NativeHTTPProvider._record_stat("timeout")
                raise Exception(f"Network Error after {retries} retries: {e}")
            except Exception as e:
                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                _logger.error(f"httpx unexpected error: {e}")
                raise
        
        raise last_exception
    
    def _parse_responses_api_response(self, resp_data: Dict) -> LLMResponse:
        """解析 AIXJ Responses API 的响应格式
        
        AIXJ Responses API 返回格式示例:
        {
            "id": "chatcmpl-xxx",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-5.4",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I help you today?"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
        
        或者可能的简化格式:
        {
            "output": "Hello! How can I help you today?",
            "usage": {...}
        }
        """
        from genesis.core.provider import ToolCall
        
        if 'error' in resp_data:
            error_msg = resp_data['error'].get('message', str(resp_data['error']))
            raise Exception(f"API Error: {error_msg}")
        
        # 尝试解析标准 OpenAI 格式
        if 'choices' in resp_data and resp_data['choices']:
            choice = resp_data['choices'][0]
            message = choice.get('message', {})
            content = message.get('content', '')
            finish_reason = choice.get('finish_reason')
            
            # 提取工具调用
            tool_calls = []
            if 'tool_calls' in message and message['tool_calls']:
                for tc in message['tool_calls']:
                    raw_args = tc['function'].get('arguments', '{}')
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        repaired = raw_args.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                        try:
                            args = json.loads(repaired)
                        except json.JSONDecodeError:
                            args = {"__json_decode_error__": raw_args}
                    tool_calls.append(ToolCall(
                        id=tc.get('id', f"call_{len(tool_calls)}"),
                        name=tc['function']['name'],
                        arguments=args
                    ))
        
        # 尝试解析简化格式
        elif 'output' in resp_data:
            content = resp_data['output']
            finish_reason = 'stop'
            tool_calls = []
        
        else:
            raise Exception(f"Invalid AIXJ Responses API Response: {resp_data}")
        
        # 提取 token 使用情况
        usage = resp_data.get('usage', {})
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', input_tokens + output_tokens)
        prompt_cache_hit_tokens = usage.get('prompt_cache_hit_tokens', 0)
        
        return LLMResponse(
            content=content,
            reasoning_content="",  # AIXJ Responses API 可能不支持 reasoning
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            prompt_cache_hit_tokens=prompt_cache_hit_tokens
        )