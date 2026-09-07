"""Catalog HTTP adapter; the service itself does not depend on FastAPI."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.catalog_seed import demo_catalog
from app.domain.catalog import Product
from app.repositories.catalog import InMemoryCatalogRepository
from app.services.catalog_service import CatalogQuery, CatalogResult, CatalogService

router = APIRouter(prefix="/commerce/products", tags=["catalog"])
_catalog_service = CatalogService(InMemoryCatalogRepository(demo_catalog()))


def get_catalog_service() -> CatalogService:
    return _catalog_service


@router.get("", response_model=CatalogResult)
def search_products(
    query: Annotated[CatalogQuery, Query()],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> CatalogResult:
    """Search demo products. Prices are CNY yuan; only matching SKUs are returned."""
    return service.search(query)


@router.get("/{product_id}", response_model=Product)
def get_product(
    product_id: str,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Product:
    """Return all SKUs for a demo product, including out-of-stock variants."""
    product = service.repository.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
