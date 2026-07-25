"""手动管理一周训练计划模板。"""

from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from bootstrap import get_repo, load_env
from db.repository import WEEKDAY_CN, WEEKDAY_KEYS
from ui import page_header, render_sidebar

st.set_page_config(page_title="训练计划", page_icon="📋", layout="wide")
load_env()
render_sidebar()
repo = get_repo()

page_header(
    "训练计划",
    "手动编辑一周模板；保存后「今日训练」会按新计划同步（未开始打卡时）。",
)
st.caption(
    "计量：哑铃重量=单手；单侧次数=每侧；静力可把次数写成秒（如 45 或 45s），"
    "或在备注写 measure=seconds。"
)


def empty_week() -> dict:
    return {
        key: {"name": "休息", "rest": True, "exercises": []}
        for key in WEEKDAY_KEYS
    }


def normalize_week(content: dict | None) -> dict:
    base = empty_week()
    if not content:
        return base
    for key in WEEKDAY_KEYS:
        raw = content.get(key) or content.get(WEEKDAY_CN[key]) or {}
        if not isinstance(raw, dict):
            continue
        exercises = []
        for ex in raw.get("exercises") or []:
            if not isinstance(ex, dict):
                continue
            name = ex.get("name") or ex.get("exercise") or ""
            if not name:
                continue
            exercises.append(
                {
                    "name": name,
                    "sets": int(ex.get("sets") or 3),
                    "reps": str(ex.get("reps") or "8-12"),
                    "weight_kg": float(ex["weight_kg"])
                    if ex.get("weight_kg") is not None
                    else None,
                    "notes": ex.get("notes") or "",
                }
            )
        base[key] = {
            "name": raw.get("name") or ("休息" if raw.get("rest") else "训练"),
            "rest": bool(raw.get("rest", False)),
            "exercises": exercises,
        }
    return base


def exercises_to_df(exercises: list[dict]) -> pd.DataFrame:
    if not exercises:
        return pd.DataFrame(
            columns=["name", "sets", "reps", "weight_kg", "notes"]
        )
    return pd.DataFrame(exercises)[["name", "sets", "reps", "weight_kg", "notes"]]


def df_to_exercises(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    rows = []
    for _, row in df.iterrows():
        name = str(row.get("name") or "").strip()
        if not name or name == "nan":
            continue
        weight = row.get("weight_kg")
        if weight is None or (isinstance(weight, float) and pd.isna(weight)):
            weight_val = None
        else:
            try:
                weight_val = float(weight)
            except (TypeError, ValueError):
                weight_val = None
        try:
            sets_val = int(row.get("sets") or 3)
        except (TypeError, ValueError):
            sets_val = 3
        rows.append(
            {
                "name": name,
                "sets": max(1, sets_val),
                "reps": str(row.get("reps") or "8-12"),
                "weight_kg": weight_val,
                "notes": str(row.get("notes") or ""),
            }
        )
    return rows


current = repo.get_current_plan()
if "plan_draft" not in st.session_state:
    st.session_state["plan_draft"] = normalize_week(
        current["content"] if current else None
    )
    st.session_state["plan_draft_name"] = (
        current["name"] if current else "我的训练计划"
    )
    st.session_state["plan_draft_version"] = current["id"] if current else None

# 若外部（AI）更新了计划，提示可重新载入
if current and st.session_state.get("plan_draft_version") != current["id"]:
    st.warning("数据库里的计划已更新（可能是教练对话改过）。")
    if st.button("重新载入最新计划到编辑器"):
        st.session_state["plan_draft"] = normalize_week(current["content"])
        st.session_state["plan_draft_name"] = current["name"]
        st.session_state["plan_draft_version"] = current["id"]
        for key in WEEKDAY_KEYS:
            st.session_state.pop(f"editor_{key}", None)
            st.session_state.pop(f"day_name_{key}", None)
            st.session_state.pop(f"rest_{key}", None)
            st.session_state.pop(f"pick_{key}", None)
        st.rerun()

draft = st.session_state["plan_draft"]

top1, top2, top3 = st.columns([2, 1, 1])
with top1:
    plan_name = st.text_input("计划名称", value=st.session_state["plan_draft_name"])
    st.session_state["plan_draft_name"] = plan_name
with top2:
    if st.button("新建空白一周", width="stretch"):
        st.session_state["plan_draft"] = empty_week()
        st.session_state["plan_draft_name"] = "新计划"
        st.session_state["plan_draft_version"] = None
        for key in WEEKDAY_KEYS:
            st.session_state.pop(f"editor_{key}", None)
            st.session_state.pop(f"day_name_{key}", None)
            st.session_state.pop(f"rest_{key}", None)
            st.session_state.pop(f"pick_{key}", None)
        st.rerun()
with top3:
    st.page_link("pages/8_动作库.py", label="浏览动作库", icon="📖")

day_labels = [f"{WEEKDAY_CN[k]}（{k}）" for k in WEEKDAY_KEYS]
selected_label = st.radio("选择要编辑的一天", day_labels, horizontal=True)
day_key = WEEKDAY_KEYS[day_labels.index(selected_label)]
day = draft[day_key]

st.subheader(WEEKDAY_CN[day_key])
c1, c2 = st.columns([2, 1])
with c1:
    day_name = st.text_input(
        "当日名称",
        value=day.get("name") or "",
        key=f"day_name_{day_key}",
        placeholder="例如：胸肩推 / 背拉 / 腿日",
    )
with c2:
    is_rest = st.checkbox(
        "休息日",
        value=bool(day.get("rest")),
        key=f"rest_{day_key}",
    )

if is_rest:
    st.info("休息日不会生成打卡动作。取消勾选后可编辑动作列表。")
    draft[day_key] = {"name": day_name or "休息", "rest": True, "exercises": []}
else:
    st.markdown("编辑动作表（可直接改单元格；底部空行可新增）")
    edited = st.data_editor(
        exercises_to_df(day.get("exercises") or []),
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("动作名称", required=True, width="medium"),
            "sets": st.column_config.NumberColumn("组数", min_value=1, max_value=10, step=1),
            "reps": st.column_config.TextColumn(
                "次数/秒", help="普通动作填次数如 8 或 6-8；平板等静力填秒如 45 或 45s"
            ),
            "weight_kg": st.column_config.NumberColumn(
                "重量kg", min_value=0.0, step=1.0, help="哑铃等双手各持时填单手重量"
            ),
            "notes": st.column_config.TextColumn("备注"),
        },
        key=f"editor_{day_key}",
    )
    exercises = df_to_exercises(edited)

    # 快捷从动作库添加（先搜再选，避免 900+ 下拉）
    st.markdown("##### 从动作库添加")
    pending = st.session_state.pop("lib_pending_add", None)
    add_q = st.text_input(
        "搜索动作",
        placeholder="输入关键词，如：深蹲 / 卧推 / squat",
        key=f"add_q_{day_key}",
    )
    if pending:
        hits = repo.list_exercises(query=pending, limit=20)
        if not any(e["name"] == pending for e in hits):
            ex = repo.get_exercise_by_name(pending)
            hits = [ex] + hits if ex else hits
        st.session_state[f"pick_{day_key}"] = pending
    else:
        hits = (
            repo.list_exercises(query=add_q.strip(), limit=40)
            if add_q.strip()
            else []
        )
    options = [""] + [e["name"] for e in hits]
    if not add_q.strip() and not pending:
        st.caption("先输入关键词再选择。")
    pick = st.selectbox(
        "从搜索结果选择",
        options=options,
        key=f"pick_{day_key}",
    )
    pick_ex = next((e for e in hits if e["name"] == pick), None)
    if pick_ex is None and pick:
        pick_ex = repo.get_exercise_by_name(pick)
    if pick_ex:
        c_img, c_meta = st.columns([1, 2])
        with c_img:
            if pick_ex.get("image_url"):
                try:
                    st.image(pick_ex["image_url"], width=160)
                except Exception:
                    st.caption("配图需联网")
        with c_meta:
            if pick_ex.get("name_en"):
                st.caption(pick_ex["name_en"])
            st.caption(
                f"{pick_ex.get('muscle') or '-'} · {pick_ex.get('equipment') or '-'}"
            )
            if pick_ex.get("tips"):
                tip = pick_ex["tips"]
                if not any("\u4e00" <= c <= "\u9fff" for c in tip):
                    tip = tip[:100] + "…"
                st.caption(tip[:140])
    if st.button("添加选中动作", key=f"add_{day_key}", width="stretch", type="primary"):
        if pick:
            exercises.append(
                {
                    "name": pick,
                    "sets": 3,
                    "reps": "8-12",
                    "weight_kg": None,
                    "notes": "",
                }
            )
            draft[day_key] = {
                "name": day_name or "训练",
                "rest": False,
                "exercises": exercises,
            }
            st.session_state["plan_draft"] = draft
            st.session_state.pop(f"editor_{day_key}", None)
            st.rerun()
        else:
            st.warning("请先搜索并选择动作")

    draft[day_key] = {
        "name": day_name or "训练",
        "rest": False,
        "exercises": exercises,
    }

st.session_state["plan_draft"] = draft

st.divider()
st.subheader("本周一览")
summary_rows = []
for key in WEEKDAY_KEYS:
    d = draft[key]
    if d.get("rest"):
        summary_rows.append(
            {"星期": WEEKDAY_CN[key], "安排": d.get("name") or "休息", "动作数": 0}
        )
    else:
        names = "、".join(ex["name"] for ex in d.get("exercises") or [])
        summary_rows.append(
            {
                "星期": WEEKDAY_CN[key],
                "安排": d.get("name") or "训练",
                "动作数": len(d.get("exercises") or []),
                "动作": names,
            }
        )
st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

save_l, save_r = st.columns([1, 1])
with save_l:
    if st.button("保存计划模板", type="primary", width="stretch"):
        # 再从 session 取最新 draft
        content = copy.deepcopy(st.session_state["plan_draft"])
        saved = repo.save_plan(content, name=st.session_state["plan_draft_name"])
        repo.sync_today_from_plan_if_idle()
        st.session_state["plan_draft_version"] = saved["id"]
        st.success("已保存。若今日尚未开始打卡，会按新模板同步。")
        st.rerun()
with save_r:
    if st.button("放弃修改并重新载入", width="stretch"):
        cur = repo.get_current_plan()
        st.session_state["plan_draft"] = normalize_week(
            cur["content"] if cur else None
        )
        st.session_state["plan_draft_name"] = cur["name"] if cur else "我的训练计划"
        st.session_state["plan_draft_version"] = cur["id"] if cur else None
        for key in WEEKDAY_KEYS:
            st.session_state.pop(f"editor_{key}", None)
            st.session_state.pop(f"day_name_{key}", None)
            st.session_state.pop(f"rest_{key}", None)
            st.session_state.pop(f"pick_{key}", None)
        st.rerun()
