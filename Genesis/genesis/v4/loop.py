"""
Genesis V4 核心执行引擎 (State Machine)
实现 G-Process (Thinker) -> Op-Process (Executor) -> C-Process (Reflector) 的解耦管线
"""

import json
import re
import time
import asyncio
import logging
import traceback
from typing import List, Dict, Any, Tuple, Optional

from genesis.core.base import Message, MessageRole, LLMProvider, PerformanceMetrics, ToolCall
from genesis.core.registry import ToolRegistry
from genesis.v4.manager import FactoryManager, NodeVault, NodeManagementTools

logger = logging.getLogger(__name__)

class V4Loop:
    """
    V4 核心管线
    
    Phases:
    1. G_PHASE (大脑): 拥有历史上下文，只能搜索。循环直至输出 Task Payload。
    2. OP_PHASE (手脚): 纯净上下文，接收 Payload，拥有执行工具，执行完退出。
    3. C_PHASE (反思): (Post-loop) 仅允许节点管理工具，沉淀知识。
    """

    def __init__(
        self,
        tools: ToolRegistry,
        provider: LLMProvider,
        max_iterations: int = 200,
    ):
        self.tools = tools
        self.provider = provider
        self.max_iterations = max_iterations
        
        # 单例管理器
        self.factory = FactoryManager()
        self.vault = NodeVault()
        
        self.metrics = PerformanceMetrics()
        
        # 共享状态（用于最后反思和记忆）
        self.user_input = ""
        self.g_messages: List[Message] = []
        self.op_messages: List[Message] = []

    async def run(self, user_input: str, step_callback: Any = None) -> Tuple[str, PerformanceMetrics]:
        """执行主管线 G -> Op -> C"""
        self.metrics.start_time = time.time()
        self.user_input = user_input
        
        final_response = ""
        
        try:
            # === Phase 1: G-Process (大脑构思) ===
            task_payload = await self._run_g_phase(user_input, step_callback)
            
            if not task_payload:
                final_response = "大脑 (G) 构思失败，无法生成有效任务派发书。"
                self.metrics.success = False
            else:
                # 渲染派发书给用户看
                rendered = self.factory.render_dispatch_for_human(task_payload)
                await self._safe_callback(step_callback, "blueprint", rendered)
                
                # === Phase 2: Op-Process (瞎子执行) ===
                final_response = await self._run_op_phase(task_payload, step_callback)
                
        except Exception as e:
            logger.error(f"Pipeline execution error: {traceback.format_exc()}")
            final_response = f"系统执行异常: {str(e)}"
            self.metrics.success = False
            
        self.metrics.total_time = time.time() - self.metrics.start_time
        
        # === Phase 3: C-Process (反思沉淀) ===
        # 只有在有足够执行动作时才进行反思
        if len(self.op_messages) > 2:
            await self._run_c_phase(step_callback)
            
        # 保存这轮完整对话作为短期记忆
        self._save_memory(final_response)
        
        return final_response, self.metrics

    async def _run_g_phase(self, user_input: str, step_callback: Any) -> Optional[Dict[str, Any]]:
        """运行 G-Process，负责搜索和组装任务"""
        logger.info(">>> Entering Phase 1: G-Process (Thinker)")
        await self._safe_callback(step_callback, "loop_start", {"phase": "G_PHASE"})
        
        g_prompt = self.factory.build_g_prompt()
        self.g_messages = [
            Message(role=MessageRole.SYSTEM, content=g_prompt),
            Message(role=MessageRole.USER, content=user_input)
        ]
        
        search_tools = [self.tools.get("search_knowledge_nodes")]
        search_tools = [t for t in search_tools if t]
        schema = [t.to_schema() for t in search_tools]
        
        for i in range(self.max_iterations):
            response = await self.provider.chat(
                messages=[m.to_dict() for m in self.g_messages],
                tools=schema,
                stream=True,
                stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data)
            )
            
            self._update_metrics(response)
            
            self.g_messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None
            ))
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self._safe_callback(step_callback, "tool_start", {"name": tc.name, "args": tc.arguments})
                    
                    if tc.name == "search_knowledge_nodes":
                        res = await self.tools.execute(tc.name, tc.arguments)
                        await self._safe_callback(step_callback, "search_result", {"name": tc.name, "result": res})
                    else:
                        res = f"G-Process has no permission to run tool {tc.name}"
                        
                    if not self.metrics.tools_used: self.metrics.tools_used = []
                    self.metrics.tools_used.append(tc.name)
                    
                    self.g_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
                continue
                
            # 纯文本回复，尝试解析 Dispatch Payload
            payload = self._parse_dispatch_payload(response.content)
            if payload:
                logger.info("G-Process successfully created Task Payload.")
                return payload
            else:
                # G 输出了普通文本但没有符合格式，强制提示它交接
                self.g_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content="你必须输出 ```dispatch ... ``` 格式的任务派发书来将任务交给 Op 执行器。否则流程无法继续。"
                ))
                continue
                
        logger.warning("G-Process reached max iterations without outputting payload.")
        return None

    def _parse_dispatch_payload(self, content: str) -> Optional[Dict[str, Any]]:
        """从 G 的输出中提取 dispatch 块并转换为字典"""
        match = re.search(r"```dispatch\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
        if not match:
            return None
            
        block = match.group(1).strip()
        
        payload = {
            "op_intent": "未定义目标",
            "active_nodes": [],
            "instructions": ""
        }
        
        # 简单提取，按关键字分割
        lines = block.split('\n')
        current_key = None
        instructions_lines = []
        
        for line in lines:
            if line.startswith("OP_INTENT:"):
                payload["op_intent"] = line[10:].strip()
            elif line.startswith("ACTIVE_NODES:"):
                nodes_str = line[13:].strip()
                if nodes_str and nodes_str.upper() != "NONE":
                    payload["active_nodes"] = [n.strip() for n in nodes_str.split(',')]
            elif line.startswith("INSTRUCTIONS:"):
                current_key = "instructions"
            elif current_key == "instructions":
                instructions_lines.append(line)
                
        if instructions_lines:
            payload["instructions"] = "\n".join(instructions_lines).strip()
            
        return payload

    async def _run_op_phase(self, task_payload: Dict[str, Any], step_callback: Any) -> str:
        """运行 Op-Process，纯粹的执行器"""
        logger.info(">>> Entering Phase 2: Op-Process (Executor)")
        await self._safe_callback(step_callback, "loop_start", {"phase": "OP_PHASE"})
        
        op_prompt = self.factory.build_op_prompt(task_payload)
        # Op 只有 system prompt，没有 user prompt (意图在 system 里了)
        self.op_messages = [Message(role=MessageRole.SYSTEM, content=op_prompt)]
        
        # 获取所有执行工具 (除了反思专属的)
        all_tools = []
        c_exclusive = ["record_context_node", "record_lesson_node", "delete_node", "search_knowledge_nodes"]
        
        for name in self.tools.list_tools():
            if name not in c_exclusive:
                t = self.tools.get(name)
                if t:
                    all_tools.append(t)
                    
        schema = [t.to_schema() for t in all_tools]
        
        for i in range(self.max_iterations):
            response = await self.provider.chat(
                messages=[m.to_dict() for m in self.op_messages],
                tools=schema,
                stream=True,
                stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data)
            )
            
            self._update_metrics(response)
            
            self.op_messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None
            ))
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self._safe_callback(step_callback, "tool_start", {"name": tc.name, "args": tc.arguments})
                    
                    if tc.name in c_exclusive:
                        res = f"Error: Op-Process 禁止使用工具 {tc.name}"
                    else:
                        res = await self.tools.execute(tc.name, tc.arguments)
                        
                    await self._safe_callback(step_callback, "tool_result", {"name": tc.name, "result": res})
                    
                    if not self.metrics.tools_used: self.metrics.tools_used = []
                    self.metrics.tools_used.append(tc.name)
                    
                    self.op_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
                continue
                
            # 没有工具调用，Op 结束任务并给出最终结果
            if not response.content.strip():
                self.op_messages.append(Message(role=MessageRole.SYSTEM, content="[系统警告] 收到空响应。请继续执行或总结最终结果。"))
                continue
                
            return response.content
            
        logger.warning("Op-Process reached max iterations.")
        return "达到最大迭代次数限制，强制终止。"

    async def _run_c_phase(self, step_callback: Any):
        """运行 C-Process 反思循环，基于 Op 的执行轨迹"""
        logger.info(">>> Entering Phase 3: C-Process (Reflector)")
        
        summary_lines = ["[Op 执行过程摘要]"]
        
        # 从 Op 的轨迹中提取摘要
        step_idx = 1
        for m in self.op_messages:
            if m.role == MessageRole.TOOL:
                preview = str(m.content)[:200].replace("\n", " ") + "..." if len(str(m.content)) > 200 else str(m.content)
                summary_lines.append(f"{step_idx}. [TOOL] {m.name} -> {preview}")
                step_idx += 1
            elif m.role == MessageRole.ASSISTANT and not m.tool_calls:
                preview = str(m.content)[:100].replace("\n", " ") + "..."
                summary_lines.append(f"{step_idx}. [AI Result] {preview}")
                step_idx += 1
                
        execution_summary = "\n".join(summary_lines)
        
        reflection_system_prompt = f"""你是 Genesis 的后台反思进程 (C-Process)。
你的任务是审查以下执行器 (Op) 的 [执行过程摘要]，从中提取高价值的“经验”或“环境上下文”，并将其沉淀到知识库中。

{execution_summary}

[核心原则]
1. **高价值增量**：只记录 (1) 真正解决了问题的关键步骤 (LESSON) (2) 新发现的固定环境参数/用户偏好 (CONTEXT)。不要记流水账。
2. **查重优先**：在写入前，先调用 `search_knowledge_nodes` 确认库里是否已经有了。
3. **机器码原则**：LESSON 的 action_steps 必须是可执行的命令，不能是“检查一下”。
4. **NO_ACTION**：如果没有值得沉淀的，直接回复 "NO_ACTION"。

[可用工具]
- search_knowledge_nodes: 查重
- record_context_node: 记状态/环境
- record_lesson_node: 记流程/经验
- delete_node: 删错误节点
"""
        c_messages = [Message(role=MessageRole.SYSTEM, content=reflection_system_prompt)]
        
        c_tool_names = ["search_knowledge_nodes", "record_context_node", "record_lesson_node", "delete_node"]
        c_tools = [self.tools.get(n) for n in c_tool_names if self.tools.get(n)]
        c_schema = [t.to_schema() for t in c_tools]
        
        for _ in range(3):
            try:
                response = await self.provider.chat(
                    messages=[m.to_dict() for m in c_messages],
                    tools=c_schema,
                    stream=False
                )
                
                content = response.content
                tool_calls = response.tool_calls
                
                c_messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=content,
                    tool_calls=[tc.__dict__ for tc in tool_calls] if tool_calls else None
                ))
                
                if "NO_ACTION" in content:
                    logger.info("C-Process decided NO_ACTION.")
                    break
                    
                if not tool_calls:
                    break
                    
                for tc in tool_calls:
                    if tc.name not in c_tool_names:
                        res = f"Error: C-Process 禁止使用工具 {tc.name}"
                    else:
                        res = await self.tools.execute(tc.name, tc.arguments)
                        await self._safe_callback(step_callback, "tool_result", {"name": f"C-Process::{tc.name}", "result": res})
                    
                    c_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
            except Exception as e:
                logger.error(f"Reflection step failed: {e}")
                break

    def _save_memory(self, agent_response: str):
        """保存本次对话到短期记忆"""
        try:
            if not self.user_input:
                return
            mgmt = NodeManagementTools(self.vault)
            mgmt.store_conversation(self.user_input, agent_response)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def _update_metrics(self, response: Any):
        self.metrics.input_tokens += response.input_tokens
        self.metrics.output_tokens += response.output_tokens
        self.metrics.total_tokens += response.total_tokens
        self.metrics.iterations += 1

    async def _safe_callback(self, callback, event, data):
        """安全调用回调"""
        if not callback: return
        try:
            res = callback(event, data)
            if asyncio.iscoroutine(res): await res
        except Exception as e:
            logger.error(f"Callback error ({event}): {e}")

    async def _stream_proxy(self, callback, event, data):
        """LLM 流式回调代理"""
        if callback: await self._safe_callback(callback, event, data)
