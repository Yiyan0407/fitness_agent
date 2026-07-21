"""Shared Streamlit UI helpers."""

from __future__ import annotations

from datetime import date

import streamlit as st

from bootstrap import get_api_key, get_app_password, get_repo


def require_login() -> None:
    """Block the page until the correct APP_PASSWORD is entered."""
    password = get_app_password()
    if not password:
        return
    if st.session_state.get("authenticated"):
        return

    st.title("健身 Agent")
    st.caption("请输入访问密码")
    with st.form("login_form"):
        entered = st.text_input("密码", type="password")
        submitted = st.form_submit_button("进入", type="primary", use_container_width=True)
    if submitted:
        if entered == password:
            st.session_state.authenticated = True
            st.rerun()
        st.error("密码错误")
    st.stop()


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
                st.session_state.authenticated = False
                st.rerun()


def page_setup(title: str, icon: str = "💪") -> None:
    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    render_sidebar()
