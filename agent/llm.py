"""MiMo LLM client via OpenAI-compatible LangChain ChatOpenAI."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from bootstrap import get_api_key, load_env

MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
# 教练 / 文本：推理更强
MIMO_MODEL = "mimo-v2.5-pro"
# 看图：官方图像理解目前支持全模态 mimo-v2.5
MIMO_VISION_MODEL = "mimo-v2.5"


class MissingAPIKeyError(RuntimeError):
    """Raised when MIMO_API_KEY is not configured."""


def get_llm(
    temperature: float = 0.4,
    streaming: bool = False,
    *,
    thinking: bool | None = None,
) -> ChatOpenAI:
    """MiMo text model. Set thinking=False for structured JSON (avoids empty content)."""
    load_env()
    api_key = get_api_key()
    if not api_key or api_key.startswith("sk-xxxxx"):
        raise MissingAPIKeyError(
            "未配置 MIMO_API_KEY。请在项目根目录创建 .env（参考 .env.example），"
            "或在「设置」页填写 API Key。获取地址：https://platform.xiaomimimo.com"
        )
    kwargs: dict = {}
    if thinking is False:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    elif thinking is True:
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    return ChatOpenAI(
        model=os.getenv("MIMO_MODEL", MIMO_MODEL),
        api_key=api_key,
        base_url=os.getenv("MIMO_BASE_URL", MIMO_BASE_URL),
        temperature=temperature,
        streaming=streaming,
        **kwargs,
    )


def get_vision_llm(temperature: float = 0.2) -> ChatOpenAI:
    """MiMo multimodal model for image understanding (meal photos, etc.).

    Deep thinking is disabled: reasoning tokens otherwise consume the budget and
    leave content empty, which breaks JSON meal parsing.
    """
    load_env()
    api_key = get_api_key()
    if not api_key or api_key.startswith("sk-xxxxx"):
        raise MissingAPIKeyError(
            "未配置 MIMO_API_KEY。饮食拍照与教练共用同一 Key，"
            "请到「设置」填写。平台：https://platform.xiaomimimo.com"
        )
    return ChatOpenAI(
        model=os.getenv("MIMO_VISION_MODEL", MIMO_VISION_MODEL),
        api_key=api_key,
        base_url=os.getenv("MIMO_BASE_URL", MIMO_BASE_URL),
        temperature=temperature,
        max_tokens=2048,
        extra_body={"thinking": {"type": "disabled"}},
    )
