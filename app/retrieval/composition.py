"""One per-app search container, shared between HTTP endpoints and agent tools."""

from dataclasses import dataclass

from app.catalog_seed import demo_catalog
from app.repositories.catalog import InMemoryCatalogRepository
from app.retrieval.engine import RetrievalEngine
from app.retrieval.providers import CompatibleEmbeddings, CompatibleReranker
from app.services.catalog_retrieval import CatalogRetrieval
from app.services.catalog_service import CatalogService
from app.services.knowledge_service import KnowledgeService
from app.settings import Settings


@dataclass
class SearchServices:
    catalog: CatalogService
    products: CatalogRetrieval
    knowledge: KnowledgeService


def build_search_services(settings: Settings) -> SearchServices:
    embeddings = CompatibleEmbeddings(settings.embedding_base_url, settings.embedding_api_key.get_secret_value(),
        settings.embedding_model, settings.retrieval_timeout_seconds) if settings.provider_configured("embedding") else None
    reranker = CompatibleReranker(settings.reranker_base_url, settings.reranker_api_key.get_secret_value(),
        settings.reranker_model, settings.retrieval_timeout_seconds) if settings.provider_configured("reranker") else None

    def engine() -> RetrievalEngine:
        return RetrievalEngine(embeddings, reranker, settings.retrieval_top_n,
                               settings.retrieval_min_similarity, settings.retrieval_timeout_seconds)

    catalog = CatalogService(InMemoryCatalogRepository(demo_catalog()))
    return SearchServices(catalog, CatalogRetrieval(catalog, engine()), KnowledgeService(engine()))
