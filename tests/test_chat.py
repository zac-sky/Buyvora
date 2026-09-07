import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_returns_session_and_reply() -> None:
    response = client.post(
        "/commerce/chat",
        json={"session_id": "demo-session", "message": "我想买一副降噪耳机"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "session_id": "demo-session",
        "reply": "我收到了你的购物需求：我想买一副降噪耳机。下一步我会帮你分析商品类型和筛选条件。",
    }


@pytest.mark.parametrize("message", ["", "  ", "\t\n", "\u3000", "a" * 2001, None, 123])
def test_chat_rejects_invalid_message(message: object) -> None:
    response = client.post("/commerce/chat", json={"message": message})
    assert response.status_code == 422


def test_chat_normalizes_whitespace() -> None:
    response = client.post(
        "/commerce/chat", json={"message": "  耳机  ", "session_id": " demo "}
    )
    assert response.status_code == 200
    assert response.json()["session_id"] == "demo"
    assert "需求：耳机。" in response.json()["reply"]


@pytest.mark.parametrize("session_id", ["", "  ", "a" * 101, None])
def test_chat_rejects_invalid_session(session_id: object) -> None:
    response = client.post(
        "/commerce/chat", json={"message": "耳机", "session_id": session_id}
    )
    assert response.status_code == 422
