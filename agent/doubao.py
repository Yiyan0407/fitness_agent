"""Doubao (Volcengine Ark) vision LLM client."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from bootstrap import load_env

DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
# 默认可改为你在方舟控制台创建的推理接入点 ID（ep-xxxx）
DOUBAO_MODEL = "doubao-seed-2-0-lite-260428"


class MissingDoubaoKeyError(RuntimeError):
    """Raised when Doubao / Ark API key is missing."""


def get_doubao_api_key() -> str:
    load_env()
    return (
        os.getenv("DOUBAO_API_KEY")
        or os.getenv("ARK_API_KEY")
        or os.getenv("VOLC_API_KEY")
        or ""
    ).strip()


def get_doubao_vision_llm(temperature: float = 0.2) -> ChatOpenAI:
    load_env()
    api_key = get_doubao_api_key()
    if not api_key or api_key.startswith("sk-xxxxx"):
        raise MissingDoubaoKeyError(
            "未配置豆包 API Key。请在 .env 填写 DOUBAO_API_KEY（火山方舟 Ark Key），"
            "并可设置 DOUBAO_MODEL 为视觉模型名或接入点 ID（ep-xxxx）。"
            "控制台：https://console.volcengine.com/ark"
        )
    return ChatOpenAI(
        model=os.getenv("DOUBAO_MODEL", DOUBAO_MODEL),
        api_key=api_key,
        base_url=os.getenv("DOUBAO_BASE_URL", DOUBAO_BASE_URL),
        temperature=temperature,
        max_tokens=2048,
    )
