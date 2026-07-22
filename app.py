"""个人健身 Agent — 今日仪表盘。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from agent.energy import deficit_delta_text, energy_balance
from bootstrap import get_api_key, get_repo, load_env
from ui import page_header, render_sidebar

st.set_page_config(
    page_title="健身仪表盘",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

load_env()
render_sidebar()
repo = get_repo()

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
today_d = date.today()
today_s = today_d.isoformat()
profile = repo.get_profile()
api_key = get_api_key()
plan_exists = bool(repo.get_current_plan())
today = repo.get_today_workout()
plan = today.get("plan") or {}
sets = today.get("sets") or []
done = sum(1 for s in sets if s.get("completed"))
total = len(sets)
nutri = repo.get_nutrition_day(today_s)
nt = nutri["targets"]
tot = nutri["totals"]
meals = nutri["meals"]
workout_row = today.get("workout") or {}
burn = workout_row.get("calories_burned")
balance = energy_balance(
    profile=profile,
    intake_kcal=tot.get("calories"),
    exercise_kcal=burn,
)


def _ratio(current: float, target: float | None) -> float | None:
    if not target:
        return None
    return min(1.0, float(current) / float(target))


def _progress(label: str, current: float, target: float | None) -> None:
    if not target:
        return
    rem = float(target) - float(current)
    rem_txt = f"还差 {rem:.0f}" if rem > 0 else f"超出 {-rem:.0f}"
    st.progress(
        _ratio(current, target) or 0.0,
        text=f"{label} {current:.0f}/{target:.0f}（{rem_txt}）",
    )


goal = profile.get("goal") or "未设目标"
caption = (
    f"{today_s} {WEEKDAY_CN[today_d.weekday()]}"
    f" · {goal}"
    + (f" · {profile['goal_detail']}" if profile.get("goal_detail") else "")
)
page_header("今日仪表盘", caption)

if not api_key or api_key.startswith("sk-xxxxx"):
    st.warning("尚未配置 MIMO_API_KEY，教练对话不可用。")
    st.page_link("pages/6_设置.py", label="去设置 API Key", icon="⚙️")

# KPI row 1: training / intake / deficit
k1, k2, k3 = st.columns(3)
if plan.get("rest"):
    k1.metric("今日训练", "休息")
elif total:
    k1.metric("训练组数", f"{done}/{total}", f"{int(100 * done / total)}%")
else:
    k1.metric("训练组数", "—" if plan_exists else "无计划")

k2.metric(
    "热量摄入",
    f"{tot['calories']:.0f}",
    None if not nt.get("calorie_target") else f"目标 {nt['calorie_target']:.0f}",
)
if balance.get("ok"):
    k3.metric(
        "热量缺口",
        f"{balance['deficit']:.0f}",
        deficit_delta_text(balance),
    )
else:
    k3.metric("热量缺口", "—", "需完善身高体重年龄")

# KPI row 2: macros
m1, m2, m3 = st.columns(3)
m1.metric(
    "蛋白 g",
    f"{tot['protein_g']:.0f}",
    None if not nt.get("protein_target_g") else f"目标 {nt['protein_target_g']:.0f}",
)
m2.metric(
    "碳水 g",
    f"{tot['carb_g']:.0f}",
    None if not nt.get("carb_target_g") else f"目标 {nt['carb_target_g']:.0f}",
)
m3.metric(
    "脂肪 g",
    f"{tot['fat_g']:.0f}",
    None if not nt.get("fat_target_g") else f"目标 {nt['fat_target_g']:.0f}",
)

if balance.get("ok"):
    ex_txt = (
        f"{balance['exercise_used']:.0f}"
        if burn is not None
        else "未估·按0"
    )
    st.caption(
        f"缺口 = 常规 {balance['baseline']:.0f} + 运动 {ex_txt}"
        f" − 摄入 {balance['intake']:.0f}"
        + (" · 可在今日训练估消耗" if burn is None else "")
    )
elif balance.get("missing"):
    st.caption("缺口需先在设置填写：" + "、".join(balance["missing"]))

st.divider()

left, right = st.columns(2, gap="large")

with left:
    st.subheader("训练")
    if not plan_exists:
        st.info("还没有训练计划。")
        st.page_link("pages/1_教练对话.py", label="让教练生成计划", icon="💬")
    elif plan.get("rest"):
        st.success("今天是休息日，好好恢复。")
        st.page_link("pages/7_每日报告.py", label="写每日报告", icon="📝")
    else:
        name = plan.get("name") or "训练"
        st.markdown(f"**{name}**")
        if total:
            st.progress(done / total, text=f"已完成 {done}/{total} 组")
            by_ex: dict[str, list] = {}
            for s in sets:
                by_ex.setdefault(s["exercise_name"], []).append(s)
            rows = []
            for ex, ex_sets in by_ex.items():
                c = sum(1 for x in ex_sets if x.get("completed"))
                rows.append(
                    f"{'✓' if c >= len(ex_sets) else '○'} {ex} {c}/{len(ex_sets)}"
                )
            st.caption("  ·  ".join(rows[:8]))
            if done >= total:
                st.success("今日训练已全部打卡。")
                st.page_link("pages/7_每日报告.py", label="生成今日报告", icon="📝")
            else:
                st.page_link("pages/2_今日训练.py", label="继续打卡", icon="🏋️")
        else:
            st.caption("今日暂无具体动作，可让教练补充。")
            st.page_link("pages/2_今日训练.py", label="打开今日训练", icon="🏋️")

with right:
    st.subheader("饮食")
    kind = nt.get("day_kind")
    kind_label = (
        "休息日目标"
        if kind == "rest"
        else ("训练日目标" if kind == "train" else "饮食目标")
    )
    st.caption(f"已记 {len(meals)} 餐 · {kind_label}")
    _progress("热量", tot["calories"], nt.get("calorie_target"))
    _progress("蛋白", tot["protein_g"], nt.get("protein_target_g"))
    _progress("碳水", tot["carb_g"], nt.get("carb_target_g"))
    _progress("脂肪", tot["fat_g"], nt.get("fat_target_g"))
    if not any(
        nt.get(k)
        for k in ("calorie_target", "protein_target_g", "carb_target_g", "fat_target_g")
    ):
        st.caption("还没设饮食目标，可在饮食管理或让教练估算。")
    elif not meals:
        st.caption("今天还没有饮食记录。")
    else:
        preview = "、".join(
            f"{m.get('meal_type') or ''}{m.get('name') or ''}" for m in meals[:4]
        )
        st.caption(preview + ("…" if len(meals) > 4 else ""))
    st.page_link("pages/4_饮食管理.py", label="饮食明细与目标", icon="🥗")

st.divider()
st.subheader("本周训练")
week = repo.get_completion_last_n_days(7)
cols = st.columns(7)
for i, d in enumerate(week):
    with cols[i]:
        is_today = d["date"] == today_s
        label = d["weekday"].replace("周", "")
        plan_day = repo.get_plan_for_date(date.fromisoformat(d["date"]))
        if plan_day and plan_day.get("rest") and d["total_sets"] == 0:
            status = "休"
        elif d["total_sets"] == 0:
            status = "—"
        elif d["done"]:
            status = "✓ 完成"
        else:
            status = f"{d['completed_sets']}/{d['total_sets']}"
        today_cls = " today" if is_today else ""
        mark = " ·今" if is_today else ""
        st.markdown(
            f'<div class="fa-week-cell{today_cls}">'
            f'<div class="wd">{label}{mark}</div>'
            f'<div class="st">{status}</div></div>',
            unsafe_allow_html=True,
        )

st.divider()
st.subheader("画像")
b1, b2, b3, b4 = st.columns(4)
b1.metric(
    "体重 kg",
    f"{profile['weight_kg']:g}" if profile.get("weight_kg") else "—",
    None
    if not profile.get("target_weight_kg")
    else f"目标 {profile['target_weight_kg']:g}",
)
b2.metric(
    "体脂 %",
    f"{profile['body_fat_pct']:g}" if profile.get("body_fat_pct") else "—",
    None
    if not profile.get("target_body_fat_pct")
    else f"目标 {profile['target_body_fat_pct']:g}",
)
b3.metric("经验", profile.get("experience") or "—")
b4.metric(
    "每周 / 单次",
    f"{profile.get('days_per_week') or '—'}天"
    + (
        f" · {profile['session_minutes']}分"
        if profile.get("session_minutes")
        else ""
    ),
)

st.caption(
    " · ".join(
        [
            f"性别 {profile.get('gender') or '未设'}",
            f"年龄 {profile.get('age') or '未设'}",
            f"器械 {profile.get('equipment') or '未设'}",
            f"活动量 {profile.get('activity_level') or '未设'}",
            f"分化 {profile.get('preferred_split') or '未设'}",
        ]
    )
)
