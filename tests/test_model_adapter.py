import asyncio
import json

import httpx
import pytest

from app.agent.errors import AgentError
from app.agent.model import CompatibleChatModel
from app.settings import Settings


def settings():
    return Settings(llm_base_url="https://model.example/v1", llm_model="test-model", llm_api_key="secret-test-key")


def completion(content="你好", tool_calls=None, finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason, "message": {
        "role": "assistant", "content": content, "tool_calls": tool_calls}}]}


def run(handler):
    model = CompatibleChatModel(settings(), httpx.MockTransport(handler))
    return asyncio.run(model.complete([{"role": "user", "content": "耳机"}], [{"type": "function"}]))


def test_adapter_sends_expected_protocol_and_parses_reply():
    def handler(request):
        assert str(request.url) == "https://model.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret-test-key"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["stream"] is False
        assert body["tool_choice"] == "auto"
        assert body["messages"] == [{"role": "user", "content": "耳机"}]
        return httpx.Response(200, json=completion())
    assert run(handler).content == "你好"


def test_adapter_parses_function_calls_and_preserves_arguments():
    calls = [{"id": "call-1", "type": "function", "function": {
        "name": "search_products", "arguments": '{"q":"耳机"}'}}]
    reply = run(lambda request: httpx.Response(200, json=completion(None, calls, "tool_calls")))
    assert reply.tool_calls[0].function.name == "search_products"
    assert reply.to_message()["tool_calls"] == calls


@pytest.mark.parametrize("status,code,http_status", [(401,"model_auth_failed",503),
    (403,"model_auth_failed",503), (429,"model_rate_limited",503),
    (500,"model_unavailable",502), (302,"model_unavailable",502)])
def test_provider_error_body_is_never_exposed(status, code, http_status):
    with pytest.raises(AgentError) as caught:
        run(lambda request: httpx.Response(status, text="secret-test-key provider private details"))
    assert caught.value.code == code
    assert caught.value.status_code == http_status
    assert "secret-test-key" not in str(caught.value)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": None},
    completion(content=""), completion(content="partial", finish_reason="length"),
    completion(content="blocked", finish_reason="content_filter"),
    completion(content="oops", finish_reason="tool_calls"),
    completion(tool_calls=[{"id":"x", "function":{"name":"search_products", "arguments":{}}}]),
    completion(tool_calls=[{"id":"x", "type":"custom", "function":{"name":"x", "arguments":"{}"}}]),
    completion(content="x" * 16001), {"choices": [{"finish_reason":"stop", "message":42}]}])
def test_malformed_or_incomplete_model_responses_fail_explicitly(payload):
    with pytest.raises(AgentError):
        run(lambda request: httpx.Response(200, json=payload))


def test_non_json_response_and_oversized_body():
    for body in ["<html>error</html>", "x" * 1000001]:
        with pytest.raises(AgentError, match="模型"):
            run(lambda request: httpx.Response(200, text=body))


def test_network_and_read_timeout_errors_are_mapped():
    for error, code in [(httpx.ConnectError("secret-test-key"), "model_unavailable"),
                        (httpx.ReadTimeout("secret-test-key"), "model_timeout")]:
        def handler(request):
            raise error
        with pytest.raises(AgentError) as caught:
            run(handler)
        assert caught.value.code == code
        assert "secret-test-key" not in str(caught.value)


def test_wall_clock_deadline_bounds_slow_provider():
    async def slow(request):
        await asyncio.sleep(2)
        return httpx.Response(200, json=completion())
    config = settings().model_copy(update={"llm_timeout_seconds": 0.01})
    async def scenario():
        model = CompatibleChatModel(config, httpx.MockTransport(slow))
        with pytest.raises(AgentError) as caught:
            await model.complete([], [])
        assert caught.value.code == "model_timeout"
    asyncio.run(scenario())


def test_loopback_provider_can_omit_authorization():
    def handler(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, json=completion())
    config = Settings(llm_base_url="http://localhost:1234/v1", llm_model="local")
    reply = asyncio.run(CompatibleChatModel(config, httpx.MockTransport(handler)).complete([], []))
    assert reply.content == "你好"


def test_invalid_tool_call_container_is_not_treated_as_empty():
    with pytest.raises(AgentError):
        run(lambda request: httpx.Response(200, json=completion(tool_calls={})))


def test_deeply_nested_provider_json_returns_controlled_error():
    with pytest.raises(AgentError):
        run(lambda request: httpx.Response(200, text='[' * 1100 + '0' + ']' * 1100))
