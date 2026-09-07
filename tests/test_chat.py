import json

import pytest
from fastapi.testclient import TestClient

from app.agent.errors import AgentError
from app.agent.model import ModelReply
from app.main import create_app
from app.settings import Settings
from tests.fakes import ScriptedModel, tool_reply


def client_with(*replies, **options):
    model = ScriptedModel(*replies)
    return TestClient(create_app(Settings(**options), model)), model


def test_chat_runs_model_tool_model_loop() -> None:
    client, model = client_with(tool_reply(), ModelReply(content="演示商品：轻听 Air 159.90 元，静听 Pro 299 元。"))
    response = client.post("/commerce/chat", json={"message": "找300元以内的耳机"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["session_id"]) >= 32
    assert body["catalog_source"] == "demo"
    assert len(body["products"]) == 2
    assert body["tool_calls"][0]["ok"] is True
    tool_message = model.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-1"
    assert json.loads(tool_message["content"])["total"] == 2
    assert {t["function"]["name"] for t in model.requests[0]["tools"]} == {"search_products", "get_product"}


def test_chat_normalizes_and_continues_server_issued_session() -> None:
    client, model = client_with(ModelReply(content="想找什么商品？"), ModelReply(content="预算是多少？"))
    first = client.post("/commerce/chat", json={"message": "  你好  "}).json()
    second = client.post("/commerce/chat", json={"message": "耳机", "session_id": first["session_id"]})
    assert second.status_code == 200
    assert second.json()["session_id"] == first["session_id"]
    assert [m["content"] for m in model.requests[1]["messages"][1:]] == ["你好", "想找什么商品？", "耳机"]


def test_new_sessions_do_not_share_history() -> None:
    client, model = client_with(ModelReply(content="收到"), ModelReply(content="你好"))
    first = client.post("/commerce/chat", json={"message": "我的预算是300"}).json()
    second = client.post("/commerce/chat", json={"message": "我说过什么？"}).json()
    assert first["session_id"] != second["session_id"]
    assert len(model.requests[1]["messages"]) == 2


@pytest.mark.parametrize("message", ["", "  ", "\t\n", "\u3000", "a" * 2001, None, 123])
def test_chat_rejects_invalid_message(message: object) -> None:
    client, model = client_with()
    assert client.post("/commerce/chat", json={"message": message}).status_code == 422
    assert not model.requests


@pytest.mark.parametrize("session_id", ["", "  ", "a" * 101, 123])
def test_chat_rejects_invalid_session(session_id: object) -> None:
    client, model = client_with()
    assert client.post("/commerce/chat", json={"message": "耳机", "session_id": session_id}).status_code == 422
    assert not model.requests


def test_unknown_session_is_not_created_or_read() -> None:
    client, model = client_with()
    assert client.post("/commerce/chat", json={"message": "耳机", "session_id": "someone-else"}).status_code == 404
    assert not model.requests


def test_no_model_config_is_explicit_and_health_still_works() -> None:
    client = TestClient(create_app(Settings()))
    response = client.post("/commerce/chat", json={"message": "耳机"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_not_configured"
    assert client.get("/health").status_code == 200
    assert client.get("/ready").json()["model_configured"] is False
    assert client.get("/commerce/products").status_code == 200


def test_failed_turn_does_not_pollute_existing_history() -> None:
    client, model = client_with(ModelReply(content="你好"), tool_reply(),
                               AgentError("model_timeout", "超时", 504), ModelReply(content="请重试需求"))
    session_id = client.post("/commerce/chat", json={"message": "开始"}).json()["session_id"]
    failed = client.post("/commerce/chat", json={"message": "失败的请求", "session_id": session_id})
    assert failed.status_code == 504
    assert client.post("/commerce/chat", json={"message": "再次请求", "session_id": session_id}).status_code == 200
    assert [m["content"] for m in model.requests[-1]["messages"][1:]] == ["开始", "你好", "再次请求"]


def test_failed_new_session_releases_capacity() -> None:
    client, _ = client_with(AgentError("model_timeout", "超时", 504), ModelReply(content="可以开始"), session_capacity=1)
    assert client.post("/commerce/chat", json={"message": "失败"}).status_code == 504
    assert client.post("/commerce/chat", json={"message": "重试"}).status_code == 200


def test_latest_search_replaces_previous_product_cards() -> None:
    client, _ = client_with(tool_reply(), tool_reply(arguments='{"q":"不存在的商品"}', call_id="call-2"),
                           ModelReply(content="没有符合条件的演示商品。"))
    body = client.post("/commerce/chat", json={"message": "先搜索再缩小条件"}).json()
    assert body["products"] == []
    assert len(body["tool_calls"]) == 2


def test_invalid_arguments_can_be_repaired_by_model() -> None:
    client, model = client_with(tool_reply(arguments='{"max_price": -1}'), tool_reply(call_id="call-2"),
                               ModelReply(content="已找到演示商品。"))
    body = client.post("/commerce/chat", json={"message": "300元以内耳机"}).json()
    assert body["tool_calls"][0]["ok"] is False
    assert body["tool_calls"][1]["ok"] is True
    assert json.loads(model.requests[1]["messages"][-1]["content"])["error"]["code"] == "invalid_arguments"


def test_model_call_budget_stops_infinite_tool_loop() -> None:
    client, model = client_with(tool_reply(), tool_reply(call_id="call-2"), agent_max_model_calls=2)
    response = client.post("/commerce/chat", json={"message": "耳机"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "model_budget_exceeded"
    assert len(model.requests) == 2


def test_tool_budget_and_duplicate_ids_are_rejected() -> None:
    for options, code in [({"agent_max_tool_calls": 1}, "tool_budget_exceeded"), ({}, "model_invalid_response")]:
        client, _ = client_with(tool_reply(), tool_reply(), **options)
        response = client.post("/commerce/chat", json={"message": "耳机"})
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == code


def test_history_trimming_preserves_complete_tool_turns() -> None:
    replies = []
    for index in range(8):
        replies.extend([tool_reply(call_id=f"call-{index}"), ModelReply(content=f"回复{index}")])
    client, model = client_with(*replies)
    session_id = None
    for index in range(8):
        response = client.post("/commerce/chat", json={"message": f"搜索{index}", "session_id": session_id})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
    messages = model.requests[-2]["messages"]
    assert messages[1]["content"] == "搜索1"
    calls = {call["id"] for m in messages for call in m.get("tool_calls", [])}
    results = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
    assert calls == results
