"""MiMo LLM client via OpenAI-compatible LangChain ChatOpenAI."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from bootstrap import get_api_key, load_env

MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5-pro"


class MissingAPIKeyError(RuntimeError):
    """Raised when MIMO_API_KEY is not configured."""


def get_llm(temperature: float = 0.4, streaming: bool = False) -> ChatOpenAI:
    load_env()
    api_key = get_api_key()
    if not api_key or api_key.startswith("sk-xxxxx"):
        raise MissingAPIKeyError(
            "未配置 MIMO_API_KEY。请在项目根目录创建 .env（参考 .env.example），"
            "或在「设置」页填写 API Key。获取地址：https://platform.xiaomimimo.com"
        )
    return ChatOpenAI(
        model=os.getenv("MIMO_MODEL", MIMO_MODEL),
        api_key=api_key,
        base_url=os.getenv("MIMO_BASE_URL", MIMO_BASE_URL),
        temperature=temperature,
        streaming=streaming,
    )
