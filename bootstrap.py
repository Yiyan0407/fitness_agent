"""Shared app helpers: env loading and repository singleton."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from db.repository import Repository
from db.schema import init_db

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def load_env() -> None:
    load_dotenv(ENV_PATH, override=False)


def get_api_key() -> str:
    load_env()
    return (os.getenv("MIMO_API_KEY") or "").strip()


def save_api_key_to_env(api_key: str) -> None:
    """Persist MIMO_API_KEY into .env (create or replace the line)."""
    upsert_env_var("MIMO_API_KEY", api_key)


def upsert_env_var(key: str, value: str) -> None:
    """Create or replace a KEY=value line in .env."""
    value = value.strip()
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


@lru_cache(maxsize=1)
def get_repo() -> Repository:
    init_db()
    return Repository()


def reset_repo_cache() -> None:
    get_repo.cache_clear()
