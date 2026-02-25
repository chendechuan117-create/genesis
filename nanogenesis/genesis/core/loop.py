"""
Agent 主循环 - ReAct 模式
推理 (Reasoning) → 行动 (Acting) → 观察 (Observing)
"""

from typing import List, Dict, Any, Optional
import logging
import time
import json

from .base import Message, MessageRole, LLMResponse, PerformanceMetrics, LLMProvider
from .registry import ToolRegistry
from .registry import ToolRegistry
from .context import SimpleContextBuilder
import asyncio

logger = logging.getLogger(__name__)


class AgentLoop:
    """Agent 主循环 - 核心执行引擎"""
    
    def __init__(
        self,
        tools: ToolRegistry,
        context: SimpleContextBuilder,
        provider: LLMProvider,
        # Dynamic configuration via Agent's global config
        max_iterations: Optional[int] = None
    ):
        self.tools = tools
        self.context = context
        self.provider = provider
        self.max_iterations = max_iterations if max_iterations is not None else getattr(self.agent.config, 'max_iterations', 10)
        
        # Ouroboros Loop State
        self.iteration_history = []
    
    async def run(
        self,
        user_input: str,
        step_callback: Optional[Any] = None, # (step_type, data) -> None
        **context_kwargs
    ) -> tuple[str, PerformanceMetrics]:
        """
        运行 Agent 循环
        
        Returns:
            (响应内容, 性能指标)
        """
        start_time = time.time()
        tools_used = []
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        prompt_cache_hit_tokens = 0
        tool_calls_recorded = []
        
        # 1. 构建初始上下文 (Stateless Protocol)
        # We pass ONLY the tactical instruction, ignoring user context/history
        instruction = context_kwargs.get("user_context", user_input)
        if "[战略蓝图]" in instruction:
             # Extract just the blueprint if possible
             try:
                 instruction = instruction.split("[战略蓝图]")[1].split("[记录决策ID:")[0].strip()
             except:
                 pass
                 
        built_messages = await self.context.build_stateless_messages(instruction)
        messages = [msg.to_dict() for msg in built_messages]
        
        # 2. ReAct 循环 (Elastic Endurance)
        iteration = 0
        final_response = ""
        soft_limit = self.max_iterations
        hard_limit = min(25, self.max_iterations * 2.5) # 弹性上限
        
        # 错误跟踪器 (Failure Attribution)
        tool_errors = {} # {tool_name: [compressed_error_reports]}
        last_tool_call_hash = None
        loop_counter = 0
        
        # 错误压缩器（降低 LLM 认知负荷）
        from genesis.core.error_compressor import ErrorCompressor
        _error_compressor = ErrorCompressor()


        while iteration < hard_limit:
            iteration += 1
            
            # Callback: Loop Start
            # Callback: Loop Start
            if step_callback:
                if asyncio.iscoroutinefunction(step_callback):
                    await step_callback("loop_start", iteration)
                else:
                    step_callback("loop_start", iteration)
            
            # 软上限检查 (Failure Attribution)
            if iteration > soft_limit:
                 logger.debug(f"⚠️ 超过软上限 {soft_limit}，进入弹性耐力模式 (第 {iteration} 次)")
                 # 注入诊断线索
                 built_messages.append(Message(
                     role=MessageRole.SYSTEM,
                     content=f"Diagnostic Hint: You have exceeded {soft_limit} iterations. Suspected issue: logic_loop or capability_gap. Please check if you are repeating the same failing steps."
                 ))
            else:
                 logger.debug(f"迭代 {iteration}/{soft_limit}")
            
            # 2.1 调用 LLM (Reasoning)
            try:
                # 重新构建 messages 并进行 Strict Schema 净化 (Sanitization)
                messages = []
                for i, msg in enumerate(built_messages):
                    msg_dict = msg.to_dict()
                    
                    if msg_dict["role"] == "tool":
                        # Check previous message
                        prev_msg = messages[-1] if messages else None
                        is_orphan = True
                        if prev_msg and prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                            # Further check if this specific tool_call_id exists in the previous assistant's tool_calls
                            target_id = msg_dict.get("tool_call_id")
                            if target_id and any(tc.get("id") == target_id for tc in prev_msg.get("tool_calls", [])):
                                is_orphan = False
                                
                        if is_orphan:
                            # Convert orphaned tool response to a user observation to satisfy OpenAI schema
                            logger.debug(f"Sanitizing orphaned tool payload {msg_dict.get('tool_call_id', 'unknown')} -> user")
                            msg_dict["role"] = "user"
                            msg_dict["content"] = f"[System Observation (Tool Result)]:\n{msg_dict.get('content', '')}"
                            if "tool_call_id" in msg_dict: del msg_dict["tool_call_id"]
                            if "name" in msg_dict: del msg_dict["name"]
                            
                    messages.append(msg_dict)
                # 定义流式回调
                async def stream_handler(chunk_type, chunk_data):
                    if step_callback:
                        if chunk_type == "reasoning":
                             if asyncio.iscoroutinefunction(step_callback):
                                 await step_callback("reasoning", chunk_data)
                             else:
                                 step_callback("reasoning", chunk_data)
                
                # --- DEBUG DUMP ---
                import json
                import os
                dump_file = "agent_loop_payload_dump.json"
                dump_data = {
                    "messages": messages,
                    "tools": [t for t in self.tools.get_definitions()] if iteration < hard_limit else None
                }
                with open(dump_file, "a", encoding="utf-8") as _df:
                    _df.write(json.dumps(dump_data, ensure_ascii=False) + "\n---\n")
                # ------------------
                
                response = await self.provider.chat(
                    messages=messages,
                    tools=[t for t in self.tools.get_definitions()] if iteration < hard_limit else None,
                    stream=True,
                    stream_callback=stream_handler
                )
                input_tokens += getattr(response, "input_tokens", 0) or 0
                output_tokens += getattr(response, "output_tokens", 0) or 0
                total_tokens += getattr(response, "total_tokens", 0) or 0
                prompt_cache_hit_tokens += getattr(response, "prompt_cache_hit_tokens", 0) or 0
                
                # Fallback: If content is empty but reasoning exists (DeepSeek R1 quirk), use reasoning
                if not response.content and getattr(response, "reasoning_content", None):
                    response.content = response.reasoning_content
                
            except Exception as e:
                error_msg = str(e)
                # Sanitize: Remove raw curl commands or massive dumps
                if "curl" in error_msg and "messages" in error_msg:
                    error_msg = "Connection failed to LLM provider (curl error). Check network or API key."
                elif len(error_msg) > 500:
                    error_msg = error_msg[:200] + "..." + error_msg[-100:]
                    
                logger.error(f"LLM 调用失败: {e}", exc_info=True)
                final_response = f"Error: LLM 调用失败 - {error_msg}"
                break
            
            # 2.2 检查是否有工具调用 (Acting)
            
            # Critical Fix: Detect Empty Response (The Silent Failure)
            if not response.content and not response.tool_calls and not response.reasoning_content:
                 logger.warning(f"⚠️ 收到空响应 (Iteration {iteration}). 触发重试机制...")
                 
                 # --- FIX: Multimodal Fallback ---
                 # If the last tool message had multimodal (image) content and the LLM returned empty,
                 # the model likely doesn't support vision. Fall back to text-only description.
                 last_tool_multimodal = next(
                     (m for m in reversed(built_messages)
                      if m.role == MessageRole.TOOL and isinstance(m.content, list)),
                     None
                 )
                 if last_tool_multimodal:
                     logger.warning("👁️→📝 视觉降级: 模型返回空响应，将图像消息 fallback 为纯文本描述")
                     # Extract text part only
                     text_only = " ".join(
                         part.get("text", "") for part in last_tool_multimodal.content
                         if isinstance(part, dict) and part.get("type") == "text"
                     )
                     last_tool_multimodal.content = (
                         text_only + "\n[注意：截图已保存，但当前模型不支持图像输入。请根据截图路径信息，用文字判断任务状态。]"
                     ) if text_only else "[工具执行完毕，模型不支持图像输入，无法直接分析截图内容。]"
                 
                 # Context Detox Strategy (Revised)
                 # If we are stuck in a retry loop (detected by 'System Error' in history), 
                 # it means the context is fatally poisoned for this step.
                 # User Feedback: DO NOT amputate history, as it causes jumps to older tasks.
                 # Correct behavior: Trigger a STRATEGIC_INTERRUPT to fail this mission node and backtrack naturally.
                 last_msg = built_messages[-1]
                 if last_msg.role == MessageRole.SYSTEM and "System Error: You returned an empty response" in last_msg.content:
                      logger.error(f"☠️ Context Poisoning Detected! (Recursive Empty Response). Triggering Strategic Interrupt...")
                      return "[STRATEGIC_INTERRUPT_SIGNAL] LLM Context Poisoned (Recursive Empty Responses)", PerformanceMetrics(
                          iterations=iteration,
                          total_time=time.time() - start_time,
                          input_tokens=input_tokens,
                          output_tokens=output_tokens,
                          total_tokens=total_tokens,
                          prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                          tools_used=tools_used,
                          success=False,
                          tool_calls=tool_calls_recorded
                      )
                 else:
                      # First offense: Polite retry
                      built_messages.append(Message(
                          role=MessageRole.SYSTEM,
                          content="System Error: You returned an empty response. You MUST output content or a tool call."
                      ))
                 continue

            # 2.1.5 Parse Metacognitive Reflection
            reflection_content = ""
            if response.content and "<reflection>" in response.content and "</reflection>" in response.content:
                 try:
                     reflection_content = response.content.split("<reflection>")[1].split("</reflection>")[0].strip()
                     logger.info(f"🤔 Metacognition: {reflection_content}")
                     
                     # Check for Natural Language Interrupt Signal
                     # "I am stuck", "requesting strategic intervention", "I need to stop"
                     interrupt_keywords = ["i am stuck", "requesting strategic intervention", "requesting strategy update"]
                     if any(k in reflection_content.lower() for k in interrupt_keywords):
                         logger.warning(f"⛔ Organic Interrupt Triggered: {reflection_content}")
                         return f"[STRATEGIC_INTERRUPT_SIGNAL] {reflection_content}", PerformanceMetrics(
                            iterations=iteration,
                            total_time=time.time() - start_time,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            total_tokens=total_tokens,
                            prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                            tools_used=tools_used,
                            success=False,
                            tool_calls=tool_calls_recorded
                        )
                 except Exception as e:
                     logger.warning(f"Failed to parse reflection: {e}")
            if not response.tool_calls and response.content:
                # [Stateless Architecture Enforcement]
                # The prompt strictly specifies to output a tool call (even if it's `system_report_failure`).
                # If the LLM outputs plain text instead of a tool call, it's hallucinating.
                # We log this and forcefully return to the main agent loop.
                logger.error(f"⚠️ Action Gap/Hallucination Detected: Expected Tool Call, got clear text.")
                final_response = f"[STATELESS_EXECUTOR_ERROR] The executor hallucinated a response instead of calling a tool: {response.content[:200]}"
                return final_response, PerformanceMetrics(
                    iterations=iteration,
                    total_time=time.time() - start_time,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                    tools_used=tools_used,
                    success=False,
                    tool_calls=tool_calls_recorded
                )
            if response.has_tool_calls:

                normalized_tool_calls = []
                current_call_hashes = []

                for idx, tool_call in enumerate(response.tool_calls or []):
                    fallback_id = f"call_{iteration}_{idx}"

                    if isinstance(tool_call, dict):
                        tool_id = tool_call.get('id') or fallback_id
                        tool_type = tool_call.get('type') or 'function'
                        fn = tool_call.get('function') or {}
                        tool_name = fn.get('name') or tool_call.get('name') or ''
                        tool_args_raw = fn.get('arguments') if fn else tool_call.get('arguments')

                        if isinstance(tool_args_raw, dict):
                            tool_args_str = json.dumps(tool_args_raw, ensure_ascii=False)
                        elif tool_args_raw is None:
                            tool_args_str = "{}"
                        else:
                            tool_args_str = tool_args_raw

                        normalized_tool_calls.append({
                            "id": tool_id,
                            "type": tool_type,
                            "function": {
                                "name": tool_name,
                                "arguments": tool_args_str
                            }
                        })
                        current_call_hashes.append(f"{tool_name}:{tool_args_str}")

                    else:
                        tool_id = getattr(tool_call, 'id', None) or fallback_id
                        tool_name = getattr(tool_call, 'name', '')
                        tool_args = getattr(tool_call, 'arguments', {}) or {}
                        tool_args_str = json.dumps(tool_args, ensure_ascii=False)

                        normalized_tool_calls.append({
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_args_str
                            }
                        })
                        current_call_hashes.append(f"{tool_name}:{tool_args_str}")

                # 检测重复调用 (Loop Detection)
                call_hash = "|".join(current_call_hashes)
                if call_hash == last_tool_call_hash:
                    loop_counter += 1
                    # Strategic Interrupt: If stuck in loop for 5 turns, abort immediately
                    if loop_counter >= 5:
                        logger.warning(f"⛔ Strategic Interrupt: Loop Detected ({call_hash})")
                        final_response = f"[STRATEGIC_INTERRUPT] Caught in a loop executing: {call_hash}. Stopping execution to request a new strategy."
                        success = False
                        # Break out of loop.py, return to agent.py
                        return final_response, PerformanceMetrics(
                            iterations=iteration,
                            total_time=time.time() - start_time,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            total_tokens=total_tokens,
                            prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                            tools_used=tools_used,
                            success=False,
                            tool_calls=tool_calls_recorded
                        )
                else:
                    loop_counter = 0
                last_tool_call_hash = call_hash

                tool_calls_recorded.extend(normalized_tool_calls)

                built_messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content or "",
                    tool_calls=normalized_tool_calls
                ))

                # 执行所有工具调用
                for tool_call in normalized_tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args_raw = tool_call["function"].get("arguments") or "{}"

                    try:
                        tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                    except json.JSONDecodeError:
                        tool_args = {}

                    tool_id = tool_call["id"]
                    tools_used.append(tool_name)
                    
                    if tool_name == "system_task_complete":
                        logger.info(f"🏁 Task legally marked as complete by Executor.")
                        summary = tool_args.get("summary", "")
                        result_str = f"Task Complete. Summary: {summary}"
                        
                        built_messages.append(Message(
                            role=MessageRole.TOOL,
                            content=result_str,
                            tool_call_id=tool_id
                        ))
                        
                        final_response = f"[STATELESS_EXECUTOR_SUCCESS] Task execution finished. Summary: {summary}"
                        success = True
                        return final_response, PerformanceMetrics(
                            iterations=iteration,
                            total_time=time.time() - start_time,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            total_tokens=total_tokens,
                            prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                            tools_used=tools_used,
                            success=success,
                            tool_calls=tool_calls_recorded
                        )
                    
                    # Callback: Tool Start
                    # Callback: Tool Start
                    if step_callback:
                        if asyncio.iscoroutinefunction(step_callback):
                            await step_callback("tool", {"name": tool_name, "args": tool_args})
                        else:
                            step_callback("tool", {"name": tool_name, "args": tool_args})
                    
                    if hasattr(self, 'on_tool_call') and self.on_tool_call:
                        self.on_tool_call(tool_name, tool_args)

                    try:
                        # ⚠️ ULTIMATE TOOL CIRCUIT BREAKER ⚠️
                        # Protect the main loop from custom generated skills that might contain `while True` 
                        # or other blocking operations. Hard timeout at 60 seconds.
                        result = await asyncio.wait_for(
                            self.tools.execute(tool_name, tool_args),
                            timeout=60.0
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"⏱️ 致命超时：工具 '{tool_name}' 运行超过 60 秒未返回！已强制阻断以保全主循环。")
                        result = f"Error: 致命超时 (Timeout)! The tool '{tool_name}' was forcibly terminated because it ran for over 60 seconds and blocked the main executing loop. Do NOT use infinite loops in tools. Background long-running tasks asynchronously."
                    except Exception as try_e:
                        result = f"Error executing tool '{tool_name}': {type(try_e).__name__} - {str(try_e)}"
                    
                    # --- MULTIMODAL HANDLING (Visual Cortex) ---
                    # Check if result is a dict with type='image'
                    image_payload = None
                    result_str = str(result)
                    
                    if isinstance(result, dict) and result.get("type") == "image":
                        image_path = result.get("path")
                        if image_path:
                            try:
                                import base64
                                with open(image_path, "rb") as img_file:
                                    b64_str = base64.b64encode(img_file.read()).decode("utf-8")
                                    
                                image_payload = {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{b64_str}"
                                    }
                                }
                                result_str = f"Screenshot successfully captured at {image_path}. (Image Payload attached to context)"
                                logger.info(f"👁️ Visual Cortex: Image {image_path} injected into context.")
                            except Exception as e:
                                logger.error(f"Failed to encode image: {e}")
                                result_str = f"Error encoding screenshot: {e}"

                    # Construct Message (Append tool result to context)
                    if image_payload:
                        content_block = [
                            {"type": "text", "text": f"Tool Output ({tool_name}): {result_str}"},
                            image_payload
                        ]
                        built_messages.append(Message(
                            role=MessageRole.TOOL,
                            content=content_block, # Native list for Multimodal
                            tool_call_id=tool_id
                        ))
                    else:
                        built_messages.append(Message(
                            role=MessageRole.TOOL,
                            content=result_str,
                            tool_call_id=tool_id
                        ))

                    # 采集错误信息 (Failure Attribution)
                    result_lower = result_str.lower()
                    is_error = False
                    
                    # More robust error detection (avoids false positives like "No error found")
                    if tool_name == "shell":
                        # For shell, only trust explicit failure indicators
                        if "exit code:" in result_lower and "exit code: 0" not in result_lower:
                            is_error = True
                        elif "command not found" in result_lower or "permission denied" in result_lower:
                            is_error = True
                    else:
                        # For other tools, check if it starts with Error/Exception or contains explicit failure language
                        if "error:" in result_lower or "exception:" in result_lower or result_lower.startswith("error"):
                            is_error = True
                    
                    if is_error:
                        if tool_name not in tool_errors: tool_errors[tool_name] = []
                        
                        # Try to compress the error to save context window
                        try:
                            compressed = _error_compressor.compress(result_str, source=tool_name)
                            new_error_str = _error_compressor.format_for_llm(compressed)
                        except:
                            new_error_str = result_str[:100]
                            
                        # Entropy-Aware Circuit Breaker (State Delta)
                        # If the new error is DIFFERENT from the last error, the agent is exploring/learning.
                        # We reset the sequential counter.
                        if tool_errors[tool_name]:
                            last_error = tool_errors[tool_name][-1]
                            if new_error_str != last_error:
                                logger.info(f"🔄 Entropy Delta Detected: Agent encountered a new error for {tool_name}. Resetting failure counter.")
                                tool_errors[tool_name] = [] # Reset!
                        
                        tool_errors[tool_name].append(new_error_str)
                        
                        # Strategic Interrupt: Consecutive IDENTICAL Failures
                        sequential_failures = len(tool_errors[tool_name])
                        if sequential_failures >= 3:
                             logger.warning(f"⛔ Strategic Interrupt: {tool_name} failed with IDENTICAL errors {sequential_failures} times sequentially.")
                             final_response = f"[STRATEGIC_INTERRUPT] Tool {tool_name} failed {sequential_failures} times in a row with the exact same error. Stopping to replan."
                             success = False
                             return final_response, PerformanceMetrics(
                                iterations=iteration,
                                total_time=time.time() - start_time,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                total_tokens=total_tokens,
                                prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                                tools_used=tools_used,
                                success=False,
                                tool_calls=tool_calls_recorded
                            )
                    else:
                        # Reset the sequential error count for this tool on a successful run
                        if tool_name in tool_errors:
                            tool_errors[tool_name] = []
                        
                        # Circuit Breaker: Critical Configuration Errors (Missing Keys, Auth)
                        # The user specifically wants the agent to stop and fix if a tool is broken.
                        critical_keywords = [
                            "api_key", "configured", "unauthorized", "access denied", 
                            "authentication failed", "permission denied"
                        ]
                        if any(k in result_str.lower() for k in critical_keywords):
                            logger.warning(f"⛔ Circuit Breaker Triggered: Critical Failure in {tool_name}")
                            final_response = f"CRITICAL_TOOL_FAILURE: {tool_name} failed with error: {result_str}\n[SYSTEM INTERRUPT] Execution halted for immediate repair."
                            built_messages.append(Message(
                                role=MessageRole.TOOL,
                                content=f"ERROR: {result_str}\n[SYSTEM_INTERRUPT] Critical configuration error detected. Stopping execution loop to allow Strategy Phase to fix this.",
                                tool_call_id=tool_id
                            ))
                            success = False
                            return final_response, PerformanceMetrics(
                                iterations=iteration,
                                total_time=time.time() - start_time,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                total_tokens=total_tokens,
                                prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                                tools_used=tools_used,
                                success=False,
                                tool_calls=tool_calls_recorded
                            )

                    built_messages.append(Message(
                        role=MessageRole.TOOL,
                        content=result_str,
                        tool_call_id=tool_id
                    ))
                    
                    # Callback: Tool Result
                    # Callback: Tool Result
                    if step_callback:
                        if asyncio.iscoroutinefunction(step_callback):
                            await step_callback("tool_result", {"tool": tool_name, "result": result_str})
                        else:
                            step_callback("tool_result", {"tool": tool_name, "result": result_str})
                
                continue
            
            else:
                # 2.3 Action Enforcement 
                # [Stateless Architecture] We no longer need to check for intents because
                # any response that reaches here without tool calls has already been caught
                # by the hallucination detector above.
                final_response = response.content
                built_messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=final_response
                ))
                break
        
        # 3. 检查是否达到最大迭代次数
        if iteration >= hard_limit and not final_response:
            # 构建简易诊断报告
            diag_report = "\n[SYSTEM_DIAGNOSTIC_REPORT]"
            diag_report += f"\n- Reason: Iteration limit reached ({iteration})"
            if tool_errors:
                diag_report += "\n- Tool Failures:"
                for t, errs in tool_errors.items():
                    diag_report += f"\n  * {t}: {errs[-1]}"
            if loop_counter > 0:
                diag_report += f"\n- Loop Warning: Repetitive tool calls detected ({loop_counter} times)"
            
            final_response = f"抱歉，我在 {iteration} 次尝试后还没完成。{diag_report}\n请检查以上诊断信息并提供干预建议。"
            success = False
        else:
            success = True
        
        # 4. 计算性能指标
        elapsed_time = time.time() - start_time
        metrics = PerformanceMetrics(
            iterations=iteration,
            total_time=elapsed_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            prompt_cache_hit_tokens=prompt_cache_hit_tokens,
            tools_used=tools_used,
            success=success,
            tool_calls=tool_calls_recorded or None
        )
        
        logger.debug(
            f"✓ 任务完成: {iteration} 迭代, "
            f"{total_tokens} tokens, "
            f"{metrics.total_time:.2f}s"
        )
        
        return final_response, metrics
