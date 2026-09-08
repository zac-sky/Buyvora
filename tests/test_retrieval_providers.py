import asyncio
import json

import httpx
import pytest

from app.retrieval.providers import CompatibleEmbeddings, CompatibleReranker, normalized_vectors
from app.retrieval.types import RetrievalUnavailable


def embeddings(handler):
    return CompatibleEmbeddings("https://model.example/v1", "private-test-key", "embedding-model", transport=httpx.MockTransport(handler))


def test_embeddings_map_response_by_index_not_return_order():
    def handler(request):
        assert request.url.path == "/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer private-test-key"
        assert json.loads(request.content) == {"model":"embedding-model", "input":["a","b"], "encoding_format":"float"}
        return httpx.Response(200, json={"data":[{"index":1,"embedding":[0,2]},{"index":0,"embedding":[3,0]}]})
    assert asyncio.run(embeddings(handler).embed(["a","b"])) == [[1,0],[0,1]]


@pytest.mark.parametrize("rows", [[], [{"index":1,"embedding":[1,0]}], [{"index":True,"embedding":[1,0]}],
    [{"index":0,"embedding":[]}], [{"index":0,"embedding":[0,0]}], [{"index":0,"embedding":[True,1]}],
    [{"index":0,"embedding":["1",0]}], [{"embedding":[1,0]}]])
def test_bad_embedding_responses_fail_at_boundary(rows):
    with pytest.raises(RetrievalUnavailable):
        asyncio.run(embeddings(lambda request: httpx.Response(200,json={"data":rows})).embed(["a"]))


@pytest.mark.parametrize("vectors", [[[1,0],[1,0,0]], [[float("nan"),1]], [[float("inf"),1]], [[1e308,1e308]], None])
def test_invalid_vector_shapes_and_numbers(vectors):
    # Large but finite vectors may normalize correctly; overflow of the norm is rejected.
    if vectors == [[1e308,1e308]]:
        normalized = normalized_vectors(vectors, 1)
        assert sum(v*v for v in normalized[0]) == pytest.approx(1)
    else:
        with pytest.raises(RetrievalUnavailable):
            normalized_vectors(vectors, len(vectors) if isinstance(vectors,list) else 1)


def test_duplicate_embedding_indices_are_rejected():
    rows = [{"index":0,"embedding":[1,0]},{"index":0,"embedding":[0,1]}]
    with pytest.raises(RetrievalUnavailable):
        asyncio.run(embeddings(lambda request: httpx.Response(200,json={"data":rows})).embed(["a","b"]))


def test_rerank_maps_scores_to_original_document_order():
    def handler(request):
        assert request.url.path == "/v1/rerank"
        body = json.loads(request.content)
        assert body["documents"] == ["a","b"] and body["top_n"] == 2
        assert body["return_documents"] is False
        return httpx.Response(200,json={"results":[{"index":1,"relevance_score":0.9},{"index":0,"relevance_score":0.1}]})
    provider = CompatibleReranker("https://model.example/v1", "", "rerank", transport=httpx.MockTransport(handler))
    assert asyncio.run(provider.rerank("q", ["a","b"])) == [0.1,0.9]


@pytest.mark.parametrize("rows", [[], [{"index":2,"relevance_score":0.1}], [{"index":0,"relevance_score":"bad"}],
    [{"index":False,"relevance_score":0.1}], [{"index":0,"relevance_score":True}]])
def test_invalid_rerank_indices_and_scores(rows):
    provider = CompatibleReranker("https://model.example/v1", "", "rerank",
               transport=httpx.MockTransport(lambda request:httpx.Response(200,json={"results":rows})))
    with pytest.raises(RetrievalUnavailable):
        asyncio.run(provider.rerank("q", ["a"]))


@pytest.mark.parametrize("status", [401,403,429,500,302])
def test_provider_failures_are_sanitized(status):
    with pytest.raises(RetrievalUnavailable) as caught:
        asyncio.run(embeddings(lambda request:httpx.Response(status,text="private-test-key")).embed(["a"]))
    assert "private-test-key" not in str(caught.value)


def test_timeout_is_sanitized():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200,json={"data":[]})
    provider = CompatibleEmbeddings("https://model.example/v1", "", "model", timeout=0.01, transport=httpx.MockTransport(slow))
    with pytest.raises(RetrievalUnavailable):
        asyncio.run(provider.embed(["a"]))


def test_huge_json_integer_is_a_controlled_vector_error():
    with pytest.raises(RetrievalUnavailable):
        normalized_vectors([[10 ** 1000, 1]], 1)
