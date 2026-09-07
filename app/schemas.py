from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """A buyer's natural-language shopping request."""

    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(default="local-session", min_length=1, max_length=100)

    @field_validator("message", "session_id", mode="before")
    @classmethod
    def strip_whitespace(cls, value: object) -> object:
        """Normalize strings before length validation rejects blank input."""
        return value.strip() if isinstance(value, str) else value


class ChatResponse(BaseModel):
    """The stable response contract for the first chat endpoint."""

    session_id: str
    reply: str
