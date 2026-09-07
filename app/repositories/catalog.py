"""A replaceable catalog port and a read-only in-memory implementation."""

from collections.abc import Iterable
from typing import Protocol

from app.domain.catalog import Product


class CatalogRepository(Protocol):
    def list_all(self) -> tuple[Product, ...]: ...

    def get(self, product_id: str) -> Product | None: ...


class InMemoryCatalogRepository:
    def __init__(self, products: Iterable[Product]) -> None:
        self._products: dict[str, Product] = {}
        sku_ids: set[str] = set()
        for product in products:
            if product.id in self._products:
                raise ValueError(f"Duplicate product ID: {product.id}")
            for sku in product.skus:
                if sku.id in sku_ids:
                    raise ValueError(f"Duplicate SKU ID: {sku.id}")
                sku_ids.add(sku.id)
            self._products[product.id] = product

    def list_all(self) -> tuple[Product, ...]:
        return tuple(self._products.values())

    def get(self, product_id: str) -> Product | None:
        return self._products.get(product_id)
