"""设置页：画像、API Key、数据库。"""

from __future__ import annotations

import os

import streamlit as st

from agent.doubao import get_doubao_api_key
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

need_mimo = not get_api_key() or get_api_key().startswith("sk-xxxxx")
need_doubao = not get_doubao_api_key() or get_doubao_api_key().startswith("sk-xxxxx")

with st.expander("API 配置", expanded=need_mimo or need_doubao):
    st.markdown("##### MiMo")
    current = get_api_key()
    masked = (
        (current[:6] + "…" + current[-4:])
        if current and len(current) > 12
        else (current or "未配置")
    )
    st.caption(f"当前 Key：{masked}")
    new_key = st.text_input("MIMO_API_KEY", type="password", placeholder="sk-…")
    if st.button("保存 API Key 到 .env"):
        if not new_key.strip():
            st.error("Key 不能为空")
        else:
            save_api_key_to_env(new_key.strip())
            st.success("已写入 .env，可前往「教练对话」使用。")

    st.markdown("##### 豆包看图（饮食拍照）")
    doubao_key = get_doubao_api_key()
    d_masked = (
        (doubao_key[:6] + "…" + doubao_key[-4:])
        if doubao_key and len(doubao_key) > 12
        else (doubao_key or "未配置")
    )
    st.caption(f"当前 DOUBAO_API_KEY：{d_masked}")
    st.caption(
        "在火山方舟开通视觉模型后填写 Key；DOUBAO_MODEL 可为模型名或接入点 ID（ep-xxxx）。"
    )
    new_doubao = st.text_input(
        "DOUBAO_API_KEY", type="password", placeholder="火山方舟 API Key"
    )
    new_model = st.text_input(
        "DOUBAO_MODEL（可选）",
        value=os.getenv("DOUBAO_MODEL", "doubao-seed-2-0-lite-260428"),
    )
    if st.button("保存豆包配置到 .env"):
        if not new_doubao.strip():
            st.error("Key 不能为空")
        else:
            upsert_env_var("DOUBAO_API_KEY", new_doubao.strip())
            if new_model.strip():
                upsert_env_var("DOUBAO_MODEL", new_model.strip())
            st.success("豆包配置已保存，可在「饮食管理」拍照记账。")

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

    st.markdown("##### 基础信息")
    GENDER_OPTIONS = ["未设置", "男", "女", "其他", "不愿透露"]
    gender_val = profile.get("gender") or "未设置"
    if gender_val not in GENDER_OPTIONS:
        gender_val = "未设置"
    gender = st.selectbox(
        "性别",
        GENDER_OPTIONS,
        index=GENDER_OPTIONS.index(gender_val),
    )
    if gender == "未设置":
        gender = ""
    experience = st.selectbox(
        "经验水平",
        ["新手", "中级", "高级"],
        index=["新手", "中级", "高级"].index(profile.get("experience") or "中级")
        if (profile.get("experience") or "中级") in ["新手", "中级", "高级"]
        else 1,
    )
    days = st.slider("每周可练天数", 1, 7, int(profile.get("days_per_week") or 4))
    equipment = st.selectbox(
        "器械条件",
        ["健身房", "家庭哑铃", "仅自重", "综合"],
        index=["健身房", "家庭哑铃", "仅自重", "综合"].index(
            profile.get("equipment") or "健身房"
        )
        if (profile.get("equipment") or "健身房")
        in ["健身房", "家庭哑铃", "仅自重", "综合"]
        else 0,
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
    height = st.number_input(
        "身高 cm",
        min_value=0.0,
        value=float(profile["height_cm"]) if profile.get("height_cm") else 0.0,
        step=0.1,
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
    injuries = st.text_area("伤病 / 禁忌", value=profile.get("injuries") or "")
    notes = st.text_area("其他备注", value=profile.get("notes") or "")
    submitted = st.form_submit_button("保存画像", type="primary")
    if submitted:
        repo.update_profile(
            goal=goal,
            goal_detail=goal_detail if goal_detail is not None else "",
            gender=gender if gender is not None else "",
            experience=experience,
            days_per_week=days,
            equipment=equipment,
            injuries=injuries,
            weight_kg=weight or None,
            target_weight_kg=target_weight or None,
            body_fat_pct=body_fat or None,
            height_cm=height or None,
            calorie_target=calorie_target or None,
            protein_target_g=protein_target or None,
            carb_target_g=carb_target or None,
            fat_target_g=fat_target or None,
            notes=notes if notes is not None else "",
        )
        st.success("画像已保存")

st.divider()
with st.expander("数据库 / 维护", expanded=False):
    st.code(str(DB_PATH), language=None)
    if st.button("重新初始化表结构（保留已有数据，仅补建缺失表）"):
        init_db()
        reset_repo_cache()
        st.success("已执行 init_db()")
