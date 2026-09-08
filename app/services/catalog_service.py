"""Deterministic catalog search reusable by HTTP routes and future agent tools."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.catalog import Category, Product
from app.retrieval.types import RetrievalInfo
from app.repositories.catalog import CatalogRepository


class CatalogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(default="", max_length=200)
    category: Category | None = None
    sku_name: str | None = Field(default=None, min_length=1, max_length=100)
    search_mode: Literal["keyword", "semantic"] = "keyword"
    min_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    max_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    in_stock: bool = True
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)

    @field_validator("q", "sku_name", mode="before")
    @classmethod
    def strip_query(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_price_range(self) -> "CatalogQuery":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price must not exceed max_price")
        return self


class CatalogResult(BaseModel):
    items: list[Product]
    total: int
    limit: int
    offset: int
    source: str = "demo"
    retrieval: RetrievalInfo | None = None


class CatalogService:
    def __init__(self, repository: CatalogRepository) -> None:
        self.repository = repository

    def candidates(self, query: CatalogQuery, match_keywords: bool = True) -> list[Product]:
        terms = query.q.casefold().split() if match_keywords else []
        min_minor = int(query.min_price * 100) if query.min_price is not None else None
        max_minor = int(query.max_price * 100) if query.max_price is not None else None
        matches: list[Product] = []
        for product in self.repository.list_all():
            if query.category is not None and product.category != query.category:
                continue
            product_text = " ".join((product.name, product.brand, product.category,
                                     product.description, *product.tags)).casefold()
            eligible_skus = []
            for sku in product.skus:
                searchable_text = f"{product_text} {sku.name.casefold()}"
                if not all(term in searchable_text for term in terms):
                    continue
                if query.sku_name is not None and query.sku_name.casefold() not in sku.name.casefold():
                    continue
                if query.in_stock and sku.stock == 0:
                    continue
                if min_minor is not None and sku.price.amount_minor < min_minor:
                    continue
                if max_minor is not None and sku.price.amount_minor > max_minor:
                    continue
                eligible_skus.append(sku)
            if eligible_skus:
                eligible_skus.sort(key=lambda sku: (sku.price.amount_minor, sku.id))
                matches.append(product.model_copy(update={"skus": tuple(eligible_skus)}))
        matches.sort(key=lambda product: (product.skus[0].price.amount_minor, product.id))
        return matches

    def search(self, query: CatalogQuery) -> CatalogResult:
        matches = self.candidates(query)
        return CatalogResult(items=matches[query.offset:query.offset + query.limit],
                             total=len(matches), limit=query.limit, offset=query.offset)
