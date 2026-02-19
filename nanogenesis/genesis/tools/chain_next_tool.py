from genesis.core.base import Tool
from typing import Dict, Any

class ChainNextTool(Tool):
    """
    Memento Protocol Tool: Schedule the next autonomous step.
    Use this to continue a complex workflow without stopping.
    """
    
    @property
    def name(self) -> str:
        return "chain_next"
        
    @property
    def description(self) -> str:
        return (
            "Schedule the next autonomous step. "
            "Use this when you have completed the current step and want to immediately trigger the next one. "
            "Think of it as 'The Memento Protocol'. "
            "Args: instruction (What to do next), reason (Why chaining is needed)"
        )
        
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "The specific instruction for the next step (e.g., 'Run the test script')."
                },
                "reason": {
                    "type": "string",
                    "description": "Why you are chaining this step."
                }
            },
            "required": ["instruction"]
        }
        
    async def execute(self, instruction: str, reason: str = "") -> str:
        return f"Next step scheduled: {instruction}"
