"""
LLM 提供商实现
"""

from typing import List, Dict, Any, Optional
import ast
import asyncio
import json
import logging
import re
import subprocess
import warnings

from .base import LLMProvider as BaseLLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)



class NativeHTTPProvider(BaseLLMProvider):
    """基于原生 HTTP 的提供商 - 无需外部依赖"""
    
    DEFAULT_STOP_SEQUENCES = ["User:", "Observation:", "用户:", "Model:", "Assistant:"]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://api.deepseek.com/v1",
        default_model: str = "deepseek-chat",
        connect_timeout: int = 10,
        request_timeout: int = 120,
        stop_sequences: Optional[List[str]] = None
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/') if base_url else "https://api.deepseek.com/v1"
        self.default_model = default_model
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.stop_sequences = stop_sequences if stop_sequences is not None else self.DEFAULT_STOP_SEQUENCES
    
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
        model = model or self.default_model
        if model.startswith("deepseek/"):
            model = model.replace("deepseek/", "")
            
        url = f"{self.base_url}/chat/completions"
        
        request_params = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        if stream:
            request_params["stream"] = True
        
        # Enforce Default Stop Sequences (Anti-Hallucination)
        if "stop" not in request_params and self.stop_sequences:
             request_params["stop"] = self.stop_sequences
        
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "NanoGenesis/1.0"
        }
        
        data = json.dumps(request_params).encode('utf-8')
        
        if stream and stream_callback:
            return await self._stream_with_curl(url, headers, data, stream_callback)
            
        return self._chat_with_curl(url, headers, data)

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
        
        # --- Internal Reflection Stripping ---
        # The Stateless Executor might use <reflection> tags to think. We strip them here
        # so they don't pollute the context traces, the final packager response, or fallback parsers.
        if "<reflection>" in content:
            content = re.sub(r"<reflection>.*?</reflection>", "", content, flags=re.DOTALL)
            content = content.strip()

        # Heuristic Fallback: Check for code-block tool calls
        if not tool_calls and content:
            tool_calls = self._try_parse_tools_from_content(content)

        # 提取使用量
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

    def _try_parse_tools_from_content(self, content: str) -> List[ToolCall]:
        """Attempt to parse function calls from Python code blocks"""
        tool_calls = []
        # Find all code blocks (python, json, or generic)
        # Capture the content inside ```...```
        code_blocks = re.findall(r"```(?:\w*)\s*(.*?)```", content, re.DOTALL | re.IGNORECASE)
        
        for block in code_blocks:
            # Strategy 1: Try parsing as JSON Action (DeepSeek Native)
            try:
                data = json.loads(block)
                if isinstance(data, dict):
                     name = data.get("action") or data.get("tool") or data.get("name") or data.get("tool_name")
                     if name:
                         # Heuristic mapping for arguments
                         if "args" in data:
                             args = data["args"]
                         elif "arguments" in data:
                             args = data["arguments"]
                         elif "command" in data:
                             # Flatten command into args if it's a single command string
                             args = {"command": data["command"]}
                         else:
                             # Assume remaining keys are arguments
                             args = {k: v for k, v in data.items() if k not in ("action", "tool", "name", "tool_name")}
                             
                         tool_calls.append(ToolCall(
                             id=f"call_json_{len(tool_calls)}",
                             name=name,
                             arguments=args
                         ))
                         continue # Succesfully parsed as JSON, skip AST
            except:
                pass

            # Strategy 2: Try parsing as Python Code (Original Logic)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    # Parse the code block into an AST
                    tree = ast.parse(block)
                for node in ast.walk(tree):
                    # Pattern 1: Function Call -> tool_name(arg=val)
                    if isinstance(node, ast.Call):
                        # Extract function name
                        func_name = ""
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            func_name = node.func.attr
                        
                        if func_name and func_name.isidentifier():
                            args = {}
                            for keyword in node.keywords:
                                if keyword.arg:
                                    try:
                                        value = ast.literal_eval(keyword.value)
                                        args[keyword.arg] = value
                                    except:
                                        if isinstance(keyword.value, ast.Constant):
                                            args[keyword.arg] = keyword.value.value
                            if args:
                                tool_calls.append(ToolCall(
                                    id=f"call_heuristic_{len(tool_calls)}",
                                    name=func_name,
                                    arguments=args
                                ))

                    # Pattern 2: Dictionary Assignment -> tool = {"name": "...", "arguments": ...}
                    elif isinstance(node, ast.Assign):
                        # Check if it's a dict assignment
                        if isinstance(node.value, ast.Dict):
                            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
                            values = node.value.values
                            
                            # Normalize dict
                            data = {}
                            for k, v in zip(keys, values):
                                try:
                                    data[k] = ast.literal_eval(v)
                                except:
                                    if isinstance(v, ast.Constant):
                                         data[k] = v.value
                            
                            # Check schema match
                            if "name" in data and ("arguments" in data or "args" in data):
                                name = data["name"]
                                args_raw = data.get("arguments") or data.get("args")
                                
                                # Handle stringified JSON args
                                args = {}
                                if isinstance(args_raw, str):
                                    try:
                                        args = json.loads(args_raw)
                                    except:
                                        pass
                                elif isinstance(args_raw, dict):
                                    args = args_raw
                                    
                                tool_calls.append(ToolCall(
                                    id=f"call_heuristic_{len(tool_calls)}",
                                    name=name,
                                    arguments=args
                                ))
            except Exception:
                continue

        # Regex Fallback for "functions = {...}" or "tool = {...}" when AST fails
        # (Common with models that output invalid Python syntax like unescaped newlines in strings)
        if not tool_calls:
             # Regex for: "name": "foo", "arguments": "..."
             # Robust pattern relying on the fact that arguments is usually the last item
             # Captures everything between 'arguments": "' and '"\s*}' (end of dict)
             pattern = r'"name":\s*"([^"]+)"[\s\S]*?"arguments":\s*"?([\s\S]*?)"?\s*\}\s*$'
             matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
             
             for match in matches:
                 name = match.group(1)
                 args_raw = match.group(2)
                 
                 args = {}
                 try:
                     # If it's a string, unquote it then parse JSON
                     if args_raw.startswith('"'):
                         # primitive unquote
                         json_str = args_raw.strip('"').replace(r'\"', '"').replace(r'\n', '\n')
                         args = json.loads(json_str)
                     else:
                         # It's a dict-like string, try to parse as JSON directly
                         args = json.loads(args_raw)
                         
                     tool_calls.append(ToolCall(
                        id=f"call_regex_{len(tool_calls)}",
                        name=name,
                        arguments=args
                     ))
                 except:
                     pass

        # Fallback 2: Check for direct JSON action blocks (Common in DeepSeek/Flash)
        # Pattern: {"action": "tool_name", "command": "arg"} or {"action": "tool_name", "args": {...}}
        if not tool_calls:
            try:
                 # Find valid JSON blocks that contain "action"
                 # We use a regex to find potental JSONs then search inside
                 json_blocks = re.findall(r'\{[\s\S]*?\}', content)
                 for block in json_blocks:
                     try:
                         data = json.loads(block)
                         if isinstance(data, dict):
                             name = data.pop("action", None) or data.pop("tool", None) or data.pop("name", None) or data.pop("tool_name", None)
                             if name:
                                 # Heuristic mapping for arguments
                                 if "args" in data:
                                     args = data["args"]
                                 elif "arguments" in data:
                                     args = data["arguments"]
                                 else:
                                     # Assume remaining keys are arguments
                                     args = data
                                     
                                 tool_calls.append(ToolCall(
                                     id=f"call_json_action_{len(tool_calls)}",
                                     name=name,
                                     arguments=args
                                 ))
                     except:
                         continue
            except Exception:
                 pass

        if tool_calls:
            logger.info(f"🔍 Heuristically detected {len(tool_calls)} tool calls in content")
            
        return tool_calls

    def _chat_with_curl(self, url: str, headers: Dict, data: bytes) -> LLMResponse:
        """使用 curl 命令发送请求（尊重系统代理配置）"""
        
        # 构建 curl 命令 — 移除 --noproxy '*' 以支持系统代理
        # 使用 --data-binary @- 从 stdin 读取数据，避免参数过长问题
        # Add --max-time to prevent indefinite hanging
        # Add -4 to force IPv4 and avoid IPv6 timeout delays
        cmd = [
            'curl', '-k', '-s', '-4',
            '--connect-timeout', str(self.connect_timeout), 
            '--max-time', str(self.request_timeout),
            '-w', '\n%{time_namelookup},%{time_connect},%{time_starttransfer},%{time_total}',
            '-X', 'POST', url
        ]
        
        for k, v in headers.items():
            cmd.extend(['-H', f'{k}: {v}'])
            
        cmd.extend(['--data-binary', '@-'])
        
        try:
            result = subprocess.run(
                cmd,
                input=data.decode('utf-8'), # Pass data via stdin
                capture_output=True,
                text=True,
                timeout=self.request_timeout
            )
            
            # Extract timing metrics from the end of stdout
            stdout_raw = result.stdout
            timing_info = "0,0,0,0"
            if stdout_raw:
                parts = stdout_raw.rsplit('\n', 1)
                if len(parts) == 2:
                    stdout_clean = parts[0]
                    timing_info = parts[1]
                else:
                    stdout_clean = stdout_raw
            else:
                stdout_clean = ""

            # Log metrics if slow
            try:
                t_dns, t_conn, t_ttfb, t_total = timing_info.split(',')
                if float(t_total) > 5.0:
                    logger.warning(f"🐢 Slow Request: DNS={t_dns}s, Conn={t_conn}s, TTFB={t_ttfb}s, Total={t_total}s")
            except:
                pass

            if result.returncode != 0:
                raise Exception(f"curl 失败: {result.stderr}")
                
            try:
                resp_data = json.loads(stdout_clean)
                return self._parse_response(resp_data)
            except json.JSONDecodeError as e:
                # 记录详细的响应内容以便调试
                preview = result.stdout[:500] if result.stdout else "Empty Response"
                raise Exception(f"API 响应解析失败: {e}. Content: {preview}")
            
        except Exception as e:
            if 'result' in locals() and result.stdout:
                 logger.error(f"Failed Response Body: {result.stdout[:1000]}")
            logger.error(f"curl 调用也失败了: {e}")
            raise

    async def _stream_with_curl(self, url: str, headers: Dict, data: bytes, callback) -> LLMResponse:
        """流式 Curl 请求 (Robust Version)"""
        
        # Add -N for no buffer, use --data-binary @- for stdin
        # Add --max-time (self.request_timeout) to prevent infinite hanging on zombie connections
        # Add -4 to force IPv4
        cmd = [
            'curl', '-k', '-s', '-N', '-4',
            '--connect-timeout', str(self.connect_timeout),
            '--max-time', str(self.request_timeout),
            '-X', 'POST', url
        ]
        for k, v in headers.items():
            cmd.extend(['-H', f'{k}: {v}'])
            
        cmd.extend(['--data-binary', '@-'])
        
        full_content = []
        reasoning_content = []
        tool_call_chunks = {}
        final_tool_calls = []
        finish_reason = None
        input_tokens = 0
        output_tokens = 0
        prompt_cache_hit_tokens = 0
        
        logger.debug(f"Starting curl command (stdin mode): {' '.join(cmd)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            if process.stdin:
                process.stdin.write(data)
                await process.stdin.drain()
                process.stdin.close()
            
            # Read line by line, but accumulating if needed
            buffer = ""
            is_sse = False
            
            async for line_bytes in process.stdout:
                line = line_bytes.decode('utf-8', errors='replace').strip()
                logger.debug(f"Stream line: {line}") 
                if not line:
                    continue
                
                # Check for SSE signature
                if line.startswith('data: '):
                    is_sse = True
                    
                if is_sse:
                    if line == 'data: [DONE]':
                        break
                    if line.startswith('data: '):
                        chunk_str = line[6:]
                        try:
                            chunk = json.loads(chunk_str)
                            if not chunk['choices']: continue
                            
                            delta = chunk['choices'][0].get('delta', {})
                            
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
                else:
                    # Not SSE yet, accumulate lines for potentially big JSON
                    buffer += line
            
            # Post-loop: Check if we have a buffered JSON (Fallback for non-streaming)
            if not is_sse and buffer:
                try:
                    resp_obj = json.loads(buffer)
                    if "choices" in resp_obj:
                        choice = resp_obj["choices"][0]
                        message = choice.get("message", {})
                        
                        # Content
                        if message.get("content"):
                            full_content.append(message["content"])
                        
                        # Tool Calls
                        if message.get("tool_calls"):
                            for tc in message["tool_calls"]:
                                final_tool_calls.append(ToolCall(
                                    id=tc["id"],
                                    name=tc["function"]["name"],
                                    arguments=json.loads(tc["function"]["arguments"])
                                ))
                        
                        # Usage
                        if "usage" in resp_obj:
                            input_tokens = resp_obj["usage"].get("prompt_tokens", 0)
                            output_tokens = resp_obj["usage"].get("completion_tokens", 0)
                            prompt_cache_hit_tokens = resp_obj["usage"].get("prompt_cache_hit_tokens", 0)
                            
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse non-SSE buffer: {buffer[:100]}...")

            await process.wait()
            
            # Check for API Error in buffer
            if not is_sse and buffer:
                try:
                    err_obj = json.loads(buffer)
                    if "error" in err_obj:
                        raise Exception(f"API Error detected: {err_obj['error']}")
                except:
                    pass
            
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
                    # Fallback: Instead of dropping or throwing confusing kwargs error, 
                    # we pass an explicit error flag to the registry.
                    final_tool_calls.append(ToolCall(
                        id=tc_data["id"] or f"call_{idx}",
                        name=tc_data["name"],
                        arguments={"__json_decode_error__": tc_data["args"]}
                    ))
            
            # Heuristic Fallback for Streaming: Check full content for code blocks
            final_content = "".join(full_content)
            if not final_tool_calls and final_content:
                heuristic_calls = self._try_parse_tools_from_content(final_content)
                if heuristic_calls:
                     final_tool_calls.extend(heuristic_calls)

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
            
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            raise

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

