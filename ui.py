"""Shared Streamlit UI helpers."""

from __future__ import annotations

from datetime import date

import streamlit as st

from bootstrap import get_api_key, get_repo


def render_sidebar() -> None:
    """Fixed sidebar: today progress + quick links."""
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
        st.page_link("app.py", label="首页", icon="🏠")
        st.page_link("pages/1_教练对话.py", label="教练对话", icon="💬")
        st.page_link("pages/2_今日训练.py", label="今日训练", icon="🏋️")
        st.page_link("pages/3_训练计划.py", label="训练计划", icon="📋")
        st.page_link("pages/4_饮食管理.py", label="饮食管理", icon="🥗")
        st.page_link("pages/5_历史进度.py", label="历史进度", icon="📅")
        st.page_link("pages/6_设置.py", label="设置", icon="⚙️")

        key = get_api_key()
        if not key or key.startswith("sk-xxxxx"):
            st.warning("未配置 API Key")


def page_setup(title: str, icon: str = "💪") -> None:
    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    render_sidebar()
