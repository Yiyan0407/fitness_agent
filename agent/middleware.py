"""Agent middleware: force tool_choice=required with no_tool_needed escape hatch."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import tool

NO_TOOL_NEEDED_NAME = "no_tool_needed"

_NO_TOOL_NEEDED_RETURN = (
    "已确认无需继续调用工具，请直接基于对话上下文回答用户问题。"
)


@tool(
    NO_TOOL_NEEDED_NAME,
    description=(
        "当无需继续调用业务工具、可以开始回答用户时调用。"
        "适用场景：① 闲聊/常识/纯建议等不涉及读写本地数据；"
        "② 已完成必要的读库/写库，信息已足够。"
        "涉及记账、打卡、改计划、改目标等写库操作时，完成写库前不得调用此工具。"
    ),
)
def no_tool_needed(reason: str = "") -> str:
    """占位工具：表示当前上下文已足够，无需再调业务工具。"""
    _ = reason
    return _NO_TOOL_NEEDED_RETURN


def tools_with_no_tool_needed(tools: list[Any] | None) -> list[Any]:
    """附加 no_tool_needed（若尚未注册）。"""
    merged = list(tools or [])
    names = {getattr(item, "name", None) for item in merged}
    if NO_TOOL_NEEDED_NAME not in names:
        merged.append(no_tool_needed)
    return merged


def _model_thinking_enabled(model: Any) -> bool:
    """部分模型 thinking 模式不支持 tool_choice=required。"""
    extra_body = dict(getattr(model, "extra_body", None) or {})
    if extra_body.get("enable_thinking"):
        return True
    thinking = extra_body.get("thinking")
    return isinstance(thinking, dict) and thinking.get("type") == "enabled"


def _should_force_required_tool_choice(messages: list[AnyMessage]) -> bool:
    """每轮 model 调用强制 tool_choice=required，除非刚收到 no_tool_needed 结果。"""
    if not messages:
        return True
    last = messages[-1]
    if isinstance(last, ToolMessage) and last.name == NO_TOOL_NEEDED_NAME:
        return False
    return True


def _apply_required_tool_choice(request: ModelRequest) -> ModelRequest:
    """每轮 tool_choice=required；no_tool_needed 返回后允许直接作答。thinking 模式回退默认。"""
    if _model_thinking_enabled(request.model):
        return request
    if _should_force_required_tool_choice(list(request.messages or [])):
        return request.override(tool_choice="required")
    return request


class RequiredToolChoiceMiddleware(AgentMiddleware):
    """sync/async：每轮强制 tool_choice=required，配合 no_tool_needed 收尾。"""

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT] | AIMessage:
        return handler(_apply_required_tool_choice(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | AIMessage:
        return await handler(_apply_required_tool_choice(request))


required_tool_choice_middleware = RequiredToolChoiceMiddleware()
