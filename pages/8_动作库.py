"""动作库浏览页 — 按肌群/器械筛选，完整一览与配图预览。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from bootstrap import get_repo, load_env
from ui import page_header, render_sidebar

st.set_page_config(page_title="动作库", page_icon="📖", layout="wide")
load_env()
render_sidebar()
repo = get_repo()

page_header(
    "动作库",
    "按肌群与器械浏览本地动作；配图需联网。要加入周计划请去「训练计划」页编辑。",
)

lib_all = repo.list_exercises()
total = len(lib_all)
if total == 0:
    st.warning("未找到动作库文件（data/exercises.json）。")
    st.stop()

muscles = sorted({e.get("muscle") or "" for e in lib_all if e.get("muscle")})
equips = sorted({e.get("equipment") or "" for e in lib_all if e.get("equipment")})

f1, f2, f3 = st.columns([2, 1, 1])
with f1:
    q = st.text_input("搜索", placeholder="深蹲 / squat / 胸", key="exlib_q")
with f2:
    muscle_f = st.selectbox("肌群", ["全部"] + muscles, key="exlib_muscle")
with f3:
    equip_f = st.selectbox("器械", ["全部"] + equips, key="exlib_equip")

filtered = repo.list_exercises(
    query=q or "",
    muscle="" if muscle_f == "全部" else muscle_f,
    equipment="" if equip_f == "全部" else equip_f,
)
st.caption(f"命中 **{len(filtered)}** / 库内 {total} 个动作")

if not filtered:
    st.info("没有匹配的动作，试试换关键词或筛选项。")
    st.stop()

df = pd.DataFrame(
    [
        {
            "name": e.get("name") or "",
            "name_en": e.get("name_en") or "",
            "muscle": e.get("muscle") or "",
            "equipment": e.get("equipment") or "",
            "tips": e.get("tips") or "",
        }
        for e in filtered
    ]
)

left, right = st.columns([3, 2])
with left:
    st.subheader("一览")
    event = st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="exlib_table",
        column_config={
            "name": st.column_config.TextColumn("动作", width="medium"),
            "name_en": st.column_config.TextColumn("英文名", width="medium"),
            "muscle": st.column_config.TextColumn("肌群", width="small"),
            "equipment": st.column_config.TextColumn("器械", width="small"),
            "tips": st.column_config.TextColumn("要点", width="large"),
        },
    )

selected_name = ""
rows = (event.selection.rows if event and getattr(event, "selection", None) else None) or []
if rows:
    idx = int(rows[0])
    if 0 <= idx < len(filtered):
        selected_name = str(filtered[idx].get("name") or "")
        st.session_state["exlib_preview"] = selected_name

names = [str(e.get("name") or "") for e in filtered]
if st.session_state.get("exlib_preview") not in names:
    st.session_state["exlib_preview"] = names[0]

with right:
    st.subheader("详情")
    pick = st.selectbox(
        "预览动作",
        options=names,
        key="exlib_preview",
    )
    ex = next((e for e in filtered if e.get("name") == pick), None)
    if ex:
        if ex.get("image_url"):
            try:
                st.image(ex["image_url"], width=320)
            except Exception:
                st.caption("配图加载失败（需联网）")
        else:
            st.caption("暂无配图")
        st.markdown(f"**{ex.get('name') or ''}**")
        if ex.get("name_en"):
            st.caption(ex["name_en"])
        st.write(
            f"肌群：{ex.get('muscle') or '-'} · 器械：{ex.get('equipment') or '-'}"
        )
        if ex.get("tips"):
            st.info(ex["tips"])
        st.page_link(
            "pages/3_训练计划.py",
            label="去训练计划添加此动作",
            icon="📋",
        )
