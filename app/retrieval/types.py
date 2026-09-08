"""Retrieval contracts shared by the catalog and the knowledge base."""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Document:
    id: str
    text: str


@dataclass(frozen=True)
class ScoredDocument:
    id: str
    score: float


class RetrievalInfo(BaseModel):
    strategy: Literal["keyword", "browse", "vector", "vector_rerank", "keyword_2gram"]
    fallback_reason: str | None = None
    candidate_count: int = 0
    truncated: bool = False
    scores: dict[str, float] = Field(default_factory=dict)


class RetrievalUnavailable(Exception):
    """A sanitized boundary error; provider response bodies are never propagated."""


class Embeddings(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...
