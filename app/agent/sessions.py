"""Bounded, process-local sessions. IDs act as unguessable bearer capabilities."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from secrets import token_urlsafe
from time import monotonic
from typing import Iterator

from app.agent.errors import AgentError
from app.agent.model import Message


@dataclass
class Session:
    id: str
    updated_at: float
    turns: list[list[Message]] = field(default_factory=list)
    busy: bool = False


class MemorySessions:
    """Used on one asyncio event loop; no await occurs during acquire/release."""

    def __init__(self, ttl_seconds: int = 1800, capacity: int = 128) -> None:
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self._sessions: dict[str, Session] = {}

    @contextmanager
    def acquire(self, session_id: str | None) -> Iterator[Session]:
        now = monotonic()
        for key, value in list(self._sessions.items()):
            if not value.busy and now - value.updated_at >= self.ttl_seconds:
                del self._sessions[key]
        is_new = session_id is None
        if is_new:
            if len(self._sessions) >= self.capacity:
                raise AgentError("session_capacity", "会话数量达到上限，请等待旧会话过期。", 503)
            session = Session(id=token_urlsafe(32), updated_at=now)
            self._sessions[session.id] = session
        else:
            session = self._sessions.get(session_id)
            if session is None:
                raise AgentError("session_not_found", "会话不存在或已过期，请不带 session_id 开始新对话。", 404)
        if session.busy:
            raise AgentError("session_busy", "本会话上一条请求仍在处理中，请稍后再发送。", 409)
        session.busy = True
        try:
            yield session
        finally:
            session.busy = False
            session.updated_at = monotonic()
            if is_new and not session.turns:
                self._sessions.pop(session.id, None)
