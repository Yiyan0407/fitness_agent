"""历史进度页 — 日历视图。"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

from bootstrap import get_repo, load_env
from db.schema import init_db
from ui import render_sidebar

st.set_page_config(page_title="历史进度", page_icon="📈", layout="wide")
load_env()
init_db()
repo = get_repo()
render_sidebar()

st.title("历史进度")

KIND_STYLE = {
    "done": {"color": "#2E7D32", "label": "已完成"},
    "in_progress": {"color": "#EF6C00", "label": "进行中"},
    "planned": {"color": "#1565C0", "label": "计划"},
    "rest": {"color": "#78909C", "label": "休息"},
}


def _event_title(day: dict) -> str:
    name = day.get("plan_name") or ("休息" if day.get("rest") else "训练")
    kind = day.get("kind")
    total = int(day.get("total_sets") or 0)
    done = int(day.get("completed_sets") or 0)
    if kind == "rest" and total == 0:
        return f"休息 · {name}" if name and name != "休息" else "休息"
    if total:
        return f"{name} {done}/{total}"
    return name or "训练"


def build_events(days: list[dict]) -> list[dict]:
    events = []
    for day in days:
        kind = day["kind"]
        style = KIND_STYLE.get(kind, KIND_STYLE["planned"])
        events.append(
            {
                "id": day["date"],
                "title": _event_title(day),
                "start": day["date"],
                "allDay": True,
                "backgroundColor": style["color"],
                "borderColor": style["color"],
                "textColor": "#FFFFFF",
                "extendedProps": day,
            }
        )
    return events


def parse_selected_date(state) -> str | None:
    if not state or not isinstance(state, dict):
        return None
    callback = state.get("callback")
    if callback == "dateClick":
        raw = (state.get("dateClick") or {}).get("date")
        if raw:
            return str(raw)[:10]
    if callback == "eventClick":
        event = (state.get("eventClick") or {}).get("event") or {}
        raw = event.get("start") or event.get("id")
        if raw:
            return str(raw)[:10]
    return None


with st.expander("体态与图例", expanded=False):
    profile = repo.get_profile()
    m1, m2 = st.columns(2)
    if profile.get("weight_kg"):
        m1.metric("当前体重 (kg)", profile["weight_kg"])
    if profile.get("body_fat_pct"):
        m2.metric("当前体脂 (%)", profile["body_fat_pct"])
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        f"<span style='color:{KIND_STYLE['done']['color']}'>●</span> 已完成",
        unsafe_allow_html=True,
    )
    c2.markdown(
        f"<span style='color:{KIND_STYLE['in_progress']['color']}'>●</span> 进行中",
        unsafe_allow_html=True,
    )
    c3.markdown(
        f"<span style='color:{KIND_STYLE['planned']['color']}'>●</span> 计划",
        unsafe_allow_html=True,
    )
    c4.markdown(
        f"<span style='color:{KIND_STYLE['rest']['color']}'>●</span> 休息",
        unsafe_allow_html=True,
    )

with st.expander("体重 / 体脂趋势", expanded=False):
    metrics = repo.list_body_metrics(days=180)
    if len(metrics) < 2:
        st.caption("在「设置」保存体重或体脂后，这里会留下历史点。至少 2 次记录可看趋势。")
    else:
        chart_df = pd.DataFrame(metrics)
        plot_cols = [c for c in ["weight_kg", "body_fat_pct"] if c in chart_df.columns]
        show = chart_df.set_index("date")[plot_cols].rename(
            columns={"weight_kg": "体重kg", "body_fat_pct": "体脂%"}
        )
        st.line_chart(show)
    with st.form("quick_body_log"):
        b1, b2 = st.columns(2)
        w_in = b1.number_input(
            "今日体重 kg",
            min_value=0.0,
            value=float(repo.get_profile().get("weight_kg") or 0),
            step=0.1,
        )
        f_in = b2.number_input(
            "今日体脂 %",
            min_value=0.0,
            max_value=60.0,
            value=float(repo.get_profile().get("body_fat_pct") or 0),
            step=0.1,
        )
        if st.form_submit_button("记入今日并更新画像"):
            repo.update_profile(
                weight_kg=w_in or None,
                body_fat_pct=f_in or None,
            )
            st.toast("已记录")
            st.rerun()

today = date.today()
cal_start = today.replace(day=1) - timedelta(days=200)
cal_end = today + timedelta(days=90)
days = repo.list_calendar_days(cal_start, cal_end)
events = build_events(days)

cal_state = calendar(
    events=events,
    options={
        "initialView": "dayGridMonth",
        "locale": "zh-cn",
        "height": 420,
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth,listMonth",
        },
        "editable": False,
        "selectable": True,
        "navLinks": True,
    },
    custom_css="""
    .fc-event-title { font-weight: 600; font-size: 0.85rem; }
    .fc-toolbar-title { font-size: 1.35rem; }
    .fc-daygrid-event { border-radius: 4px; }
    """,
    key="workout_calendar",
)

selected = parse_selected_date(cal_state)
if selected:
    st.session_state["history_selected_date"] = selected
selected = st.session_state.get("history_selected_date", today.isoformat())

st.divider()
st.subheader(f"当日详情 · {selected}")

try:
    date.fromisoformat(selected)
except ValueError:
    selected = today.isoformat()

detail = repo.get_day_detail(selected)
plan = detail.get("plan") or {}
workout = detail.get("workout")
sets = detail.get("sets") or []

meta1, meta2, meta3 = st.columns(3)
meta1.write(f"**安排**：{plan.get('name') or ('休息日' if plan.get('rest') else '无计划')}")
meta2.write(f"**状态**：{(workout or {}).get('status') or '-'}")
done_n = sum(1 for s in sets if s.get("completed"))
meta3.write(f"**组数**：{done_n}/{len(sets)}")

if plan.get("rest") and not sets:
    st.info("这一天是休息日。")
elif not sets:
    st.info("这一天还没有训练记录。可去「今日训练」打卡，或让教练生成计划。")
else:
    rows = [
        {
            "动作": s["exercise_name"],
            "组": s["set_index"],
            "重量kg": s["weight_kg"],
            "次数": s["reps"],
            "RPE": s["rpe"],
            "完成": "是" if s.get("completed") else "否",
            "备注": s.get("notes") or "",
        }
        for s in sets
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

if workout and workout.get("notes"):
    st.caption(f"备注：{workout['notes']}")

go1, go2, go3 = st.columns(3)
with go1:
    if st.button("在「今日训练」打开这一天", width="stretch"):
        st.session_state["workout_jump_date"] = selected
        st.switch_page("pages/2_今日训练.py")
with go2:
    st.page_link("pages/2_今日训练.py", label="去今日训练", icon="🏋️")
with go3:
    if st.button("查看 / 生成日报", width="stretch"):
        st.session_state["daily_report_date"] = date.fromisoformat(selected)
        st.switch_page("pages/7_每日报告.py")

day_report = repo.get_daily_report(selected)
if day_report:
    with st.expander(f"已存日报：{day_report.get('title') or selected}", expanded=False):
        st.markdown(day_report.get("content") or "")

with st.expander("动作重量趋势", expanded=False):
    progress = repo.get_exercise_progress(days=90)
    if not progress:
        st.caption("暂无带重量的完成记录。")
    else:
        pdf = pd.DataFrame(progress)
        exercises = sorted(pdf["exercise_name"].unique().tolist())
        pick = st.multiselect(
            "选择动作", exercises, default=exercises[:3], key="hist_ex_pick"
        )
        if pick:
            filtered = pdf[pdf["exercise_name"].isin(pick)].copy()
            pivot = filtered.pivot_table(
                index="date",
                columns="exercise_name",
                values="max_weight",
                aggfunc="max",
            )
            st.line_chart(pivot)
