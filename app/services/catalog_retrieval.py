"""Rank only eligible SKUs and build product cards from the ranked matches."""

from app.domain.catalog import Product
from app.retrieval.engine import RetrievalEngine
from app.retrieval.types import Document, RetrievalInfo
from app.services.catalog_service import CatalogQuery, CatalogResult, CatalogService


class CatalogRetrieval:
    def __init__(self, catalog: CatalogService, engine: RetrievalEngine) -> None:
        self.catalog, self.engine = catalog, engine

    async def search(self, query: CatalogQuery) -> CatalogResult:
        if query.search_mode == "keyword" or not query.q:
            result = self.catalog.search(query)
            result.retrieval = RetrievalInfo(strategy="keyword" if query.q else "browse",
                                             candidate_count=sum(len(p.skus) for p in self.catalog.candidates(query)))
            return result
        candidates = self.catalog.candidates(query, match_keywords=False)
        allowed = {sku.id for product in candidates for sku in product.skus}
        documents = [Document(sku.id, " ".join((product.name, product.brand, product.category,
                     product.description, *product.tags, sku.name)))
                     for product in self.catalog.repository.list_all() for sku in product.skus]
        ranked, info = await self.engine.rank(query.q, documents, allowed)
        scores = {item.id: item.score for item in ranked}
        products: list[Product] = []
        product_scores = {}
        for product in candidates:
            skus = tuple(sku for sku in product.skus if sku.id in scores)
            if skus:
                products.append(product.model_copy(update={"skus": skus}))
                product_scores[product.id] = max(scores[sku.id] for sku in skus)
        products.sort(key=lambda product: (-product_scores[product.id],
                      min(sku.price.amount_minor for sku in product.skus), product.id))
        page = products[query.offset:query.offset + query.limit]
        info.scores = {product.id: round(product_scores[product.id], 6) for product in page}
        return CatalogResult(items=page, total=len(products), offset=query.offset, limit=query.limit, retrieval=info)
