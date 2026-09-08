"""HTTP entry point. An app factory keeps configuration and test state isolated."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.agent.errors import AgentError
from app.agent.model import ChatModel
from app.retrieval.composition import build_search_services
from app.routes.catalog import router as catalog_router
from app.schemas import ChatRequest, ChatResponse
from app.services.chat_service import build_shopping_agent
from app.settings import Settings, load_settings


def create_app(settings: Settings | None = None, model: ChatModel | None = None) -> FastAPI:
    application = FastAPI(title="Buyvora Agent", description="A personal e-commerce agent project.", version="0.3.0")
    application.include_router(catalog_router)
    configuration_error = False
    try:
        configuration = settings if settings is not None else load_settings()
    except (ValidationError, OSError, ValueError):
        configuration = Settings()
        configuration_error = True
    application.state.search_services = build_search_services(configuration)
    agent = build_shopping_agent(configuration, model, application.state.search_services) if configuration.configured or model is not None else None

    @application.exception_handler(AgentError)
    async def agent_error_handler(request: Request, error: AgentError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code,
                            content={"detail": {"code": error.code, "message": error.message}})

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "buyvora-agent"}

    @application.get("/ready")
    async def ready() -> dict:
        return {"model_configured": agent is not None,
                "configuration_valid": not configuration_error,
                "catalog_source": "demo", "session_storage": "memory",
                "embedding_configured": configuration.provider_configured("embedding"),
                "reranker_configured": configuration.provider_configured("reranker")}

    @application.post("/commerce/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        if agent is None:
            if configuration_error:
                raise AgentError("model_config_invalid", "模型配置格式无效，请检查本地 .env 或环境变量。", 503)
            raise AgentError("model_not_configured", "请在本地配置 LLM_BASE_URL、LLM_MODEL 和 LLM_API_KEY 后重启服务。", 503)
        return await agent.reply(request)

    return application


app = create_app()
