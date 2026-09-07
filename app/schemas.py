from pydantic import BaseModel, Field, field_validator

from app.agent.tools import ToolTrace
from app.domain.catalog import Product


class ChatRequest(BaseModel):
    """Omit session_id to create a new session; reuse the returned ID to continue."""

    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("message", "session_id", mode="before")
    @classmethod
    def strip_whitespace(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    products: list[Product] = Field(default_factory=list)
    tool_calls: list[ToolTrace] = Field(default_factory=list)
    catalog_source: str = "demo"
