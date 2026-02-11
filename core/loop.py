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
from .context import SimpleContextBuilder

logger = logging.getLogger(__name__)


class AgentLoop:
    """Agent 主循环 - 核心执行引擎"""
    
    def __init__(
        self,
        tools: ToolRegistry,
        context: SimpleContextBuilder,
        provider: LLMProvider,
        max_iterations: int = 10
    ):
        self.tools = tools
        self.context = context
        self.provider = provider
        self.max_iterations = max_iterations
    
    async def run(
        self,
        user_input: str,
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
        tool_calls_recorded = []
        
        # 1. 构建初始上下文
        built_messages = await self.context.build_messages(user_input, **context_kwargs)
        messages = [msg.to_dict() for msg in built_messages]
        
        # 2. ReAct 循环 (Elastic Endurance)
        iteration = 0
        final_response = ""
        soft_limit = self.max_iterations
        hard_limit = min(25, self.max_iterations * 2.5) # 弹性上限
        
        # 错误跟踪器 (Failure Attribution)
        tool_errors = {} # {tool_name: [error_messages]}
        last_tool_call_hash = None
        loop_counter = 0

        while iteration < hard_limit:
            iteration += 1
            
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
                # 重新构建 messages
                messages = [msg.to_dict() for msg in built_messages]
                response = await self.provider.chat(
                    messages=messages,
                    tools=self.tools.get_definitions()
                )
                input_tokens += getattr(response, "input_tokens", 0) or 0
                output_tokens += getattr(response, "output_tokens", 0) or 0
                total_tokens += getattr(response, "total_tokens", 0) or 0
                
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                final_response = f"Error: LLM 调用失败 - {str(e)}"
                break
            
            # 2.2 检查是否有工具调用 (Acting)
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
                    if loop_counter >= 3:
                        logger.warning(f"⚠️ 检测到工具调用死循环: {call_hash}")
                        # 强行注入警告
                        built_messages.append(Message(
                            role=MessageRole.SYSTEM,
                            content="CRITICAL: You are trapped in a loop. IDENTIFY the reason (e.g., file permission, invalid path, logic error) and STOP repeating the same action. If you cannot fix it, use [HUMAN_INTERVENTION_REQUIRED] with a Diagnostic Report."
                        ))
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
                    
                    if hasattr(self, 'on_tool_call') and self.on_tool_call:
                        self.on_tool_call(tool_name, tool_args)

                    result = await self.tools.execute(tool_name, tool_args)
                    
                    # 采集错误信息 (Failure Attribution)
                    if "error" in str(result).lower() or "failed" in str(result).lower():
                        if tool_name not in tool_errors: tool_errors[tool_name] = []
                        tool_errors[tool_name].append(str(result)[:100])

                    built_messages.append(Message(
                        role=MessageRole.TOOL,
                        content=str(result),
                        tool_call_id=tool_id
                    ))
                
                continue
            
            else:
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
