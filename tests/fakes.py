"""Scripted models are test doubles, never a runtime fallback."""

from copy import deepcopy

from app.agent.model import FunctionCall, ModelReply, ToolCall


def tool_reply(name="search_products", arguments='{"q":"耳机","max_price":300}', call_id="call-1"):
    return ModelReply(tool_calls=[ToolCall(id=call_id, function=FunctionCall(name=name, arguments=arguments))])


class ScriptedModel:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    async def complete(self, messages, tools):
        self.requests.append(deepcopy({"messages": messages, "tools": tools}))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
