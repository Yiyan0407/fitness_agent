"""个人健身 Agent — 首页概览。"""

from __future__ import annotations

import streamlit as st

from bootstrap import get_api_key, get_repo, load_env
from db.schema import init_db
from ui import render_sidebar

st.set_page_config(
    page_title="健身 Agent",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_env()
init_db()
repo = get_repo()
render_sidebar()

st.title("个人健身 Agent")
st.caption("你的私人训练助手")

api_key = get_api_key()
if not api_key or api_key.startswith("sk-xxxxx"):
    st.warning("尚未配置 MIMO_API_KEY，请到「设置」填写后再开始对话。")
    st.page_link("pages/6_设置.py", label="去设置 API Key", icon="⚙️")

profile = repo.get_profile()
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("目标", profile.get("goal") or "-")
col2.metric("性别", profile.get("gender") or "-")
col3.metric("经验", profile.get("experience") or "-")
col4.metric("每周天数", profile.get("days_per_week") or "-")
col5.metric("器械", profile.get("equipment") or "-")
if profile.get("goal_detail") or profile.get("target_weight_kg"):
    parts = []
    if profile.get("goal_detail"):
        parts.append(profile["goal_detail"])
    if profile.get("target_weight_kg"):
        parts.append(f"目标体重 {profile['target_weight_kg']:g} kg")
    st.caption("具体目标：" + " · ".join(parts))

st.divider()
st.subheader("下一步")

plan_exists = bool(repo.get_current_plan())
today = repo.get_today_workout()
plan = today.get("plan")
sets = today.get("sets") or []
done = sum(1 for s in sets if s.get("completed"))
total = len(sets)

if not api_key or api_key.startswith("sk-xxxxx"):
    st.info("先配置 API Key，才能和教练对话生成计划。")
elif not plan_exists:
    st.info("还没有训练计划。")
    c1, c2 = st.columns(2)
    with c1:
        st.page_link("pages/1_教练对话.py", label="让教练生成一周计划", icon="💬")
    with c2:
        st.page_link("pages/3_训练计划.py", label="手动编辑训练计划", icon="📋")
elif plan and plan.get("rest"):
    st.success(f"今天是休息日（{today['date']}），好好恢复。")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.page_link("pages/1_教练对话.py", label="问问教练恢复建议", icon="💬")
    with c2:
        st.page_link("pages/5_历史进度.py", label="看历史日历", icon="📅")
    with c3:
        st.page_link("pages/3_训练计划.py", label="改训练计划", icon="📋")
elif total and done >= total:
    st.success(f"今日「{(plan or {}).get('name') or '训练'}」已全部打卡完成。")
    st.page_link("pages/5_历史进度.py", label="在日历里回顾", icon="📅")
else:
    name = (plan or {}).get("name") or "训练"
    st.write(f"**今天：{name}** · {today['date']}")
    if total:
        st.progress(done / total, text=f"已完成 {done}/{total} 组")
        by_ex: dict[str, list] = {}
        for s in sets:
            by_ex.setdefault(s["exercise_name"], []).append(s)
        pending = [
            ex for ex, ex_sets in by_ex.items() if not all(x.get("completed") for x in ex_sets)
        ]
        if pending:
            st.caption("待完成：" + "、".join(pending[:5]))
    else:
        st.caption("今日暂无具体动作，可让教练补充安排。")
    st.page_link("pages/2_今日训练.py", label="开始 / 继续今日训练", icon="🏋️")

# 饮食快捷
st.divider()
nutri = repo.get_nutrition_day()
nt = nutri["targets"]
tot = nutri["totals"]
st.subheader("今日饮食")
if nt.get("calorie_target") or nt.get("protein_target_g") or nutri["meals"]:
    nc1, nc2, nc3 = st.columns(3)
    nc1.metric(
        "热量",
        f"{tot['calories']:.0f}"
        + (f"/{nt['calorie_target']:.0f}" if nt.get("calorie_target") else ""),
    )
    nc2.metric(
        "蛋白",
        f"{tot['protein_g']:.0f}"
        + (f"/{nt['protein_target_g']:.0f}" if nt.get("protein_target_g") else ""),
    )
    nc3.metric("餐次", len(nutri["meals"]))
else:
    st.caption("还没有饮食记录或目标。去教练对话说一声就能记。")
d1, d2 = st.columns(2)
with d1:
    st.page_link("pages/1_教练对话.py", label="去教练对话记账", icon="💬")
with d2:
    st.page_link("pages/4_饮食管理.py", label="查看饮食明细", icon="🥗")

st.divider()
st.subheader("近 7 天")

days = repo.get_completion_last_n_days(7)
cols = st.columns(7)
for i, d in enumerate(days):
    with cols[i]:
        label = d["weekday"]
        st.markdown(f"**{label}**")
        if d["total_sets"] == 0:
            st.caption("—")
        elif d["done"]:
            st.caption("完成")
        else:
            st.caption(f"{d['completed_sets']}/{d['total_sets']}")
