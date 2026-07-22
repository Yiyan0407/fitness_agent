"""Shared app helpers: env loading and repository singleton."""

from __future__ import annotations

import os
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from db.accounts import init_accounts, user_db_path
from db.repository import REPO_IMPL_VERSION, Repository
from db.schema import init_db

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"

# LangChain ToolNode runs tools in ContextThreadPoolExecutor workers where
# Streamlit session_state is unavailable. Bind username here so get_repo() works.
_bound_username: ContextVar[str | None] = ContextVar("fitness_username", default=None)


def load_env() -> None:
    load_dotenv(ENV_PATH, override=False)


def get_api_key() -> str:
    load_env()
    return (os.getenv("MIMO_API_KEY") or "").strip()


def get_admin_password() -> str:
    """Admin password required to create new accounts."""
    load_env()
    return (os.getenv("ADMIN_PASSWORD") or "").strip()


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


def bind_current_username(username: str | None) -> None:
    """Bind username for the current request (incl. LangChain tool threads)."""
    _bound_username.set((username or "").strip() or None)


def get_current_username() -> str | None:
    """Logged-in username from request binding or Streamlit session."""
    bound = _bound_username.get()
    if bound:
        return bound
    try:
        import streamlit as st

        name = st.session_state.get("username")
        if name and st.session_state.get("authenticated"):
            username = str(name)
            bind_current_username(username)
            return username
    except Exception:
        pass
    return None


@lru_cache(maxsize=8)
def _repo_for_user(username: str, impl_version: int) -> Repository:
    path = user_db_path(username)
    init_db(path)
    return Repository(path)


def get_repo() -> Repository:
    """Return Repository bound to the current logged-in user."""
    load_env()
    init_accounts()
    username = get_current_username()
    if not username:
        raise RuntimeError("未登录，无法访问用户数据")
    bind_current_username(username)
    repo = _repo_for_user(username, REPO_IMPL_VERSION)
    # Streamlit hot-reload can leave older Repository instances in lru_cache.
    if getattr(repo, "_impl_version", 0) != REPO_IMPL_VERSION:
        reset_repo_cache()
        repo = _repo_for_user(username, REPO_IMPL_VERSION)
    return repo


def reset_repo_cache() -> None:
    _repo_for_user.cache_clear()


# Drop any cached repos from a previous code version after reload.
reset_repo_cache()
