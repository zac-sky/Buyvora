"""Retrieve authored Markdown guidance with stable source and chunk identifiers."""

from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.retrieval.engine import RetrievalEngine
from app.retrieval.types import Document, RetrievalInfo

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=3, ge=1, le=5)

    @field_validator("q", mode="before")
    @classmethod
    def strip_query(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class KnowledgeChunk(BaseModel):
    id: str
    title: str
    section: str
    text: str
    source: str


class KnowledgeResult(BaseModel):
    items: list[KnowledgeChunk]
    retrieval: RetrievalInfo
    source: str = "authored_guidance"


def load_chunks(root: Path = KNOWLEDGE_ROOT) -> list[KnowledgeChunk]:
    chunks = []
    for path in sorted(root.glob("*.md")):
        if path.is_symlink():
            continue
        text = path.read_text(encoding="utf-8-sig")
        title = text.splitlines()[0].lstrip("# ") if text else path.stem
        sections = re.split(r"(?m)^## ", text)
        index = 0
        for position, part in enumerate(sections):
            if position == 0:
                section = title
                content = part.partition("\n")[2] if part.startswith("# ") else part
            else:
                section, _, content = part.partition("\n")
            content = content.strip()
            for start in range(0, len(content), 800):
                segment = content[start:start + 900]
                if segment.strip():
                    index += 1
                    chunks.append(KnowledgeChunk(id=f"{path.stem}:{index:03}", title=title,
                                  section=section.strip(), text=segment, source=f"knowledge/{path.name}"))
                if start + 900 >= len(content):
                    break
    return chunks


class KnowledgeService:
    def __init__(self, engine: RetrievalEngine, chunks: list[KnowledgeChunk] | None = None) -> None:
        self.engine = engine
        self.chunks = load_chunks() if chunks is None else chunks

    async def search(self, query: KnowledgeQuery) -> KnowledgeResult:
        documents = [Document(chunk.id, f"{chunk.title} {chunk.section} {chunk.text}") for chunk in self.chunks]
        ranked, info = await self.engine.rank(query.q, documents)
        by_id = {chunk.id: chunk for chunk in self.chunks}
        selected = ranked[:query.limit]
        info.scores = {item.id: round(item.score, 6) for item in selected}
        return KnowledgeResult(items=[by_id[item.id] for item in selected], retrieval=info)
