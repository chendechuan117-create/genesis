from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
from genesis.v4.agent import GenesisV4

app = FastAPI(title="Genesis V4 API", description="LLM Application Layer for Genesis", version="1.0.0")

class ChatRequest(BaseModel):
    user_input: str
    image_paths: Optional[List[str]] = None
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    success: bool
    iterations: int
    duration_ms: float

@app.post("/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main endpoint for other systems to query Genesis as a cognitive API.
    """
    try:
        # Import inside to avoid circular dependencies
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from factory import create_agent
        
        # Temporary instantiation per request (stateless mode)
        agent = create_agent()
        
        result = await agent.process(request.user_input, image_paths=request.image_paths)
        
        return ChatResponse(
            response=result["response"],
            success=result["metrics"].success,
            iterations=result["metrics"].iterations,
            duration_ms=result["metrics"].total_time * 1000
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}
