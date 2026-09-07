"""Minimal Chat Completions adapter with a model-independent port."""

import asyncio
import json
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agent.errors import AgentError
from app.settings import Settings

Message = dict[str, Any]


class FunctionCall(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    arguments: str = Field(max_length=8000)


class ToolCall(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    type: Literal["function"] = "function"
    function: FunctionCall


class ModelReply(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str | None = Field(default=None, max_length=16000)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def valid_reply(self) -> "ModelReply":
        ids = [call.id for call in self.tool_calls]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate tool call IDs")
        if not self.tool_calls and not (self.content and self.content.strip()):
            raise ValueError("Empty model reply")
        return self

    def to_message(self) -> Message:
        message: Message = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [call.model_dump() for call in self.tool_calls]
        return message


class ChatModel(Protocol):
    async def complete(self, messages: list[Message], tools: list[dict]) -> ModelReply: ...


class CompatibleChatModel:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    async def complete(self, messages: list[Message], tools: list[dict]) -> ModelReply:
        headers = {"Content-Type": "application/json"}
        key = self.settings.llm_api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            # A wall-clock deadline also bounds slow responses that keep sending small chunks.
            async with asyncio.timeout(self.settings.llm_timeout_seconds):
                async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds,
                                             transport=self.transport, follow_redirects=False) as client:
                    async with client.stream(
                        "POST", self.settings.llm_base_url + "/chat/completions", headers=headers,
                        json={"model": self.settings.llm_model, "messages": messages,
                              "tools": tools, "tool_choice": "auto", "stream": False},
                    ) as response:
                        if response.status_code in {401, 403}:
                            raise AgentError("model_auth_failed", "模型鉴权失败，请检查本地 API Key 和模型权限。", 503)
                        if response.status_code == 429:
                            raise AgentError("model_rate_limited", "模型服务限流，请稍后重试。", 503)
                        if response.status_code != 200:
                            raise AgentError("model_unavailable", "模型服务暂时不可用，请检查服务配置后重试。")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 1_000_000:
                                raise AgentError("model_invalid_response", "模型响应超过大小限制。")
            data = json.loads(body)
            choice = data["choices"][0]
            if choice.get("finish_reason") not in {"stop", "tool_calls"}:
                raise AgentError("model_incomplete_response", "模型未完成本轮回复，请缩小问题范围后重试。")
            message = choice["message"]
            if not isinstance(message, dict):
                raise ValueError("Invalid assistant message")
            # API providers commonly encode no tool calls as null.
            parsed = ModelReply.model_validate({**message, "tool_calls": [] if message.get("tool_calls") is None else message["tool_calls"]})
            if (choice["finish_reason"] == "tool_calls") != bool(parsed.tool_calls):
                raise ValueError("Tool calls and finish reason disagree")
            return parsed
        except (httpx.TimeoutException, TimeoutError):
            raise AgentError("model_timeout", "模型响应超时，请稍后重试。", 504) from None
        except httpx.HTTPError:
            raise AgentError("model_unavailable", "无法连接模型服务，请检查地址和网络。") from None
        except (ValueError, KeyError, IndexError, TypeError, RecursionError, ValidationError):
            raise AgentError("model_invalid_response", "模型返回了无法处理的响应。") from None
