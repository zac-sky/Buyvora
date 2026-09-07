"""Explicit configuration; environment variables override the local .env file."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr, field_validator


class Settings(BaseModel):
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=30, ge=1, le=120, allow_inf_nan=False)
    agent_max_model_calls: int = Field(default=5, ge=1, le=10)
    agent_max_tool_calls: int = Field(default=8, ge=1, le=20)
    session_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    session_capacity: int = Field(default=128, ge=1, le=1000)

    @field_validator("llm_base_url", "llm_model", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("llm_base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        _ = parsed.port  # Validate malformed port numbers before creating an HTTP request.
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query
                or parsed.fragment or parsed.scheme not in {"http", "https"}
                or (parsed.scheme == "http" and not local)):
            raise ValueError("Use HTTPS, or HTTP for a loopback model server")
        return value.rstrip("/")

    @property
    def configured(self) -> bool:
        local = urlsplit(self.llm_base_url).hostname in {"localhost", "127.0.0.1", "::1"}
        return bool(self.llm_base_url and self.llm_model
                    and (self.llm_api_key.get_secret_value().strip() or local))


def load_settings(env_file: str | Path = ".env") -> Settings:
    file_values = dotenv_values(env_file, interpolate=False)
    values = {}
    for name in Settings.model_fields:
        env_name = name.upper()
        value = os.environ.get(env_name, file_values.get(env_name))
        if value is not None:
            values[name] = value
    return Settings.model_validate(values)
