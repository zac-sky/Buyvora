"""Catalog HTTP adapter; the service itself does not depend on FastAPI."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.domain.catalog import Product
from app.services.catalog_retrieval import CatalogRetrieval
from app.services.knowledge_service import KnowledgeQuery, KnowledgeResult, KnowledgeService
from app.services.catalog_service import CatalogQuery, CatalogResult, CatalogService

router = APIRouter(prefix="/commerce", tags=["catalog"])


def get_catalog_service(request: Request) -> CatalogService:
    return request.app.state.search_services.catalog


def get_catalog_retrieval(request: Request) -> CatalogRetrieval:
    return request.app.state.search_services.products


def get_knowledge_service(request: Request) -> KnowledgeService:
    return request.app.state.search_services.knowledge


@router.get("/products", response_model=CatalogResult)
async def search_products(
    query: Annotated[CatalogQuery, Query()],
    service: Annotated[CatalogRetrieval, Depends(get_catalog_retrieval)],
) -> CatalogResult:
    """Search demo products. Prices are CNY yuan; only matching SKUs are returned."""
    return await service.search(query)


@router.get("/products/{product_id}", response_model=Product)
def get_product(
    product_id: str,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Product:
    """Return all SKUs for a demo product, including out-of-stock variants."""
    product = service.repository.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/knowledge", response_model=KnowledgeResult)
async def search_knowledge(
    query: Annotated[KnowledgeQuery, Query()],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeResult:
    return await service.search(query)
