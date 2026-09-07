from fastapi import FastAPI

from app.schemas import ChatRequest, ChatResponse
from app.services.chat_service import build_shopping_reply


app = FastAPI(
    title="Buyvora Agent",
    description="A personal e-commerce agent project.",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return a small liveness response for local development and deployment."""
    return {"status": "ok", "service": "buyvora-agent"}


@app.post("/commerce/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Accept a shopping request and return the current assistant response."""
    return ChatResponse(
        session_id=request.session_id,
        reply=build_shopping_reply(request.message),
    )

