"""Shared Streamlit UI helpers."""

from __future__ import annotations

import hashlib
import hmac
import html
import time
from datetime import datetime, timedelta
from urllib.parse import quote, unquote

import extra_streamlit_components as stx
import streamlit as st

from bootstrap import (
    bind_current_username,
    get_admin_password,
    get_api_key,
    get_current_username,
    get_repo,
    load_env,
    reset_repo_cache,
)
from db.accounts import (
    authenticate,
    create_user,
    init_accounts,
    validate_username,
)

COOKIE_NAME = "fitness_remember"
REMEMBER_DAYS = 30


def _auth_secret() -> bytes:
    import os

    load_env()
    raw = (
        (os.getenv("APP_AUTH_SECRET") or "").strip()
        or (os.getenv("ADMIN_PASSWORD") or "").strip()
        or "fitness-agent-fallback-secret"
    )
    return hashlib.sha256(f"fitness-agent-auth|{raw}".encode("utf-8")).digest()


def make_remember_token(username: str, days: int = REMEMBER_DAYS) -> str:
    exp = int(time.time()) + max(1, int(days)) * 86400
    user = quote(str(username).strip(), safe="")
    payload = f"v2.{user}.{exp}"
    sig = hmac.new(
        _auth_secret(), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_remember_token(token: str | None) -> str | None:
    """Return username if token is valid, else None."""
    if not token:
        return None
    try:
        parts = str(token).strip().split(".")
        if len(parts) != 4 or parts[0] != "v2":
            return None
        user = unquote(parts[1])
        exp = int(parts[2])
        sig = parts[3]
        payload = f"v2.{parts[1]}.{parts[2]}"
        expect = hmac.new(
            _auth_secret(), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(sig, expect):
            return None
        if exp < int(time.time()):
            return None
        if not user:
            return None
        return user
    except Exception:
        return None


def _cookie_manager() -> stx.CookieManager:
    return stx.CookieManager(key="fitness_auth_cookies")


def _read_remember_token(cm: stx.CookieManager) -> str | None:
    """Read remember token from request cookies and CookieManager."""
    try:
        raw = st.context.cookies.get(COOKIE_NAME)
        if raw:
            return str(raw)
    except Exception:
        pass
    try:
        val = cm.get(COOKIE_NAME)
        if val:
            return str(val)
    except Exception:
        pass
    return None


def _flush_cookie_ops(cm: stx.CookieManager) -> None:
    """Apply pending set/delete so the CookieManager iframe can actually run."""
    token = st.session_state.pop("_pending_remember_set", None)
    if token:
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


def _set_logged_in(username: str, *, remember: bool) -> None:
    st.session_state.authenticated = True
    st.session_state.username = username
    bind_current_username(username)
    reset_repo_cache()
    if remember:
        st.session_state["_pending_remember_set"] = make_remember_token(username)
        st.session_state.pop("_pending_remember_clear", None)
    else:
        st.session_state["_pending_remember_clear"] = True
        st.session_state.pop("_pending_remember_set", None)


def logout() -> None:
    st.session_state.authenticated = False
    st.session_state.pop("username", None)
    bind_current_username(None)
    st.session_state["_pending_remember_clear"] = True
    st.session_state.pop("_pending_remember_set", None)
    st.session_state.pop("_auth_cookie_ready", None)
    reset_repo_cache()


def inject_global_styles(*, narrow: bool = False) -> None:
    """Shared layout CSS. Call once per page (via render_sidebar / login)."""
    max_w = "420px" if narrow else "1120px"
    st.markdown(
        f"""
        <style>
        :root, html, [data-theme="dark"], html[data-theme="dark"], .stApp {{
            --fa-bg: #f4f7f5;
            --fa-ink: #1a2421;
            --fa-muted: #5b6b63;
            --fa-accent: #0f766e;
            --fa-card: #ffffff;
            --fa-border: #d5e3d9;
            --fa-metric-bg: linear-gradient(160deg, #f3f7f4 0%, #e8f0ea 100%);
            --fa-sidebar-bg: #fbfcfb;
            --fa-nav-hover: #eef5f1;
            --fa-nav-label: #8a9a92;
            --fa-wash-1: #e7f2ec;
            --fa-wash-2: #eef4f1;
            --fa-header-bg: rgba(255, 255, 255, 0.92);
            color-scheme: light;
        }}
        .stApp {{
            background:
                radial-gradient(1200px 480px at 10% -10%, var(--fa-wash-1) 0%, transparent 55%),
                radial-gradient(900px 420px at 100% 0%, var(--fa-wash-2) 0%, transparent 50%),
                var(--fa-bg) !important;
            color: var(--fa-ink);
        }}
        .block-container {{
            max-width: {max_w} !important;
            padding-top: 3.25rem !important;
            padding-bottom: 3.5rem !important;
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
        }}
        h1 {{
            letter-spacing: -0.02em;
            color: var(--fa-ink) !important;
            margin-bottom: 0.15rem !important;
        }}
        h2, h3 {{
            color: var(--fa-ink) !important;
        }}
        div[data-testid="stCaptionContainer"] {{
            color: var(--fa-muted) !important;
        }}
        div[data-testid="stMetric"] {{
            background: var(--fa-metric-bg);
            border: 1px solid var(--fa-border);
            border-radius: 12px;
            padding: 0.7rem 0.85rem;
        }}
        div[data-testid="stMetric"] label {{
            color: var(--fa-muted) !important;
        }}
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
            color: var(--fa-ink) !important;
        }}
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {{
            color: var(--fa-muted) !important;
        }}
        hr {{
            margin: 1.1rem 0 1.25rem !important;
            border-color: var(--fa-border) !important;
        }}
        [data-testid="stSidebar"] {{
            background: var(--fa-sidebar-bg) !important;
            border-right: 1px solid var(--fa-border);
            color: var(--fa-ink) !important;
        }}
        [data-testid="stSidebar"] .block-container {{
            padding-top: 1.25rem !important;
        }}
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"],
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] span,
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {{
            border-radius: 8px;
            margin: 0.12rem 0;
            padding: 0.35rem 0.55rem !important;
            color: var(--fa-ink) !important;
        }}
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{
            background: var(--fa-nav-hover);
        }}
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .fa-nav-label,
        [data-testid="stSidebar"] .fa-side-status,
        [data-testid="stSidebar"] .fa-side-status .fa-user,
        [data-testid="stSidebar"] .fa-side-status .fa-plan {{
            color: var(--fa-ink) !important;
        }}
        [data-testid="stSidebar"] .fa-side-status .fa-user,
        [data-testid="stSidebar"] .fa-nav-label {{
            color: var(--fa-muted) !important;
        }}
        [data-testid="stSidebar"] button,
        [data-testid="stSidebar"] button p,
        [data-testid="stSidebar"] button span {{
            color: var(--fa-ink) !important;
            border-color: var(--fa-border) !important;
        }}
        [data-testid="stSidebar"] button[kind="secondary"],
        [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
            background-color: var(--fa-card) !important;
            color: var(--fa-ink) !important;
            border: 1px solid var(--fa-border) !important;
        }}
        [data-testid="stSidebar"] button[kind="primary"],
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p,
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] span {{
            background-color: var(--fa-accent) !important;
            color: #ffffff !important;
            border-color: var(--fa-accent) !important;
        }}
        [data-testid="stSidebar"] [data-testid="stProgress"] {{
            color: var(--fa-ink);
        }}
        header[data-testid="stHeader"] {{
            background: var(--fa-header-bg);
        }}
        .fa-page-header {{
            margin: 0 0 1.1rem 0;
        }}
        .fa-page-header h1 {{
            font-size: 1.75rem;
            font-weight: 700;
            margin: 0 0 0.25rem 0;
            color: var(--fa-ink);
        }}
        .fa-page-header p {{
            margin: 0;
            color: var(--fa-muted);
            font-size: 0.95rem;
            line-height: 1.45;
        }}
        .fa-side-status {{
            background: var(--fa-card);
            border: 1px solid var(--fa-border);
            border-radius: 12px;
            padding: 0.75rem 0.85rem;
            margin-bottom: 0.35rem;
        }}
        .fa-side-status .fa-user {{
            font-size: 0.8rem;
            color: var(--fa-muted);
            margin-bottom: 0.2rem;
        }}
        .fa-side-status .fa-plan {{
            font-weight: 600;
            color: var(--fa-ink);
            font-size: 0.98rem;
        }}
        .fa-nav-label {{
            font-size: 0.72rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--fa-nav-label);
            margin: 0.85rem 0 0.25rem 0.15rem;
            font-weight: 600;
        }}
        .fa-week-cell {{
            background: var(--fa-card);
            border: 1px solid var(--fa-border);
            border-radius: 10px;
            padding: 0.55rem 0.4rem;
            text-align: center;
            min-height: 4.2rem;
        }}
        .fa-week-cell.today {{
            border-color: var(--fa-accent);
            box-shadow: inset 0 0 0 1px var(--fa-accent);
        }}
        .fa-week-cell .wd {{
            font-weight: 600;
            color: var(--fa-ink);
            font-size: 0.9rem;
        }}
        .fa-week-cell .st {{
            color: var(--fa-muted);
            font-size: 0.8rem;
            margin-top: 0.2rem;
        }}
        .fa-login-wrap .block-container {{
            max-width: 420px !important;
        }}
        .coach-empty {{
            color: var(--fa-muted);
        }}
        .coach-empty h3 {{
            color: var(--fa-ink);
        }}
        .coach-hint {{
            color: var(--fa-muted);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, caption: str | None = None) -> None:
    """Consistent page title + optional caption."""
    cap = f"<p>{html.escape(caption)}</p>" if caption else ""
    st.markdown(
        f'<div class="fa-page-header"><h1>{html.escape(title)}</h1>{cap}</div>',
        unsafe_allow_html=True,
    )


def require_login() -> None:
    """Block until a user logs in; optionally remember device 30 days."""
    load_env()
    init_accounts()

    cm = _cookie_manager()
    _flush_cookie_ops(cm)

    if st.session_state.get("authenticated") and st.session_state.get("username"):
        bind_current_username(str(st.session_state.username))
        return

    from db.accounts import get_user

    if not st.session_state.get("_auth_cookie_ready"):
        st.session_state["_auth_cookie_ready"] = True
        token = _read_remember_token(cm)
        user = verify_remember_token(token)
        if user and get_user(user):
            st.session_state.authenticated = True
            st.session_state.username = user
            bind_current_username(user)
            return
        inject_global_styles(narrow=True)
        st.caption("正在恢复登录状态…")
        st.stop()

    token = _read_remember_token(cm)
    user = verify_remember_token(token)
    if user and get_user(user):
        st.session_state.authenticated = True
        st.session_state.username = user
        bind_current_username(user)
        return

    inject_global_styles(narrow=True)
    page_header("健身 Agent", "登录已有账户，或展开下方用管理员密码新建账户。")

    with st.form("login_form"):
        username = st.text_input("用户名", placeholder="例如 jyy")
        password = st.text_input("密码", type="password")
        remember = st.checkbox("记住这台设备（30 天）", value=True)
        submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
    if submitted:
        name = (username or "").strip()
        if authenticate(name, password or ""):
            _set_logged_in(name, remember=remember)
            st.rerun()
        st.error("用户名或密码错误")

    with st.expander("新建账户", expanded=False):
        admin = get_admin_password()
        if not admin:
            st.error("未配置 ADMIN_PASSWORD，无法新建账户。请在 .env 中设置。")
        with st.form("create_account_form"):
            new_user = st.text_input("新用户名", key="create_username")
            new_pw = st.text_input("新密码", type="password", key="create_password")
            new_pw2 = st.text_input("确认密码", type="password", key="create_password2")
            admin_pw = st.text_input("管理员密码", type="password", key="create_admin")
            created = st.form_submit_button("创建并登录", use_container_width=True)
        if created:
            if not admin:
                st.error("未配置 ADMIN_PASSWORD")
            elif (admin_pw or "") != admin:
                st.error("管理员密码错误")
            elif (new_pw or "") != (new_pw2 or ""):
                st.error("两次密码不一致")
            else:
                err = validate_username(new_user or "")
                if err:
                    st.error(err)
                else:
                    try:
                        create_user(new_user.strip(), new_pw or "")
                        _set_logged_in(new_user.strip(), remember=True)
                        st.success(f"已创建账户 {new_user.strip()}")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

    st.stop()


def render_sidebar() -> None:
    """Fixed sidebar: today progress + grouped nav."""
    require_login()
    inject_global_styles()
    repo = get_repo()
    with st.sidebar:
        who = get_current_username() or ""
        plan_exists = bool(repo.get_current_plan())
        today = repo.get_today_workout()
        plan = today.get("plan") or {}
        sets = today.get("sets") or []
        done = sum(1 for s in sets if s.get("completed"))
        total = len(sets)

        if not plan_exists:
            plan_line = "还没有训练计划"
        elif plan.get("rest"):
            plan_line = f"休息日 · {today['date']}"
        else:
            name = plan.get("name") or "训练"
            plan_line = f"{name} · {today['date']}"

        st.markdown(
            f"""
            <div class="fa-side-status">
              <div class="fa-user">{html.escape(who)}</div>
              <div class="fa-plan">{html.escape(plan_line)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if not plan_exists:
            st.page_link("pages/1_教练对话.py", label="去生成计划", icon="💬")
            st.page_link("pages/3_训练计划.py", label="或手动编辑计划", icon="📋")
        elif plan.get("rest"):
            pass
        else:
            if total:
                st.progress(done / total, text=f"{done}/{total} 组")
            else:
                st.caption("暂无组安排")
            st.page_link("pages/2_今日训练.py", label="继续打卡", icon="🏋️")

        st.markdown('<div class="fa-nav-label">训练</div>', unsafe_allow_html=True)
        st.page_link("app.py", label="仪表盘", icon="🏠")
        st.page_link("pages/1_教练对话.py", label="教练对话", icon="💬")
        st.page_link("pages/2_今日训练.py", label="今日训练", icon="🏋️")
        st.page_link("pages/3_训练计划.py", label="训练计划", icon="📋")
        st.page_link("pages/8_动作库.py", label="动作库", icon="📖")

        st.markdown('<div class="fa-nav-label">饮食与记录</div>', unsafe_allow_html=True)
        st.page_link("pages/4_饮食管理.py", label="饮食管理", icon="🥗")
        st.page_link("pages/5_历史进度.py", label="历史进度", icon="📅")
        st.page_link("pages/7_每日报告.py", label="每日报告", icon="📝")

        st.markdown('<div class="fa-nav-label">账户</div>', unsafe_allow_html=True)
        st.page_link("pages/6_设置.py", label="设置", icon="⚙️")

        key = get_api_key()
        if not key or key.startswith("sk-xxxxx"):
            st.warning("未配置 API Key")

        if st.session_state.get("authenticated"):
            if st.button("退出登录", use_container_width=True):
                logout()
                st.rerun()


def page_setup(title: str, icon: str = "💪") -> None:
    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    render_sidebar()
