"""
Context Packager (Entity B)
Responsible for reconnaissance and gathering context before the Executor (Entity A) begins.
"""

import logging
import json
import re
from typing import Dict, Any, Optional

from genesis.core.base import Message, MessageRole, LLMProvider
from genesis.core.registry import ToolRegistry
from genesis.tools.file_tools import ReadFileTool, ListDirectoryTool
from genesis.tools.shell_tool import ShellTool

logger = logging.getLogger(__name__)

class ContextPackager:
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        
        # Assemble read-only toolkit
        self.tools = ToolRegistry()
        self.tools.register(ReadFileTool())
        self.tools.register(ListDirectoryTool())
        self.tools.register(ShellTool())
        
        self.system_prompt = """You are Genesis Context Packager (Entity B), the Reconnaissance Unit.
Your ONLY purpose is to gather context and prepare a comprehensive Payload for the Executor (Entity A).

【Directives】
1. READ ONLY: You must strictly gather information. Do NOT modify files, write code, or execute destructive commands. Use `shell` strictly for read operations like `ls`, `cat`, `find`, `pwd`, etc.
2. GATHER CONTEXT: Understand the User's objective. Find the relevant files in the project. Read them carefully so Entity A has exactly what it needs to write the solution.
3. PACKAGING: Once you have sufficient context, output your findings within `<MISSION_PAYLOAD>...</MISSION_PAYLOAD>` tags. Do not call further tools after outputting the payload.

【Payload Format】
<MISSION_PAYLOAD>
# Environment Status
(Operating System, Current Directory, relevant active processes, etc)

# Relevant Files
(Exact absolute paths and the relevant content/code snippets that Entity A must edit or know about)

# Constraints & Dependencies
(Missing packages, framework rules, or strict patterns Entity A must follow)
</MISSION_PAYLOAD>

If the user's objective is extremely simple (e.g. conversational, or requires no specific file context), immediately output an empty payload:
<MISSION_PAYLOAD>
No local context required.
</MISSION_PAYLOAD>
"""

    async def build_payload(self, user_input: str, step_callback: Optional[Any] = None) -> str:
        messages = [
            Message(role=MessageRole.SYSTEM, content=self.system_prompt),
            Message(role=MessageRole.USER, content=f"Mission Objective: {user_input}\n\nBegin gathering context now.")
        ]
        
        max_iterations = 6
        payload = "No specific context gathered."
        
        for iteration in range(1, max_iterations + 1):
            if step_callback:
                import asyncio
                if asyncio.iscoroutinefunction(step_callback):
                    await step_callback("strategy", f"[Packager] Scouting Environment (Step {iteration})...")
                else:
                    step_callback("strategy", f"[Packager] Scouting Environment (Step {iteration})...")
                    
            try:
                response = await self.provider.generate(
                    messages=[m.to_dict() for m in messages],
                    tools=self.tools.get_all_schemas()
                )
                
                # Check if Packager has output the payload
                if response.content and "<MISSION_PAYLOAD>" in response.content:
                    extracted = re.search(r"<MISSION_PAYLOAD>(.*?)</MISSION_PAYLOAD>", response.content, re.DOTALL)
                    if extracted:
                        payload = extracted.group(1).strip()
                    else:
                        payload = response.content
                    logger.info("📦 Mission Payload Generated.")
                    break
                    
                messages.append(Message(role=MessageRole.ASSISTANT, content=response.content, tool_calls=response.tool_calls))
                
                if response.tool_calls:
                    for tc in response.tool_calls:
                        tool_name = tc.get("function", {}).get("name")
                        args_str = tc.get("function", {}).get("arguments", "{}")
                        call_id = tc.get("id")
                        
                        try:
                            args = json.loads(args_str)
                        except:
                            args = {}
                            
                        if step_callback:
                            import asyncio
                            if asyncio.iscoroutinefunction(step_callback):
                                await step_callback("tool", {"name": f"[Packager] {tool_name}", "args": args})
                            else:
                                step_callback("tool", {"name": f"[Packager] {tool_name}", "args": args})
                        
                        tool = self.tools.get_tool(tool_name)
                        if tool:
                            try:
                                result = await tool.execute(**args)
                                result_str = str(result)
                            except Exception as e:
                                result_str = f"Error: {e}"
                        else:
                            result_str = f"Error: Tool {tool_name} not found."
                            
                        # Prevent payload bloat
                        if len(result_str) > 8000:
                            result_str = result_str[:8000] + "\n...[TRUNCATED]"
                            
                        if step_callback:
                            import asyncio
                            if asyncio.iscoroutinefunction(step_callback):
                                await step_callback("tool_result", {"result": result_str})
                            else:
                                step_callback("tool_result", {"result": result_str})
                                
                        messages.append(Message(
                            role=MessageRole.TOOL,
                            content=result_str,
                            name=tool_name,
                            tool_call_id=call_id
                        ))
                else:
                    # No tools called and no payload tag? Force break.
                    if response.content:
                        payload = response.content
                    break
                    
            except Exception as e:
                logger.error(f"Context Packager error: {e}")
                payload = f"Error during context gathering: {e}"
                break
                
        return payload
