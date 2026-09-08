"""Composition root for the shopping agent; no fixed-reply fallback."""

from app.agent.model import ChatModel, CompatibleChatModel
from app.agent.shopping import ShoppingAgent
from app.agent.tools import ShoppingTools
from app.retrieval.composition import SearchServices, build_search_services
from app.settings import Settings


def build_shopping_agent(settings: Settings, model: ChatModel | None = None,
                         services: SearchServices | None = None) -> ShoppingAgent:
    services = services or build_search_services(settings)
    tools = ShoppingTools(services.catalog, services.products, services.knowledge)
    return ShoppingAgent(model or CompatibleChatModel(settings), tools, settings)
