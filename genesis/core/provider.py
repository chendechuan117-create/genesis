"""
LLM 提供商实现
"""

from typing import List, Dict, Any, Optional
import logging
import json
import re
import asyncio
import httpx

from .base import LLMProvider as BaseLLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class NativeHTTPProvider(BaseLLMProvider):
    """基于原生 HTTP (httpx) 的提供商 - 高性能异步实现"""
    
    DEFAULT_STOP_SEQUENCES = ["User:", "Observation:", "用户:", "Model:", "Assistant:"]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://api.deepseek.com/v1",
        default_model: str = "deepseek-chat",
        connect_timeout: int = 30,
        request_timeout: int = 180,
        stop_sequences: Optional[List[str]] = None,
        provider_name: str = "default"
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/') if base_url else "https://api.deepseek.com/v1"
        self.default_model = default_model
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.stop_sequences = stop_sequences if stop_sequences is not None else self.DEFAULT_STOP_SEQUENCES
        self.provider_name = provider_name
    
    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        stream: bool = False,
        stream_callback: Any = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求 (httpx)"""
        model = model or self.default_model
        if model.startswith("deepseek/"):
            model = model.replace("deepseek/", "")
            
        url = f"{self.base_url}/chat/completions"
        
        # Optional stop sequences and truncation limit
        stop_seqs = self.stop_sequences if "stop" not in kwargs else kwargs["stop"]
        if self.provider_name == 'groq' and len(stop_seqs) > 4:
            stop_seqs = stop_seqs[:4]
            
        request_params = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        if stream:
            request_params["stream"] = True
        
        if "stop" not in request_params and stop_seqs:
             request_params["stop"] = stop_seqs
        
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "NanoGenesis/1.0"
        }
        
        timeout = httpx.Timeout(self.request_timeout, connect=self.connect_timeout)
        
        # httpx handles proxies automatically via env vars (HTTP_PROXY, HTTPS_PROXY)
        # 强制 trust_env=False，不使用代理（DeepSeek等国内API直连更快，避免绕代理导致单次请求多花11秒）
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            if stream:
                return await self._stream_with_httpx(client, url, headers, request_params, stream_callback)
            else:
                return await self._chat_with_httpx(client, url, headers, request_params)

    async def _chat_with_httpx(self, client: httpx.AsyncClient, url: str, headers: Dict, params: Dict) -> LLMResponse:
        """非流式请求"""
        retries = 3
        last_exception = None
        
        for attempt in range(retries):
            try:
                response = await client.post(url, headers=headers, json=params)
                response.raise_for_status()
                return self._parse_response(response.json())
            except httpx.HTTPStatusError as e:
                # API returned error (4xx/5xx)
                error_body = e.response.text
                try:
                    err_json = e.response.json()
                    error_msg = err_json.get('error', {}).get('message', error_body)
                except:
                    error_msg = error_body
                raise Exception(f"API Error ({e.response.status_code}): {error_msg}")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(f"httpx connection error (attempt {attempt+1}/{retries}): {e}")
                last_exception = e
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise Exception(f"Network Error after {retries} retries: {e}")
            except Exception as e:
                 logger.error(f"httpx unexpected error: {e}")
                 raise

        raise last_exception

    def _parse_response(self, resp_data: Dict) -> LLMResponse:
        """解析 API 响应"""
        if 'error' in resp_data:
             error_msg = resp_data['error'].get('message', str(resp_data['error']))
             raise Exception(f"API Error: {error_msg}")
             
        if 'choices' not in resp_data or not resp_data['choices']:
             raise Exception(f"Invalid API Response: Missing 'choices'. Data: {resp_data}")

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
        
        content = message.get('content') or ""
        
        if "<reflection>" in content:
            content = re.sub(r"<reflection>.*?</reflection>", "", content, flags=re.DOTALL)
            content = content.strip()

        usage = resp_data.get('usage', {})
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=usage.get('prompt_tokens', 0),
            output_tokens=usage.get('completion_tokens', 0),
            total_tokens=usage.get('total_tokens', 0),
            prompt_cache_hit_tokens=usage.get('prompt_cache_hit_tokens', 0)
        )

    async def _stream_with_httpx(self, client: httpx.AsyncClient, url: str, headers: Dict, params: Dict, callback) -> LLMResponse:
        """流式请求"""
        full_content = []
        reasoning_content = []
        tool_call_chunks = {}
        final_tool_calls = []
        finish_reason = None
        input_tokens = 0
        output_tokens = 0
        prompt_cache_hit_tokens = 0
        
        retries = 3
        
        for attempt in range(retries):
            try:
                async with client.stream("POST", url, headers=headers, json=params) as response:
                    if response.status_code != 200:
                        await response.aread()
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if not line.startswith('data: '):
                            continue
                            
                        chunk_str = line[6:]
                        if chunk_str == '[DONE]':
                            break
                            
                        try:
                            chunk = json.loads(chunk_str)
                            choices = chunk.get('choices')
                            if not choices: continue
                            
                            delta = choices[0].get('delta', {})
                            
                            # Reasoning
                            if 'reasoning_content' in delta:
                                rc = delta['reasoning_content']
                                if rc:
                                    reasoning_content.append(rc)
                                    if callback:
                                        res = callback("reasoning", rc)
                                        if asyncio.iscoroutine(res): await res
                                        
                            # Content
                            if 'content' in delta:
                                c = delta['content']
                                if c:
                                    full_content.append(c)
                                    if callback:
                                        res = callback("content", c)
                                        if asyncio.iscoroutine(res): await res
                            
                            # Tool Calls
                            if 'tool_calls' in delta:
                                for tc in delta['tool_calls']:
                                    idx = tc['index']
                                    if idx not in tool_call_chunks:
                                        tool_call_chunks[idx] = {"id": "", "name": "", "args": ""}
                                    if 'id' in tc and tc['id']: tool_call_chunks[idx]["id"] = tc['id']
                                    if 'function' in tc:
                                        if 'name' in tc['function']: tool_call_chunks[idx]["name"] += tc['function']['name']
                                        if 'arguments' in tc['function']: tool_call_chunks[idx]["args"] += tc['function']['arguments']
                            
                            if 'usage' in chunk:
                                output_tokens = chunk['usage'].get('completion_tokens', 0)
                                input_tokens = chunk['usage'].get('prompt_tokens', 0)
                                prompt_cache_hit_tokens = chunk['usage'].get('prompt_cache_hit_tokens', 0)

                        except json.JSONDecodeError:
                            continue
                            
                # If we get here, stream completed successfully
                break
                
            except httpx.HTTPStatusError as e:
                raise Exception(f"API Error ({e.response.status_code}): {e.response.text}")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(f"httpx stream error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise Exception(f"Stream Network Error after {retries} retries: {e}")
            except Exception as e:
                raise
                
        # Post-processing
        for idx in sorted(tool_call_chunks.keys()):
            tc_data = tool_call_chunks[idx]
            try:
                args = json.loads(tc_data["args"]) if tc_data["args"] else {}
                final_tool_calls.append(ToolCall(
                    id=tc_data["id"] or f"call_{idx}",
                    name=tc_data["name"],
                    arguments=args
                ))
            except json.JSONDecodeError:
                # Try simple repair for newlines
                repaired = tc_data["args"].replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                try:
                    args = json.loads(repaired)
                    final_tool_calls.append(ToolCall(
                        id=tc_data["id"] or f"call_{idx}",
                        name=tc_data["name"],
                        arguments=args
                    ))
                except:
                     final_tool_calls.append(ToolCall(
                        id=tc_data["id"] or f"call_{idx}",
                        name=tc_data["name"],
                        arguments={"__json_decode_error__": tc_data["args"]}
                    ))

        final_content = "".join(full_content)
        
        if not final_content and not final_tool_calls:
            rc_text = "".join(reasoning_content)
            if rc_text.strip():
                final_content = rc_text
            else:
                raise Exception("Empty LLM response from stream")

        return LLMResponse(
            content=final_content,
            reasoning_content="".join(reasoning_content),
            tool_calls=final_tool_calls,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            prompt_cache_hit_tokens=prompt_cache_hit_tokens
        )

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

