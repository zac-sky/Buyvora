"""HTTP adapters for float embeddings and index/relevance_score rerank APIs."""

import asyncio
import json
import math

import httpx

from app.retrieval.types import RetrievalUnavailable


def normalized_vectors(vectors: object, expected: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != expected:
        raise RetrievalUnavailable("embedding_invalid_response")
    output = []
    dimension = None
    for vector in vectors:
        if not isinstance(vector, list) or not 1 <= len(vector) <= 8192:
            raise RetrievalUnavailable("embedding_invalid_response")
        if dimension is not None and len(vector) != dimension:
            raise RetrievalUnavailable("embedding_dimension_mismatch")
        dimension = len(vector)
        try:
            if any(type(value) not in {int, float} or not math.isfinite(value) for value in vector):
                raise RetrievalUnavailable("embedding_invalid_response")
            norm = math.hypot(*vector)
        except OverflowError:
            raise RetrievalUnavailable("embedding_invalid_response") from None
        if not math.isfinite(norm) or norm == 0:
            raise RetrievalUnavailable("embedding_invalid_response")
        output.append([value / norm for value in vector])
    return output


class JsonProvider:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 10,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url, self.api_key, self.model = base_url, api_key, model
        self.timeout, self.transport = timeout, transport

    async def post(self, endpoint: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout,
                                             follow_redirects=False) as client:
                    async with client.stream("POST", self.base_url + endpoint,
                                             headers=headers, json={"model": self.model, **payload}) as response:
                        if response.status_code != 200:
                            raise RetrievalUnavailable("retrieval_provider_unavailable")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 4_000_000:
                                raise RetrievalUnavailable("retrieval_response_too_large")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError("Expected an object")
            return result
        except (httpx.HTTPError, TimeoutError, ValueError, RecursionError):
            raise RetrievalUnavailable("retrieval_provider_unavailable") from None


class CompatibleEmbeddings(JsonProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > 32 or any(not text or len(text) > 4000 for text in texts):
            raise RetrievalUnavailable("embedding_input_limit")
        result = await self.post("/embeddings", {"input": texts, "encoding_format": "float"})
        try:
            rows = result["data"]
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise ValueError("Invalid batch length")
            mapped = {}
            for row in rows:
                index = row["index"]
                if type(index) is not int or index not in range(len(texts)) or index in mapped:
                    raise ValueError("Invalid embedding index")
                mapped[index] = row["embedding"]
            return normalized_vectors([mapped[index] for index in range(len(texts))], len(texts))
        except (KeyError, TypeError, ValueError, OverflowError):
            raise RetrievalUnavailable("embedding_invalid_response") from None


class CompatibleReranker(JsonProvider):
    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        result = await self.post("/rerank", {"query": query, "documents": documents,
                                            "top_n": len(documents), "return_documents": False})
        try:
            rows = result["results"]
            if not isinstance(rows, list) or len(rows) != len(documents):
                raise ValueError("Incomplete rerank output")
            mapped = {}
            for row in rows:
                index, score = row["index"], row["relevance_score"]
                if (type(index) is not int or index not in range(len(documents)) or index in mapped
                        or type(score) not in {int, float} or not math.isfinite(score)):
                    raise ValueError("Invalid rerank item")
                mapped[index] = float(score)
            return [mapped[index] for index in range(len(documents))]
        except (KeyError, TypeError, ValueError, OverflowError):
            raise RetrievalUnavailable("reranker_invalid_response") from None
