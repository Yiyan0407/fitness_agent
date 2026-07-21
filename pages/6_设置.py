"""设置页：画像、API Key、数据库。"""

from __future__ import annotations

import os

import streamlit as st

from bootstrap import (
    get_api_key,
    get_repo,
    load_env,
    reset_repo_cache,
    save_api_key_to_env,
    upsert_env_var,
)
from db.schema import DB_PATH, init_db
from ui import render_sidebar

st.set_page_config(page_title="设置", page_icon="⚙️", layout="centered")
load_env()
init_db()
repo = get_repo()
render_sidebar()

st.title("设置")

if st.session_state.pop("profile_saved_flash", False):
    st.success("画像已保存")
    st.toast("画像已保存")

need_mimo = not get_api_key() or get_api_key().startswith("sk-xxxxx")

st.subheader("API 配置")
if need_mimo:
    st.caption("请先配置 MIMO_API_KEY（教练对话与饮食拍照共用）")
st.markdown("##### 小米 MiMo")
current = get_api_key()
masked = (
    (current[:6] + "…" + current[-4:])
    if current and len(current) > 12
    else (current or "未配置")
)
st.caption(f"当前 Key：{masked}")
st.caption(
    "教练默认 mimo-v2.5-pro；饮食拍照用全模态 mimo-v2.5。同一 Key 即可。"
)
new_key = st.text_input("MIMO_API_KEY", type="password", placeholder="sk-…")
vision_model = st.text_input(
    "MIMO_VISION_MODEL（可选）",
    value=os.getenv("MIMO_VISION_MODEL", "mimo-v2.5"),
)
if st.button("保存 API 配置到 .env"):
    if not new_key.strip() and need_mimo:
        st.error("Key 不能为空")
    else:
        if new_key.strip():
            save_api_key_to_env(new_key.strip())
        if vision_model.strip():
            upsert_env_var("MIMO_VISION_MODEL", vision_model.strip())
        st.success("已保存。教练与拍照记账都走 MiMo。")

st.subheader("个人画像")
profile = repo.get_profile()

GOAL_OPTIONS = ["增肌", "减脂", "体能", "保持健康", "力量"]

with st.form("profile_form"):
    st.markdown("##### 目标")
    goal = st.selectbox(
        "训练方向",
        GOAL_OPTIONS,
        index=GOAL_OPTIONS.index(profile.get("goal") or "增肌")
        if (profile.get("goal") or "增肌") in GOAL_OPTIONS
        else 0,
        help="大方向，教练排计划时会优先参考",
    )
    goal_detail = st.text_area(
        "具体目标",
        value=profile.get("goal_detail") or "",
        placeholder="例如：3 个月内增重到 75kg；卧推冲击 100kg；夏天前体脂降到 15%",
        help="越具体，教练越容易帮你定组数、强度和进度",
    )
    target_weight = st.number_input(
        "目标体重 kg",
        min_value=0.0,
        value=float(profile["target_weight_kg"])
        if profile.get("target_weight_kg")
        else 0.0,
        step=0.1,
        help="没有可填 0",
    )
    target_bf = st.number_input(
        "目标体脂 %",
        min_value=0.0,
        max_value=60.0,
        value=float(profile["target_body_fat_pct"])
        if profile.get("target_body_fat_pct")
        else 0.0,
        step=0.1,
        help="没有可填 0",
    )

    st.markdown("##### 基础信息")
    GENDER_OPTIONS = ["未设置", "男", "女", "其他", "不愿透露"]
    gender_val = profile.get("gender") or "未设置"
    if gender_val not in GENDER_OPTIONS:
        gender_val = "未设置"
    g1, g2 = st.columns(2)
    gender = g1.selectbox(
        "性别",
        GENDER_OPTIONS,
        index=GENDER_OPTIONS.index(gender_val),
    )
    if gender == "未设置":
        gender = ""
    age = g2.number_input(
        "年龄",
        min_value=0,
        max_value=120,
        value=int(profile["age"]) if profile.get("age") else 0,
        step=1,
        help="没有可填 0；用于热量与强度建议",
    )
    experience = st.selectbox(
        "经验水平",
        ["新手", "中级", "高级"],
        index=["新手", "中级", "高级"].index(profile.get("experience") or "中级")
        if (profile.get("experience") or "中级") in ["新手", "中级", "高级"]
        else 1,
    )
    days = st.slider("每周可练天数", 1, 7, int(profile.get("days_per_week") or 4))
    session_minutes = st.slider(
        "单次可练时长（分钟）",
        20,
        150,
        int(profile.get("session_minutes") or 60),
        step=5,
        help="教练排计划时会按此控制动作数量与休息",
    )
    ACTIVITY_OPTIONS = ["久坐", "轻度活动", "中度活动", "重度活动"]
    raw_act = profile.get("activity_level") or "轻度活动"
    if raw_act not in ACTIVITY_OPTIONS:
        raw_act = "轻度活动"
    activity_level = st.selectbox(
        "日常活动量（非训练日）",
        ACTIVITY_OPTIONS,
        index=ACTIVITY_OPTIONS.index(raw_act),
        help="久坐≈办公室；轻度≈日常走动；中度≈站立/体力工作；重度≈重体力",
    )
    SPLIT_OPTIONS = ["随教练", "全身", "推拉腿", "上下肢", "五分化"]
    raw_split = profile.get("preferred_split") or "随教练"
    if raw_split not in SPLIT_OPTIONS:
        raw_split = "随教练"
    preferred_split = st.selectbox(
        "偏好分化",
        SPLIT_OPTIONS,
        index=SPLIT_OPTIONS.index(raw_split),
        help="排周计划时优先按此结构",
    )
    EQUIP_OPTIONS = ["健身房", "家庭哑铃杠铃", "仅自重", "弹力带为主", "综合"]
    raw_equip = profile.get("equipment") or "健身房"
    if raw_equip == "家庭哑铃":
        raw_equip = "家庭哑铃杠铃"
    if raw_equip not in EQUIP_OPTIONS:
        raw_equip = "健身房"
    equipment = st.selectbox(
        "器械条件",
        EQUIP_OPTIONS,
        index=EQUIP_OPTIONS.index(raw_equip),
        help="教练排计划时会按此条件优先挑选动作库器械",
    )
    w1, w2 = st.columns(2)
    weight = w1.number_input(
        "当前体重 kg",
        min_value=0.0,
        value=float(profile["weight_kg"]) if profile.get("weight_kg") else 0.0,
        step=0.1,
    )
    body_fat = w2.number_input(
        "当前体脂 %",
        min_value=0.0,
        max_value=60.0,
        value=float(profile["body_fat_pct"]) if profile.get("body_fat_pct") else 0.0,
        step=0.1,
        help="没有可填 0；有变化时在这里更新",
    )
    h1, h2 = st.columns(2)
    height = h1.number_input(
        "身高 cm",
        min_value=0.0,
        value=float(profile["height_cm"]) if profile.get("height_cm") else 0.0,
        step=0.1,
    )
    sleep_hours = h2.number_input(
        "平均睡眠小时",
        min_value=0.0,
        max_value=16.0,
        value=float(profile["sleep_hours"]) if profile.get("sleep_hours") else 0.0,
        step=0.5,
        help="没有可填 0；影响恢复与容量建议",
    )
    st.markdown("##### 饮食目标")
    d1, d2 = st.columns(2)
    calorie_target = d1.number_input(
        "每日热量 kcal",
        min_value=0.0,
        value=float(profile["calorie_target"] or 0),
        step=50.0,
    )
    protein_target = d2.number_input(
        "每日蛋白 g",
        min_value=0.0,
        value=float(profile["protein_target_g"] or 0),
        step=5.0,
    )
    d3, d4 = st.columns(2)
    carb_target = d3.number_input(
        "每日碳水 g",
        min_value=0.0,
        value=float(profile["carb_target_g"] or 0),
        step=5.0,
    )
    fat_target = d4.number_input(
        "每日脂肪 g",
        min_value=0.0,
        value=float(profile["fat_target_g"] or 0),
        step=5.0,
    )
    diet_prefs = st.text_area(
        "饮食偏好 / 忌口",
        value=profile.get("diet_prefs") or "",
        placeholder="例如：不吃猪肉；乳糖不耐；工作日只吃两餐；偏好高蛋白简餐",
    )
    injuries = st.text_area("伤病 / 禁忌", value=profile.get("injuries") or "")
    notes = st.text_area("其他备注", value=profile.get("notes") or "")
    submitted = st.form_submit_button("保存画像", type="primary")
    if submitted:
        # 数字项填 0 = 清空（写入 NULL）；不能用 `x or None` 后直接丢弃，否则旧值不会被清掉
        def _num_or_clear(v: float | int) -> float | int | None:
            return v if v else None

        repo.update_profile(
            goal=goal,
            goal_detail=goal_detail if goal_detail is not None else "",
            gender=gender if gender is not None else "",
            age=_num_or_clear(int(age)),
            experience=experience,
            days_per_week=days,
            session_minutes=int(session_minutes),
            activity_level=activity_level,
            preferred_split=preferred_split,
            equipment=equipment,
            injuries=injuries if injuries is not None else "",
            diet_prefs=diet_prefs if diet_prefs is not None else "",
            sleep_hours=_num_or_clear(sleep_hours),
            weight_kg=_num_or_clear(weight),
            target_weight_kg=_num_or_clear(target_weight),
            body_fat_pct=_num_or_clear(body_fat),
            target_body_fat_pct=_num_or_clear(target_bf),
            height_cm=_num_or_clear(height),
            calorie_target=_num_or_clear(calorie_target),
            protein_target_g=_num_or_clear(protein_target),
            carb_target_g=_num_or_clear(carb_target),
            fat_target_g=_num_or_clear(fat_target),
            notes=notes if notes is not None else "",
        )
        st.session_state["profile_saved_flash"] = True
        st.rerun()

st.divider()
st.caption(f"数据库：{DB_PATH}")
if st.button("重新初始化表结构（保留已有数据，仅补建缺失表）"):
    init_db()
    reset_repo_cache()
    st.success("已执行 init_db()")
