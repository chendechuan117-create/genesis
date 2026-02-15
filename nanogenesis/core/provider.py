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
        stream: bool = False,
        stream_callback: Any = None,
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
        
        if stream and stream_callback:
            return await self._stream_with_curl(url, headers, data, stream_callback)
            
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
        
        # 构建 curl 命令 — 使用 --noproxy 绕过 all_proxy 环境变量
        # 使用 --data-binary @- 从 stdin 读取数据，避免参数过长问题
        cmd = ['curl', '-k', '-s', '--noproxy', '*', '--connect-timeout', '15', '-X', 'POST', url]
        
        for k, v in headers.items():
            cmd.extend(['-H', f'{k}: {v}'])
            
        cmd.extend(['--data-binary', '@-'])
        
        try:
            result = subprocess.run(
                cmd,
                input=data.decode('utf-8'), # Pass data via stdin
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                raise Exception(f"curl 失败: {result.stderr}")
                
            resp_data = json.loads(result.stdout)
            return self._parse_response(resp_data)
            
        except Exception as e:
            if 'result' in locals() and result.stdout:
                 logger.error(f"Failed Response Body: {result.stdout[:1000]}")
            logger.error(f"curl 调用也失败了: {e}")
            raise

    async def _stream_with_curl(self, url: str, headers: Dict, data: bytes, callback) -> LLMResponse:
        """流式 Curl 请求 (Async) - Unified Version"""
        import asyncio
        
        # Add -N for no buffer, use --data-binary @- for stdin
        cmd = ['curl', '-k', '-s', '-N', '--noproxy', '*', '--connect-timeout', '15', '-X', 'POST', url]
        for k, v in headers.items():
            cmd.extend(['-H', f'{k}: {v}'])
            
        cmd.extend(['--data-binary', '@-'])
        
        full_content = []
        reasoning_content = []
        tool_call_chunks = {}
        final_tool_calls = [] # Initialized early
        finish_reason = None
        
        input_tokens = 0
        output_tokens = 0
        
        logger.debug(f"Starting curl command (stdin mode): {' '.join(cmd)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE, # Enable stdin
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Write data to stdin
            if process.stdin:
                process.stdin.write(data)
                await process.stdin.drain()
                process.stdin.close()
            
            logger.debug(f"Curl process started, PID: {process.pid}")
            
            line_count = 0
            async for line_bytes in process.stdout:
                line_count += 1
                line = line_bytes.decode('utf-8').strip()
                logger.debug(f"DEBUG_RAW: {line}")
                if not line:
                    continue
                if line == 'data: [DONE]':
                    break
                
                # Error Handling for JSON responses (non-SSE)
                if not line.startswith('data: '):
                    try:
                        resp_obj = json.loads(line)
                        
                        # Case 1: API Error
                        if "error" in resp_obj:
                             logger.error(f"API Error Response: {line}")
                             full_content.append(f"[API Error: {resp_obj['error'].get('message', line)}]")
                             break
                             
                        # Case 2: Non-streaming Response (Fallback)
                        if "choices" in resp_obj and isinstance(resp_obj["choices"], list):
                            choice = resp_obj["choices"][0]
                            message = choice.get("message", {})
                            
                            # Content
                            if "content" in message and message["content"]:
                                full_content.append(message["content"])
                                if callback:
                                    if asyncio.iscoroutinefunction(callback):
                                        await callback("content", message["content"])
                                    else:
                                        callback("content", message["content"])
                            
                            # Reasoning (if present in non-stream)
                            if "reasoning_content" in message and message["reasoning_content"]:
                                reasoning_content.append(message["reasoning_content"])
                                if callback:
                                    if asyncio.iscoroutinefunction(callback):
                                        await callback("reasoning", message["reasoning_content"])
                                    else:
                                        callback("reasoning", message["reasoning_content"])
                            
                            # Tool Calls (Non-stream format)
                            if "tool_calls" in message and message["tool_calls"]:
                                for tc in message["tool_calls"]:
                                    final_tool_calls.append(ToolCall(
                                        id=tc["id"],
                                        name=tc["function"]["name"],
                                        arguments=json.loads(tc["function"]["arguments"])
                                    ))
                                # Prevent tool_call_chunks logic from overriding
                                tool_call_chunks = {} 
                                
                            # Finish Reason
                            finish_reason = choice.get("finish_reason")
                            
                            # Usage
                            if "usage" in resp_obj:
                                input_tokens = resp_obj["usage"].get("prompt_tokens", 0)
                                output_tokens = resp_obj["usage"].get("completion_tokens", 0)
                                
                            break # Response is complete
                             
                    except json.JSONDecodeError:
                        logger.warning(f"Unexpected curl output: {line[:200]}")
                    continue

                if line.startswith('data: '):
                    try:
                        chunk_str = line[6:]
                        if chunk_str.strip() == '[DONE]': break
                        
                        chunk = json.loads(chunk_str)
                        if not chunk['choices']: continue
                        
                        delta = chunk['choices'][0]['delta']
                        
                        # Handle Reasoning (DeepSeek)
                        if 'reasoning_content' in delta and delta['reasoning_content']:
                            rc = delta['reasoning_content']
                            reasoning_content.append(rc)
                            if callback:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback("reasoning", rc)
                                else:
                                    callback("reasoning", rc)
                            
                        # Handle Content
                        if 'content' in delta and delta['content']:
                            c = delta['content']
                            full_content.append(c)
                            if callback:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback("content", c)
                                else:
                                    callback("content", c)
                            
                        # Handle Tool Calls
                        if 'tool_calls' in delta and delta['tool_calls']:
                            for tc in delta['tool_calls']:
                                idx = tc['index']
                                if idx not in tool_call_chunks:
                                    tool_call_chunks[idx] = {"id": "", "name": "", "args": ""}
                                
                                if 'id' in tc and tc['id']:
                                    tool_call_chunks[idx]["id"] = tc['id']
                                if 'function' in tc:
                                    if 'name' in tc['function'] and tc['function']['name']:
                                        tool_call_chunks[idx]["name"] += tc['function']['name']
                                    if 'arguments' in tc['function'] and tc['function']['arguments']:
                                        tool_call_chunks[idx]["args"] += tc['function']['arguments']

                        if 'finish_reason' in chunk['choices'][0]:
                            finish_reason = chunk['choices'][0]['finish_reason']
                            
                        if 'usage' in chunk:
                             output_tokens = chunk['usage'].get('completion_tokens', 0)
                             
                    except json.JSONDecodeError:
                        continue
            
            # Wait for completion
            await process.wait()
            stderr = await process.stderr.read()
            
            logger.debug(f"Curl finished. Return code: {process.returncode}, Lines read: {line_count}")
            if stderr:
                logger.debug(f"Curl stderr: {stderr.decode('utf-8')}")

            if process.returncode != 0:
                 logger.error(f"Curl stream error: {stderr.decode('utf-8')}")
            
            # Reconstruct ToolCalls (from stream chunks)
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
                    logger.warning(f"Failed to parse tool args: {tc_data['args']}")

            return LLMResponse(
                content="".join(full_content),
                reasoning_content="".join(reasoning_content),
                tool_calls=final_tool_calls,
                finish_reason=finish_reason,
                input_tokens=input_tokens,
                output_tokens=len(full_content) + len(reasoning_content),
                total_tokens=0
            )
            
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
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
