"""饮食管理页 — 进度与明细；记账请去教练对话。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from bootstrap import get_repo, load_env
from db.schema import init_db
from ui import render_sidebar

st.set_page_config(page_title="饮食管理", page_icon="🥗", layout="wide")
load_env()
init_db()
repo = get_repo()
render_sidebar()

st.title("饮食管理")
st.caption("这里看进度和明细；记账请到「教练对话」用文字或拍照。")

go1, go2 = st.columns(2)
with go1:
    st.page_link("pages/1_教练对话.py", label="去教练对话记账", icon="💬")
with go2:
    if st.button("快捷：喝了一瓶可乐（发给教练）", width="stretch"):
        st.session_state["pending_chat"] = "喝了一瓶可乐，帮我记到饮食里"
        st.switch_page("pages/1_教练对话.py")

target = st.date_input("日期", value=date.today())
day = repo.get_nutrition_day(target.isoformat())
totals = day["totals"]
targets = day["targets"]
meals = day["meals"]

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "热量 kcal",
    f"{totals['calories']:.0f}",
    None
    if not targets.get("calorie_target")
    else f"目标 {targets['calorie_target']:.0f}",
)
c2.metric(
    "蛋白质 g",
    f"{totals['protein_g']:.0f}",
    None
    if not targets.get("protein_target_g")
    else f"目标 {targets['protein_target_g']:.0f}",
)
c3.metric("碳水 g", f"{totals['carb_g']:.0f}")
c4.metric("脂肪 g", f"{totals['fat_g']:.0f}")

if targets.get("calorie_target"):
    ratio = min(1.0, totals["calories"] / float(targets["calorie_target"]))
    st.progress(
        ratio,
        text=f"热量进度 {totals['calories']:.0f}/{targets['calorie_target']:.0f}",
    )
if targets.get("protein_target_g"):
    pr = min(1.0, totals["protein_g"] / float(targets["protein_target_g"]))
    st.progress(
        pr,
        text=f"蛋白进度 {totals['protein_g']:.0f}/{targets['protein_target_g']:.0f}",
    )

if not targets.get("calorie_target") and not targets.get("protein_target_g"):
    st.info("还没设饮食目标。可在教练对话里让教练估算，或在下方填写。")

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
        "删除某条记录",
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
with st.expander("饮食目标", expanded=False):
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
                calorie_target=cal or None,
                protein_target_g=pro or None,
                carb_target_g=carb_t or None,
                fat_target_g=fat_t or None,
            )
            st.success("已保存")
            st.rerun()

with st.expander("近 7 天饮食汇总", expanded=False):
    recent = repo.get_recent_nutrition(7)
    if not recent["daily"]:
        st.caption("暂无记录")
    else:
        st.dataframe(pd.DataFrame(recent["daily"]), width="stretch", hide_index=True)

with st.expander("手动精确填写（可选）", expanded=False):
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
                    calories=calories or None,
                    protein_g=protein or None,
                    carb_g=carb or None,
                    fat_g=fat or None,
                    notes=meal_notes,
                    target_date=target.isoformat(),
                )
                st.success("已记录")
                st.rerun()
