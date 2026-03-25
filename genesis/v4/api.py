import os
import logging
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import List, Optional
from genesis.v4.unified_response import UnifiedResponse

logger = logging.getLogger(__name__)

# ── Security ──
_API_KEY = os.environ.get("GENESIS_API_KEY", "")
_ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost"}
_security = HTTPBearer(auto_error=False)


class LocalhostOnlyMiddleware(BaseHTTPMiddleware):
    """Reject non-localhost requests unless GENESIS_API_ALLOW_REMOTE=1"""
    async def dispatch(self, request: Request, call_next):
        if os.environ.get("GENESIS_API_ALLOW_REMOTE") == "1":
            return await call_next(request)
        client_host = request.client.host if request.client else None
        if client_host not in _ALLOWED_HOSTS:
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "only localhost allowed"}, status_code=403)
        return await call_next(request)


def _check_api_key(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security)):
    """If GENESIS_API_KEY is set, require Bearer token match."""
    if not _API_KEY:
        return  # no key configured, open access (localhost-only anyway)
    if not credentials or credentials.credentials != _API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing api key")


app = FastAPI(title="Genesis V4 API", description="Internal orchestration entry for Genesis", version="1.1.0")
app.add_middleware(LocalhostOnlyMiddleware)

# ── Singleton Agent ──
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from factory import create_agent
        _agent = create_agent()
        _agent.c_phase_blocking = True
        logger.info("API: agent singleton created")
    return _agent


class ChatRequest(BaseModel):
    user_input: str
    image_paths: Optional[List[str]] = None
    session_id: Optional[str] = None


@app.post("/v1/chat", response_model=UnifiedResponse)
async def chat_endpoint(request: ChatRequest, _=Depends(_check_api_key)):
    """
    Internal orchestration entry. Localhost-only by default.
    Set GENESIS_API_KEY env var to require Bearer auth.
    """
    try:
        agent = _get_agent()
        result = await agent.process(request.user_input, image_paths=request.image_paths)
        return result
    except Exception as e:
        logger.error(f"API /v1/chat error: {e}", exc_info=True)
        return UnifiedResponse.from_error("internal error")


@app.get("/health")
def health_check():
    agent = _get_agent() if _agent else None
    provider_ok = False
    if agent and hasattr(agent, 'provider') and hasattr(agent.provider, 'active_provider_name'):
        provider_ok = bool(agent.provider.active_provider_name)
    return {
        "status": "ok" if provider_ok else "degraded",
        "agent_loaded": _agent is not None,
        "provider": agent.provider.active_provider_name if agent and hasattr(agent, 'provider') else None,
    }