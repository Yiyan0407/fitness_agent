"""Shared Streamlit UI helpers."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta

import extra_streamlit_components as stx
import streamlit as st

from bootstrap import get_api_key, get_app_password, get_repo

COOKIE_NAME = "fitness_remember"
REMEMBER_DAYS = 30


def _auth_secret(password: str) -> bytes:
    import os

    from bootstrap import load_env

    load_env()
    raw = (os.getenv("APP_AUTH_SECRET") or "").strip() or password
    return hashlib.sha256(f"fitness-agent-auth|{raw}".encode("utf-8")).digest()


def make_remember_token(password: str, days: int = REMEMBER_DAYS) -> str:
    exp = int(time.time()) + max(1, int(days)) * 86400
    payload = f"v1.{exp}"
    sig = hmac.new(
        _auth_secret(password), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_remember_token(token: str | None, password: str) -> bool:
    if not token or not password:
        return False
    try:
        parts = str(token).strip().split(".")
        if len(parts) != 3:
            return False
        payload = f"{parts[0]}.{parts[1]}"
        sig = parts[2]
        expect = hmac.new(
            _auth_secret(password), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(sig, expect):
            return False
        return int(parts[1]) >= int(time.time())
    except Exception:
        return False


def _cookie_manager() -> stx.CookieManager:
    return stx.CookieManager(key="fitness_auth_cookies")


def _read_remember_token(cm: stx.CookieManager) -> str | None:
    """Read remember token from request cookies and CookieManager."""
    # Full page reload: available immediately via HTTP Cookie header
    try:
        raw = st.context.cookies.get(COOKIE_NAME)
        if raw:
            return str(raw)
    except Exception:
        pass
    # Same session / component path
    try:
        val = cm.get(COOKIE_NAME)
        if val:
            return str(val)
    except Exception:
        pass
    return None


def _flush_cookie_ops(cm: stx.CookieManager) -> None:
    """Apply pending set/delete so the CookieManager iframe can actually run.

    Important: never call cm.set()/delete() and st.rerun() in the same run —
    the set iframe would be cancelled before writing the browser cookie.
    """
    token = st.session_state.pop("_pending_remember_set", None)
    if token:
        # naive datetime: js-cookie Date parsing is more reliable
        cm.set(
            COOKIE_NAME,
            token,
            key="fitness_remember_set",
            path="/",
            expires_at=datetime.now() + timedelta(days=REMEMBER_DAYS),
            max_age=float(REMEMBER_DAYS * 86400),
            same_site="lax",
        )

    if st.session_state.pop("_pending_remember_clear", None):
        cm.delete(COOKIE_NAME, key="fitness_remember_del")


def require_login() -> None:
    """Block until APP_PASSWORD is entered; optionally remember device 30 days."""
    password = get_app_password()
    if not password:
        return

    cm = _cookie_manager()
    _flush_cookie_ops(cm)

    if st.session_state.get("authenticated"):
        return

    # Give CookieManager one frame to hydrate from the browser after cold start
    if not st.session_state.get("_auth_cookie_ready"):
        st.session_state["_auth_cookie_ready"] = True
        token = _read_remember_token(cm)
        if verify_remember_token(token, password):
            st.session_state.authenticated = True
            return
        # No token yet on this first frame — wait for component getAll callback
        st.caption("正在恢复登录状态…")
        st.stop()

    token = _read_remember_token(cm)
    if verify_remember_token(token, password):
        st.session_state.authenticated = True
        return

    st.title("健身 Agent")
    st.caption("请输入访问密码。勾选「记住设备」后，关闭再打开也不用重输。")
    with st.form("login_form"):
        entered = st.text_input("密码", type="password")
        remember = st.checkbox("记住这台设备（30 天）", value=True)
        submitted = st.form_submit_button("进入", type="primary", use_container_width=True)
    if submitted:
        if entered == password:
            st.session_state.authenticated = True
            if remember:
                # Defer cookie write to next run so the component can render
                st.session_state["_pending_remember_set"] = make_remember_token(password)
                st.session_state.pop("_pending_remember_clear", None)
            else:
                st.session_state["_pending_remember_clear"] = True
                st.session_state.pop("_pending_remember_set", None)
            st.rerun()
        st.error("密码错误")
    st.stop()


def logout() -> None:
    st.session_state.authenticated = False
    st.session_state["_pending_remember_clear"] = True
    st.session_state.pop("_pending_remember_set", None)
    # Force cookie hydration path again after logout
    st.session_state.pop("_auth_cookie_ready", None)


def render_sidebar() -> None:
    """Fixed sidebar: today progress + quick links."""
    require_login()
    repo = get_repo()
    with st.sidebar:
        st.markdown("### 今日")
        plan_exists = bool(repo.get_current_plan())
        today = repo.get_today_workout()
        plan = today.get("plan") or {}
        sets = today.get("sets") or []
        done = sum(1 for s in sets if s.get("completed"))
        total = len(sets)

        if not plan_exists:
            st.caption("还没有训练计划")
            st.page_link("pages/1_教练对话.py", label="去生成计划", icon="💬")
            st.page_link("pages/3_训练计划.py", label="或手动编辑计划", icon="📋")
        elif plan.get("rest"):
            st.caption(f"休息日 · {today['date']}")
        else:
            name = plan.get("name") or "训练"
            st.caption(f"{name} · {today['date']}")
            if total:
                st.progress(done / total, text=f"{done}/{total} 组")
            else:
                st.caption("暂无组安排")
            st.page_link("pages/2_今日训练.py", label="继续打卡", icon="🏋️")

        st.divider()
        st.page_link("app.py", label="仪表盘", icon="🏠")
        st.page_link("pages/1_教练对话.py", label="教练对话", icon="💬")
        st.page_link("pages/2_今日训练.py", label="今日训练", icon="🏋️")
        st.page_link("pages/3_训练计划.py", label="训练计划", icon="📋")
        st.page_link("pages/4_饮食管理.py", label="饮食管理", icon="🥗")
        st.page_link("pages/5_历史进度.py", label="历史进度", icon="📅")
        st.page_link("pages/7_每日报告.py", label="每日报告", icon="📝")
        st.page_link("pages/6_设置.py", label="设置", icon="⚙️")

        key = get_api_key()
        if not key or key.startswith("sk-xxxxx"):
            st.warning("未配置 API Key")

        if get_app_password() and st.session_state.get("authenticated"):
            st.divider()
            if st.button("退出登录", use_container_width=True):
                logout()
                st.rerun()


def page_setup(title: str, icon: str = "💪") -> None:
    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    render_sidebar()
