import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.errors import AgentError
from app.agent.model import ModelReply
from app.agent.sessions import MemorySessions
from app.main import create_app
from app.schemas import ChatRequest
from app.services.chat_service import build_shopping_agent
from app.settings import Settings, load_settings
from tests.fakes import ScriptedModel


@pytest.mark.parametrize("url", ["http://remote.example/v1", "https://user:pass@model.example/v1",
    "https://model.example/v1?key=secret", "https://model.example/#fragment", "ftp://model.example", "invalid"])
def test_invalid_model_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        Settings(llm_base_url=url)


def test_config_requires_explicit_model_url_and_cloud_key():
    assert not Settings().configured
    assert not Settings(llm_base_url="https://model.example/v1", llm_model="test").configured
    assert Settings(llm_base_url="http://127.0.0.1:1234/v1", llm_model="local").configured
    config = Settings(llm_base_url="https://model.example/v1/", llm_model="test", llm_api_key="private-key")
    assert config.configured
    assert config.llm_base_url.endswith("/v1")
    assert "private-key" not in repr(config)


def test_environment_overrides_env_file_without_mutating_environment(tmp_path, monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_BASE_URL=https://model.example/v1\nLLM_MODEL=file-model\nLLM_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    config = load_settings(env_file)
    assert config.llm_model == "env-model"
    assert config.llm_api_key.get_secret_value() == "file-key"
    import os
    assert "LLM_API_KEY" not in os.environ


def test_bad_environment_config_does_not_expose_secret_or_break_catalog(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://user:private-key@model.example/v1")
    client = TestClient(create_app())
    response = client.post("/commerce/chat", json={"message":"你好"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_config_invalid"
    assert "private-key" not in response.text
    assert client.get("/commerce/products").status_code == 200


def test_expired_sessions_are_removed_but_busy_sessions_are_preserved(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("app.agent.sessions.monotonic", lambda: now[0])
    sessions = MemorySessions(ttl_seconds=60, capacity=1)
    with sessions.acquire(None) as session:
        session.turns.append([{"role":"user", "content":"hello"}])
        session_id = session.id
        now[0] = 100
        with pytest.raises(AgentError) as caught:
            with sessions.acquire(None):
                pass
        assert caught.value.code == "session_capacity"
    now[0] = 161
    with pytest.raises(AgentError) as caught:
        with sessions.acquire(session_id):
            pass
    assert caught.value.code == "session_not_found"
    with sessions.acquire(None) as new:
        assert new.id != session_id


def test_concurrent_requests_for_same_session_get_conflict():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class SlowModel:
            async def complete(self, messages, tools):
                if len(messages) > 2:
                    entered.set()
                    await release.wait()
                return ModelReply(content="你好")
        agent = build_shopping_agent(Settings(), SlowModel())
        first = await agent.reply(ChatRequest(message="开始"))
        pending = asyncio.create_task(agent.reply(ChatRequest(message="慢请求", session_id=first.session_id)))
        await entered.wait()
        try:
            with pytest.raises(AgentError) as caught:
                await agent.reply(ChatRequest(message="重复请求", session_id=first.session_id))
            assert caught.value.status_code == 409
        finally:
            release.set()
            await pending
    asyncio.run(scenario())


def test_cancelled_request_releases_session_for_retry():
    async def scenario():
        entered = asyncio.Event()
        class Model:
            calls = 0
            async def complete(self, messages, tools):
                self.calls += 1
                if self.calls == 2:
                    entered.set()
                    await asyncio.Event().wait()
                return ModelReply(content="完成")
        agent = build_shopping_agent(Settings(), Model())
        first = await agent.reply(ChatRequest(message="开始"))
        pending = asyncio.create_task(agent.reply(ChatRequest(message="取消", session_id=first.session_id)))
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        result = await agent.reply(ChatRequest(message="重试", session_id=first.session_id))
        assert result.reply == "完成"
    asyncio.run(scenario())
