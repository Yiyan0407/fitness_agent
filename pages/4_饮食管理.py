"""饮食管理页 — 进度与明细；记账请去教练对话。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from bootstrap import get_repo, load_env
from agent.energy import deficit_delta_text, energy_balance
from ui import render_sidebar

st.set_page_config(page_title="饮食管理", page_icon="🥗", layout="wide")
load_env()
render_sidebar()
repo = get_repo()

st.title("饮食管理")

if st.session_state.pop("nutrition_saved_flash", False):
    st.toast("目标已保存")
if st.session_state.pop("meal_logged_flash", False):
    st.toast("已记录")

st.page_link("pages/1_教练对话.py", label="去教练对话记账", icon="💬")

target = st.date_input("日期", value=date.today())
day = repo.get_nutrition_day(target.isoformat())
totals = day["totals"]
targets = day["targets"]
meals = day["meals"]
profile = repo.get_profile()
detail = repo.get_day_detail(target.isoformat())
workout = detail.get("workout") or {}
burn = workout.get("calories_burned")
balance = energy_balance(
    profile=profile,
    intake_kcal=totals.get("calories"),
    exercise_kcal=burn,
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "热量摄入",
    f"{totals['calories']:.0f}",
    None
    if not targets.get("calorie_target")
    else f"目标 {targets['calorie_target']:.0f}",
)
if balance.get("ok"):
    c2.metric("热量缺口", f"{balance['deficit']:.0f}", deficit_delta_text(balance))
else:
    c2.metric("热量缺口", "—")
c3.metric(
    "蛋白质 g",
    f"{totals['protein_g']:.0f}",
    None
    if not targets.get("protein_target_g")
    else f"目标 {targets['protein_target_g']:.0f}",
)
c4.metric(
    "碳水 g",
    f"{totals['carb_g']:.0f}",
    None
    if not targets.get("carb_target_g")
    else f"目标 {targets['carb_target_g']:.0f}",
)
c5.metric(
    "脂肪 g",
    f"{totals['fat_g']:.0f}",
    None
    if not targets.get("fat_target_g")
    else f"目标 {targets['fat_target_g']:.0f}",
)

if balance.get("ok"):
    b1, b2, b3 = st.columns(3)
    b1.metric("常规消耗", f"{balance['baseline']:.0f}")
    b2.metric(
        "运动消耗",
        f"{balance['exercise_used']:.0f}" if burn is not None else "未估",
        None if burn is not None else "暂按 0",
    )
    b3.metric("总消耗", f"{balance['total_out']:.0f}")
    st.caption(
        f"缺口 = 常规 {balance['baseline']:.0f}（{balance['activity_level']}）"
        f" + 运动 {balance['exercise_used']:.0f}"
        f" − 摄入 {balance['intake']:.0f} kcal"
        " · 正数=缺口，负数=盈余"
    )
elif balance.get("missing"):
    st.info(
        "要算热量缺口，请先在「设置」填写："
        + "、".join(balance["missing"])
        + "，并确认日常活动量。"
    )


def _progress(label: str, current: float, target_val: float | None) -> None:
    if not target_val:
        return
    ratio = min(1.0, float(current) / float(target_val))
    rem = float(target_val) - float(current)
    rem_txt = f"还差 {rem:.0f}" if rem > 0 else f"超出 {-rem:.0f}"
    st.progress(ratio, text=f"{label} {current:.0f}/{target_val:.0f}（{rem_txt}）")


_progress("热量", totals["calories"], targets.get("calorie_target"))
_progress("蛋白", totals["protein_g"], targets.get("protein_target_g"))
_progress("碳水", totals["carb_g"], targets.get("carb_target_g"))
_progress("脂肪", totals["fat_g"], targets.get("fat_target_g"))

if not any(
    targets.get(k)
    for k in ("calorie_target", "protein_target_g", "carb_target_g", "fat_target_g")
):
    st.info("还没设饮食目标。可在教练对话里让教练估算，或在下方填写热量/蛋白/碳水/脂肪。")
elif not targets.get("carb_target_g") or not targets.get("fat_target_g"):
    missing = []
    if not targets.get("carb_target_g"):
        missing.append("碳水")
    if not targets.get("fat_target_g"):
        missing.append("脂肪")
    st.caption(f"尚未设置{' / '.join(missing)}目标，可在下方「饮食目标」补上。")

st.divider()
st.subheader("当日记录")
if not meals:
    st.caption("这一天还没有饮食记录。去教练对话说「喝了一瓶可乐」或拍照即可。")
else:
    df = pd.DataFrame(
        [
            {
                "id": m["id"],
                "餐次": m["meal_type"],
                "食物": m["name"],
                "热量": m["calories"],
                "蛋白": m["protein_g"],
                "碳水": m["carb_g"],
                "脂肪": m["fat_g"],
                "备注": m["notes"],
            }
            for m in meals
        ]
    )
    st.dataframe(df.drop(columns=["id"]), width="stretch", hide_index=True)
    del_id = st.selectbox(
        "删除记录",
        options=[0] + [int(m["id"]) for m in meals],
        format_func=lambda x: "不删除"
        if x == 0
        else next(
            f"#{m['id']} {m['meal_type']}·{m['name']}"
            for m in meals
            if m["id"] == x
        ),
    )
    if del_id and st.button("确认删除"):
        repo.delete_meal(int(del_id))
        st.rerun()

st.divider()
st.subheader("饮食目标")
profile = repo.get_profile()
with st.form("nutrition_targets"):
    t1, t2 = st.columns(2)
    cal = t1.number_input(
        "每日热量目标 kcal",
        min_value=0.0,
        value=float(profile["calorie_target"] or 0),
        step=50.0,
    )
    pro = t2.number_input(
        "每日蛋白目标 g",
        min_value=0.0,
        value=float(profile["protein_target_g"] or 0),
        step=5.0,
    )
    t3, t4 = st.columns(2)
    carb_t = t3.number_input(
        "每日碳水目标 g",
        min_value=0.0,
        value=float(profile["carb_target_g"] or 0),
        step=5.0,
    )
    fat_t = t4.number_input(
        "每日脂肪目标 g",
        min_value=0.0,
        value=float(profile["fat_target_g"] or 0),
        step=5.0,
    )
    if st.form_submit_button("保存饮食目标"):
        repo.update_profile(
            calorie_target=cal if cal else None,
            protein_target_g=pro if pro else None,
            carb_target_g=carb_t if carb_t else None,
            fat_target_g=fat_t if fat_t else None,
        )
        st.session_state["nutrition_saved_flash"] = True
        st.rerun()

st.divider()
st.subheader("近 7 天")
recent = repo.get_recent_nutrition(7)
if not recent["daily"]:
    st.caption("暂无记录")
else:
    st.dataframe(pd.DataFrame(recent["daily"]), width="stretch", hide_index=True)

st.divider()
st.subheader("手动记账")
with st.form("log_meal_form"):
    m1, m2 = st.columns([2, 1])
    with m1:
        meal_name = st.text_input("食物 / 菜名")
    with m2:
        meal_type = st.selectbox(
            "餐次",
            ["早餐", "午餐", "晚餐", "加餐", "蛋白粉", "其他"],
        )
    n1, n2, n3, n4 = st.columns(4)
    calories = n1.number_input("热量 kcal", min_value=0.0, value=0.0, step=10.0)
    protein = n2.number_input("蛋白 g", min_value=0.0, value=0.0, step=1.0)
    carb = n3.number_input("碳水 g", min_value=0.0, value=0.0, step=1.0)
    fat = n4.number_input("脂肪 g", min_value=0.0, value=0.0, step=1.0)
    meal_notes = st.text_input("备注", placeholder="可选")
    submitted = st.form_submit_button("添加记录")
    if submitted:
        if not meal_name.strip():
            st.error("请填写食物名称")
        else:
            repo.log_meal(
                name=meal_name.strip(),
                meal_type=meal_type,
                calories=calories if calories else None,
                protein_g=protein if protein else None,
                carb_g=carb if carb else None,
                fat_g=fat if fat else None,
                notes=meal_notes,
                target_date=target.isoformat(),
            )
            st.session_state["meal_logged_flash"] = True
            st.rerun()
