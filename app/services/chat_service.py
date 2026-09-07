"""Composition root for the shopping agent; no fixed-reply fallback."""

from app.agent.model import ChatModel, CompatibleChatModel
from app.agent.shopping import ShoppingAgent
from app.agent.tools import ShoppingTools
from app.catalog_seed import demo_catalog
from app.repositories.catalog import InMemoryCatalogRepository
from app.services.catalog_service import CatalogService
from app.settings import Settings


def build_shopping_agent(settings: Settings, model: ChatModel | None = None) -> ShoppingAgent:
    catalog = CatalogService(InMemoryCatalogRepository(demo_catalog()))
    return ShoppingAgent(model or CompatibleChatModel(settings), ShoppingTools(catalog), settings)
