"""Exact cosine retrieval for a small catalog, with observable lexical fallback."""

import asyncio
from collections import Counter
import math
import re
from time import monotonic

from app.retrieval.providers import normalized_vectors
from app.retrieval.types import Document, Embeddings, Reranker, RetrievalInfo, RetrievalUnavailable, ScoredDocument


def tokens(text: str) -> set[str]:
    output = set()
    for part in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.casefold()):
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            output.update(part[index:index + 2] for index in range(max(1, len(part) - 1)))
        else:
            output.add(part)
    return output


def lexical_scores(query: str, documents: list[Document]) -> list[ScoredDocument]:
    terms = tokens(query)
    if not terms:
        return []
    document_terms = [tokens(document.text) for document in documents]
    frequencies = Counter(term for values in document_terms for term in values)
    weights = {term: math.log(1 + len(documents) / (1 + frequencies[term])) for term in terms}
    denominator = sum(weights.values())
    results = []
    for document, values in zip(documents, document_terms):
        common = terms & values
        if common:
            results.append(ScoredDocument(document.id, sum(weights[t] for t in common) / denominator))
    return results


class RetrievalEngine:
    def __init__(self, embeddings: Embeddings | None = None, reranker: Reranker | None = None,
                 top_n: int = 30, min_similarity: float = 0.25, timeout: float = 15) -> None:
        self.embeddings, self.reranker = embeddings, reranker
        self.top_n, self.min_similarity, self.timeout = top_n, min_similarity, timeout
        self._snapshot: tuple[Document, ...] = ()
        self._vectors: list[list[float]] = []
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    async def _document_vectors(self, documents: list[Document]) -> list[list[float]]:
        snapshot = tuple(documents)
        async with self._lock:
            if self._snapshot == snapshot and monotonic() - self._cached_at < 300:
                return self._vectors
            vectors = []
            for index in range(0, len(documents), 32):
                batch = documents[index:index + 32]
                vectors.extend(await self.embeddings.embed([document.text for document in batch]))
            # Validate the whole snapshot, including dimensions across separate batches.
            vectors = normalized_vectors(vectors, len(documents))
            self._snapshot, self._vectors, self._cached_at = snapshot, vectors, monotonic()
            return vectors

    async def rank(self, query: str, documents: list[Document],
                   allowed_ids: set[str] | None = None) -> tuple[list[ScoredDocument], RetrievalInfo]:
        eligible = [document for document in documents if allowed_ids is None or document.id in allowed_ids]
        info = RetrievalInfo(strategy="keyword_2gram", candidate_count=len(eligible))
        if not eligible:
            return [], info
        if self.embeddings is None:
            info.fallback_reason = "embedding_not_configured"
            scored = lexical_scores(query, eligible)
        else:
            try:
                async with asyncio.timeout(self.timeout):
                    vectors = await self._document_vectors(documents)
                    query_vector = normalized_vectors(await self.embeddings.embed([query]), 1)[0]
                    if len(query_vector) != len(vectors[0]):
                        raise RetrievalUnavailable("embedding_dimension_mismatch")
                    scores = {document.id: sum(a * b for a, b in zip(vector, query_vector))
                              for document, vector in zip(documents, vectors)}
                    scored = [ScoredDocument(document.id, scores[document.id]) for document in eligible
                              if scores[document.id] >= self.min_similarity]
                info.strategy = "vector"
            except (RetrievalUnavailable, TimeoutError):
                info.fallback_reason = "embedding_unavailable"
                scored = lexical_scores(query, eligible)
        scored.sort(key=lambda item: (-item.score, item.id))
        info.truncated = len(scored) > self.top_n
        scored = scored[:self.top_n]
        if info.strategy == "vector" and self.reranker is not None and scored:
            try:
                by_id = {document.id: document.text for document in eligible}
                async with asyncio.timeout(self.timeout):
                    scores = await self.reranker.rerank(query, [by_id[item.id] for item in scored])
                if len(scores) != len(scored) or any(type(s) not in {int, float} or not math.isfinite(s) for s in scores):
                    raise RetrievalUnavailable("reranker_invalid_response")
                scored = [ScoredDocument(item.id, score) for item, score in zip(scored, scores)]
                scored.sort(key=lambda item: (-item.score, item.id))
                info.strategy = "vector_rerank"
            except (RetrievalUnavailable, TimeoutError):
                info.fallback_reason = "reranker_unavailable"
        return scored, info
