"""Account registry: multi-user auth and per-user DB paths."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from db.schema import DATA_DIR, DB_PATH, init_db

ACCOUNTS_DB = DATA_DIR / "accounts.db"
USERS_DIR = DATA_DIR / "users"
LEGACY_DB = DB_PATH  # data/fitness.db
DEFAULT_USER = "jyy"
# 仅在从旧版 data/fitness.db 升级时，给承接账户 jyy 设的初始密码
LEGACY_MIGRATE_PASSWORD = "jyy"
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fff]{1,32}$")

_PBKDF2_ITERS = 200_000


def user_db_path(username: str) -> Path:
    safe = _normalize_username(username)
    return USERS_DIR / safe / "fitness.db"


def _normalize_username(username: str) -> str:
    return (username or "").strip()


def validate_username(username: str) -> str | None:
    """Return error message, or None if ok."""
    name = _normalize_username(username)
    if not name:
        return "用户名不能为空"
    if not USERNAME_RE.match(name):
        return "用户名仅支持中英文、数字、下划线，最长 32 位"
    return None


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return stored form: pbkdf2$sha256$iters$salt_hex$hash_hex."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERS,
    )
    return (
        f"pbkdf2$sha256${_PBKDF2_ITERS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = (stored or "").split("$")
        if len(parts) != 5 or parts[0] != "pbkdf2" or parts[1] != "sha256":
            return False
        iters = int(parts[2])
        salt = bytes.fromhex(parts[3])
        expect = bytes.fromhex(parts[4])
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iters,
        )
        return hmac.compare_digest(digest, expect)
    except Exception:
        return False


def _accounts_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ACCOUNTS_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_accounts() -> None:
    """Create accounts DB, migrate legacy fitness.db under user jyy if needed."""
    conn = _accounts_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conn.commit()
        _maybe_migrate_legacy(conn)
    finally:
        conn.close()


def _maybe_migrate_legacy(conn: sqlite3.Connection) -> None:
    """If old single-user data/fitness.db exists, attach it under account jyy.

    Fresh installs (no legacy DB) create no users — use the login page to register.
    """
    target = user_db_path(DEFAULT_USER)
    has_jyy = (
        conn.execute(
            "SELECT id FROM users WHERE username = ?", (DEFAULT_USER,)
        ).fetchone()
        is not None
    )

    # Already migrated earlier: nothing to do unless leftover legacy file
    if has_jyy:
        if LEGACY_DB.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(LEGACY_DB), str(target))
        return

    if not LEGACY_DB.exists():
        return

    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (DEFAULT_USER, hash_password(LEGACY_MIGRATE_PASSWORD)),
    )
    conn.commit()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.move(str(LEGACY_DB), str(target))


def list_usernames() -> list[str]:
    init_accounts()
    conn = _accounts_conn()
    try:
        rows = conn.execute(
            "SELECT username FROM users ORDER BY username COLLATE NOCASE"
        ).fetchall()
        return [str(r["username"]) for r in rows]
    finally:
        conn.close()


def get_user(username: str) -> dict[str, Any] | None:
    init_accounts()
    name = _normalize_username(username)
    if not name:
        return None
    conn = _accounts_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def authenticate(username: str, password: str) -> bool:
    user = get_user(username)
    if not user:
        return False
    return verify_password(password, user["password_hash"])


def create_user(username: str, password: str) -> dict[str, Any]:
    """Create account + empty fitness DB. Raises ValueError on validation errors."""
    init_accounts()
    err = validate_username(username)
    if err:
        raise ValueError(err)
    name = _normalize_username(username)
    if not password or len(password) < 1:
        raise ValueError("密码不能为空")
    if get_user(name):
        raise ValueError("用户名已存在")

    conn = _accounts_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (name, hash_password(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("用户名已存在") from exc
    finally:
        conn.close()

    path = user_db_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    init_db(path)
    return {"username": name, "db_path": str(path)}


def change_password(username: str, new_password: str) -> None:
    if not new_password:
        raise ValueError("密码不能为空")
    name = _normalize_username(username)
    conn = _accounts_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_password(new_password), name),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("用户不存在")
    finally:
        conn.close()

