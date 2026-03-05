
import logging
import asyncio
from typing import Dict, Any, List, Optional
from genesis.core.base import Message, MessageRole
from genesis.core.loop import AgentLoop
from genesis.core.mission import Mission
from genesis.core.registry import ToolRegistry

logger = logging.getLogger(__name__)

class StrictExecutor:
    """
    Entity B (The Hand): A stateless, isolated executor for Anchors.
    
    Principles:
    1. Isolation: No chat history. Starts fresh for every Anchor.
    2. Determinism: Input (Anchor Params) -> Output (Raw Result).
    3. No Storytelling: Does not "chat" back. Just executes tools and reports.
    """
    
    def __init__(self, tools: ToolRegistry, provider: Any):
        self.tools = tools
        self.provider = provider
        
        # We reuse AgentLoop mechanics but STRIP the context
        self.loop = AgentLoop(
            tools=self.tools,
            context=None, # No context builder needed, we build raw messages
            provider=self.provider,
            max_iterations=5 # Hard limit for single anchor execution
        )

    async def execute_anchor(self, anchor: Mission) -> Dict[str, Any]:
        """
        Execute a single Anchor Node.
        
        Args:
            anchor: The Mission object representing the node.
            
        Returns:
            Dict containing 'success', 'output', 'error'
        """
        logger.info(f"🔧 Entity B: Executing Anchor [{anchor.id[:4]}] {anchor.objective}")
        
        # 1. Build Stateless Prompt (The Isolation Chamber)
        # We manually construct the messages to ensure NO history leakage.
        
        system_prompt = (
            "You are Entity B, a stateless execution engine.\n"
            "Your Identity: You have NO memory, NO personality, and NO past.\n"
            "Your Task: Execute the requested Objective using the provided Tools.\n"
            "Constraints:\n"
            "1. DO NOT chat or explain. Just use tools.\n"
            "2. If you find the answer, output it purely.\n"
            "3. If a tool fails, try to fix it LOCALLY (retry). If impossible, report failure.\n"
            "4. Output format: Just the raw result or a tool call.\n"
        )
        
        user_prompt = (
            f"OBJECTIVE: {anchor.objective}\n"
            f"INPUT PARAMS: {anchor.input_params}\n"
            f"EXPECTED OUTPUT: {anchor.expected_output}\n\n"
            "Execute now."
        )
        
        # We need a temporary context for the loop to work (AgentLoop expects a context object)
        # But we mock it or use a fresh one.
        from genesis.core.context import SimpleContextBuilder
        isolated_context = SimpleContextBuilder(system_prompt=system_prompt)
        isolated_context.add_to_history(Message(role=MessageRole.USER, content=user_prompt))
        
        self.loop.context = isolated_context # Hot-swap context
        
        try:
            # Run the loop
            # The loop will handle ReAct (Thought -> Tool -> Observation)
            # We want the FINAL output or the AGGREGATED tool outputs.
            
            response, metrics = await self.loop.run(
                user_input=user_prompt,
                step_callback=None
            )
            
            success = metrics.success
            
            # DeepSeek suggested: "B output must be strictly verified"
            # Here we just return the raw text + tool outputs.
            # In a stricter version, we would parse the tool outputs directly.
            
            return {
                "success": success,
                "result_raw": response,
                "metrics": metrics
            }
            
        except Exception as e:
            logger.error(f"Entity B Execution Failed: {e}")
            return {
                "success": False,
                "result_raw": str(e),
                "error": str(e)
            }
