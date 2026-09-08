import asyncio

import pytest
from fastapi.testclient import TestClient

from app.domain.catalog import Money, Product, Sku
from app.main import create_app
from app.repositories.catalog import InMemoryCatalogRepository
from app.retrieval.engine import RetrievalEngine
from app.retrieval.types import Document, RetrievalUnavailable
from app.services.catalog_retrieval import CatalogRetrieval
from app.services.catalog_service import CatalogQuery, CatalogService
from app.services.knowledge_service import KnowledgeQuery, KnowledgeService, load_chunks
from app.settings import Settings


class Vectors:
    def __init__(self, mapping):
        self.mapping = mapping
        self.requests = []

    async def embed(self, texts):
        self.requests.append(texts)
        return [self.mapping[text] for text in texts]


class BrokenEmbeddings:
    async def embed(self, texts):
        raise RetrievalUnavailable("provider-private-error")


class Scores:
    def __init__(self, scores):
        self.scores = scores
        self.documents = None

    async def rerank(self, query, documents):
        self.documents = documents
        return self.scores


def test_vector_search_uses_cosine_and_reuses_document_cache():
    async def scenario():
        vectors = Vectors({"first": [1,0], "second": [0,1], "query": [2,1], "other": [0,2]})
        engine = RetrievalEngine(vectors)
        docs = [Document("a", "first"), Document("b", "second")]
        first, info = await engine.rank("query", docs)
        assert [item.id for item in first] == ["a", "b"]
        assert first[0].score == pytest.approx(2 / (5 ** 0.5))
        assert info.strategy == "vector" and info.fallback_reason is None
        second, _ = await engine.rank("other", docs)
        assert [item.id for item in second] == ["b"]
        assert vectors.requests == [["first", "second"], ["query"], ["other"]]
    asyncio.run(scenario())


def test_cache_rebuilds_when_document_content_changes():
    async def scenario():
        vectors = Vectors({"old": [1,0], "new": [0,1], "query": [0,1]})
        engine = RetrievalEngine(vectors)
        await engine.rank("query", [Document("same-id", "old")])
        result, _ = await engine.rank("query", [Document("same-id", "new")])
        assert [item.id for item in result] == ["same-id"]
        assert ["new"] in vectors.requests
    asyncio.run(scenario())


def test_reranker_reorders_only_retrieved_candidates():
    vectors = Vectors({"first": [1,0], "second": [1,1], "query": [1,0]})
    reranker = Scores([0.1, 0.9])
    result, info = asyncio.run(RetrievalEngine(vectors, reranker).rank("query", [Document("a","first"),Document("b","second")]))
    assert [item.id for item in result] == ["b", "a"]
    assert reranker.documents == ["first", "second"]
    assert info.strategy == "vector_rerank"


@pytest.mark.parametrize("scores", [[0.5], [float("nan"), 0.3], [True, 0.3]])
def test_bad_reranker_preserves_vector_order_and_reports_fallback(scores):
    vectors = Vectors({"first": [1,0], "second": [1,1], "query": [1,0]})
    result, info = asyncio.run(RetrievalEngine(vectors, Scores(scores)).rank("query", [Document("a","first"),Document("b","second")]))
    assert [item.id for item in result] == ["a", "b"]
    assert info.strategy == "vector"
    assert info.fallback_reason == "reranker_unavailable"


@pytest.mark.parametrize("embedding,reason", [(None,"embedding_not_configured"),(BrokenEmbeddings(),"embedding_unavailable")])
def test_embedding_fallback_is_observable_and_never_invents_semantic_vectors(embedding, reason):
    result, info = asyncio.run(RetrievalEngine(embedding).rank("通勤用的蓝牙耳机", [Document("a","通勤蓝牙耳机"),Document("b","机械键盘")]))
    assert [item.id for item in result] == ["a"]
    assert info.strategy == "keyword_2gram"
    assert info.fallback_reason == reason


def test_dimension_mismatch_falls_back_without_dot_product_truncation():
    vectors = Vectors({"蓝牙耳机": [1,0], "耳机": [1,0,0]})
    result, info = asyncio.run(RetrievalEngine(vectors).rank("耳机", [Document("a","蓝牙耳机")]))
    assert result[0].id == "a"
    assert info.fallback_reason == "embedding_unavailable"


def test_empty_eligible_set_never_calls_provider():
    vectors = Vectors({})
    result, info = asyncio.run(RetrievalEngine(vectors).rank("query", [Document("a","first")], set()))
    assert result == [] and info.candidate_count == 0
    assert not vectors.requests


def test_filtering_precedes_top_n_and_same_sku_constraints_hold():
    products = [Product(id="expensive", name="Expensive", brand="Test", category="headphones", description="", skus=(
        Sku(id="costly", name="白色", price=Money(amount_minor=50000), stock=1),)),
        Product(id="eligible", name="Eligible", brand="Test", category="headphones", description="", skus=(
        Sku(id="cheap-white", name="白色", price=Money(amount_minor=15000), stock=1),
        Sku(id="cheap-black", name="黑色", price=Money(amount_minor=10000), stock=0),))]
    catalog = CatalogService(InMemoryCatalogRepository(products))
    class Provider:
        async def embed(self, texts):
            return [[0.8,0.6] if "Eligible" in text else [1,0] for text in texts]
    service = CatalogRetrieval(catalog, RetrievalEngine(Provider(), top_n=1))
    query = CatalogQuery(q="earphones", search_mode="semantic", max_price=200, sku_name="白色")
    result = asyncio.run(service.search(query))
    assert [p.id for p in result.items] == ["eligible"]
    assert [sku.id for sku in result.items[0].skus] == ["cheap-white"]
    assert result.retrieval.candidate_count == 1
    assert len(catalog.repository.get("eligible").skus) == 2


def test_retrieval_truncation_is_reported():
    engine = RetrievalEngine(top_n=1)
    result, info = asyncio.run(engine.rank("耳机", [Document("a","耳机"), Document("b","耳机")]))
    assert len(result) == 1 and info.truncated


def test_semantic_http_search_uses_structured_filters_and_shows_strategy():
    client = TestClient(create_app(Settings()))
    response = client.get("/commerce/products", params={"q":"通勤用的蓝牙耳机", "search_mode":"semantic", "max_price":"300", "category":"headphones"})
    assert response.status_code == 200
    body = response.json()
    assert body["items"]
    assert body["retrieval"]["strategy"] == "keyword_2gram"
    for product in body["items"]:
        assert product["category"] == "headphones"
        assert all(s["stock"] > 0 and s["price"]["amount_minor"] <= 30000 for s in product["skus"])
    assert client.get("/commerce/products", params={"search_mode":"invalid"}).status_code == 422
    assert client.get("/commerce/products", params={"sku_name":" "}).status_code == 422


def test_sku_filter_also_applies_to_keyword_browse():
    body = TestClient(create_app(Settings())).get("/commerce/products", params={"q":"耳机", "sku_name":"白色"}).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "demo-headphones-02"


def test_knowledge_retrieval_returns_real_source_text_and_chunk_ids():
    service = KnowledgeService(RetrievalEngine())
    result = asyncio.run(service.search(KnowledgeQuery(q="扩展坞 USB-C 接口", limit=2)))
    assert result.items[0].source == "knowledge/hubs.md"
    for chunk in result.items:
        assert chunk.text in next(c.text for c in service.chunks if c.id == chunk.id)
        assert chunk.id and chunk.section
    assert result.retrieval.strategy == "keyword_2gram"


def test_knowledge_http_handles_no_match_and_bad_input():
    client = TestClient(create_app(Settings()))
    assert client.get("/commerce/knowledge", params={"q":"火星潜艇"}).json()["items"] == []
    for params in [{"q":" "}, {"q":"耳机","limit":6}, {"q":"耳机","path":"secret"}]:
        assert client.get("/commerce/knowledge", params=params).status_code == 422


def test_chunking_keeps_text_bounded_and_sources_stable(tmp_path):
    text = "具体内容" * 500
    (tmp_path / "guide.md").write_text("# 指南\n\n## 规格\n" + text, encoding="utf-8")
    chunks = load_chunks(tmp_path)
    assert len(chunks) > 1
    assert len({c.id for c in chunks}) == len(chunks)
    assert all(len(c.text) <= 900 and c.text in text for c in chunks)
    assert chunks == load_chunks(tmp_path)


def test_short_document_intro_is_indexed_without_duplicate_tail(tmp_path):
    content = "资料内容" * 210
    (tmp_path / "intro.md").write_text("# 简介\n" + content, encoding="utf-8")
    chunks = load_chunks(tmp_path)
    assert len(chunks) == 1
    assert chunks[0].text == content


def test_cache_expiration_reembeds_documents(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("app.retrieval.engine.monotonic", lambda: now[0])
    async def scenario():
        vectors = Vectors({"doc":[1,0], "q":[1,0]})
        engine = RetrievalEngine(vectors)
        docs = [Document("d","doc")]
        await engine.rank("q", docs)
        now[0] = 301
        await engine.rank("q", docs)
        assert vectors.requests.count(["doc"]) == 2
    asyncio.run(scenario())


def test_concurrent_cache_misses_only_build_one_snapshot():
    async def scenario():
        class SlowVectors(Vectors):
            async def embed(self, texts):
                await asyncio.sleep(0.01)
                return await super().embed(texts)
        vectors = SlowVectors({"doc":[1,0], "q":[1,0]})
        engine = RetrievalEngine(vectors)
        docs = [Document("d","doc")]
        await asyncio.gather(engine.rank("q",docs), engine.rank("q",docs))
        assert vectors.requests.count(["doc"]) == 1
    asyncio.run(scenario())
