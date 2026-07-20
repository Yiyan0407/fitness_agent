"""今日训练打卡页 — 一键完成 + 当场改计划。"""

from __future__ import annotations

from datetime import date
import time

import streamlit as st

from agent.calorie_burn import estimate_workout_calories
from agent.llm import MissingAPIKeyError
from bootstrap import get_api_key, get_repo, load_env
from db.schema import init_db
from ui import render_sidebar

st.set_page_config(page_title="今日训练", page_icon="🏋️", layout="wide")
load_env()
init_db()
repo = get_repo()
render_sidebar()

st.title("今日训练")

# 从历史日历跳转时，强制写入 date_input 的 widget state
jump = st.session_state.pop("workout_jump_date", None)
if jump:
    try:
        st.session_state["workout_date_picker"] = date.fromisoformat(str(jump)[:10])
    except ValueError:
        pass
if "workout_date_picker" not in st.session_state:
    st.session_state["workout_date_picker"] = date.today()

target = st.date_input("日期", key="workout_date_picker")
today = repo.get_today_workout(target.isoformat())
plan = today.get("plan")
workout = today["workout"]
sets = today.get("sets") or []

if not repo.get_current_plan():
    st.warning("还没有训练计划。")
    st.page_link("pages/1_教练对话.py", label="去让教练生成计划", icon="💬")
    st.page_link("pages/3_训练计划.py", label="或手动编辑计划", icon="📋")
    st.stop()

if plan and plan.get("rest"):
    st.info(f"{target.isoformat()} 计划为休息日。")
    notes = st.text_area("备注", value=workout.get("notes") or "")
    if st.button("保存备注"):
        repo.update_workout(workout["id"], notes=notes)
        st.success("已保存")
    st.stop()

done = sum(1 for s in sets if s.get("completed"))
total = len(sets)
pending = total - done
name = (plan or {}).get("name") or "训练"
st.subheader(f"{name}")
st.caption(f"状态：{workout.get('status')} · {target.isoformat()}")
if total:
    st.progress(done / total, text=f"{done}/{total} 组已完成")

# 运动消耗
burn = workout.get("calories_burned")
burn_note = workout.get("calories_burned_note") or ""
b1, b2, b3 = st.columns([2, 2, 2])
with b1:
    if burn is not None:
        st.metric("运动消耗", f"{float(burn):.0f} kcal")
    else:
        st.metric("运动消耗", "未估算")
with b2:
    can_ai = get_api_key() and not get_api_key().startswith("sk-xxxxx")
    if st.button(
        "AI 估算消耗",
        width="stretch",
        disabled=not can_ai or done == 0,
        help="根据画像与已完成组估算额外消耗并入库",
    ):
        with st.spinner("正在按画像估算运动消耗…"):
            try:
                result = estimate_workout_calories(target.isoformat(), save=True)
            except MissingAPIKeyError as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001
                st.error(f"估算失败：{exc}")
            else:
                st.toast(f"已记录约 {result['calories_burned']} kcal")
                st.rerun()
with b3:
    manual = st.number_input(
        "手动修正 kcal",
        min_value=0.0,
        value=float(burn) if burn is not None else 0.0,
        step=10.0,
        key="manual_burn",
    )
    if st.button("保存消耗", width="stretch"):
        repo.update_workout(
            workout["id"],
            calories_burned=manual or None,
            calories_burned_note=(burn_note or "手动录入") if manual else "",
            clear_calories_burned=not manual,
        )
        st.toast("已保存运动消耗")
        st.rerun()
if burn_note:
    st.caption(burn_note)
if done == 0:
    st.caption("完成至少一组后再估算运动消耗。")

# 今日整体临时调整
with st.expander("今天临时改安排（推不动 / 没力气）", expanded=pending > 0 and done > 0):
    st.caption("只改今天的打卡列表，不会自动改一周模板。要改模板请去「训练计划」。")
    g1, g2, g3 = st.columns(3)
    with g1:
        if st.button("结束剩余组（没力气了）", width="stretch"):
            n = repo.skip_remaining_sets(workout["id"])
            repo.update_workout(workout["id"], status="done")
            st.toast(f"已去掉 {n} 组未完成")
            st.rerun()
    with g2:
        if st.button("全部剩余重量 -2.5kg", width="stretch"):
            names = {s["exercise_name"] for s in sets if not s.get("completed")}
            for ex in names:
                repo.apply_to_remaining_sets(
                    workout["id"], ex, weight_delta=-2.5
                )
            st.toast("已给剩余组减重 2.5kg")
            st.rerun()
    with g3:
        st.page_link("pages/3_训练计划.py", label="编辑一周模板", icon="📋")

with st.expander("高级：从周计划重置今日组数", expanded=False):
    if st.button("重新生成今日组数（清空本日记录）"):
        for s in repo.get_sets(workout["id"]):
            repo.conn.execute("DELETE FROM sets WHERE id = ?", (s["id"],))
        repo.conn.commit()
        repo.ensure_today_sets_from_plan(target, force=True)
        st.rerun()

if not sets:
    st.info("今日暂无动作。可让教练调整计划，或下方手动追加。")
else:
    by_ex: dict[str, list] = {}
    for s in sets:
        by_ex.setdefault(s["exercise_name"], []).append(s)

    if st.session_state.get("rest_until"):
        remaining = int(st.session_state["rest_until"] - time.time())
        if remaining > 0:
            st.info(f"组间休息：还剩 **{remaining}** 秒（可照常改重量，或点跳过）")
            if st.button("跳过休息"):
                st.session_state.pop("rest_until", None)
                st.rerun()
        else:
            st.session_state.pop("rest_until", None)
            st.toast("休息结束，下一组！")

    for ex_name, ex_sets in by_ex.items():
        finished = sum(1 for s in ex_sets if s.get("completed"))
        left = [s for s in ex_sets if not s.get("completed")]
        st.markdown(f"### {ex_name}　`{finished}/{len(ex_sets)}`")
        last = repo.get_last_completed_set(ex_name, before_date=target.isoformat())
        if last:
            st.caption(
                f"上次（{last['workout_date']}）："
                f"{last.get('weight_kg') or '-'} kg × {last.get('reps') or '-'} 次"
                + (f" · RPE {last['rpe']}" if last.get("rpe") else "")
            )

        if left:
            with st.container(border=True):
                st.caption("本动作临时调整")
                a1, a2, a3, a4, a5 = st.columns(5)
                cur_w = float(left[0].get("weight_kg") or 0)
                if a1.button("剩余-2.5kg", key=f"ex_wm_{ex_name}", width="stretch"):
                    repo.apply_to_remaining_sets(
                        workout["id"], ex_name, weight_delta=-2.5
                    )
                    st.rerun()
                if a2.button("剩余+2.5kg", key=f"ex_wp_{ex_name}", width="stretch"):
                    repo.apply_to_remaining_sets(
                        workout["id"], ex_name, weight_delta=2.5
                    )
                    st.rerun()
                if a3.button("去掉最后一组", key=f"ex_drop_{ex_name}", width="stretch"):
                    if repo.drop_last_incomplete_set(workout["id"], ex_name):
                        st.toast(f"已去掉 {ex_name} 最后一组")
                    st.rerun()
                if a4.button("跳过剩余组", key=f"ex_skip_{ex_name}", width="stretch"):
                    n = repo.skip_remaining_sets(workout["id"], ex_name)
                    st.toast(f"已跳过 {n} 组")
                    st.rerun()
                if a5.button("再加一组", key=f"ex_add_{ex_name}", width="stretch"):
                    repo.add_planned_set(workout["id"], ex_name)
                    st.rerun()

                set_w = st.number_input(
                    "把剩余组重量统一设为 (kg)",
                    min_value=0.0,
                    value=cur_w,
                    step=2.5,
                    key=f"ex_setw_{ex_name}",
                )
                if st.button("应用到剩余组", key=f"ex_applyw_{ex_name}"):
                    repo.apply_to_remaining_sets(
                        workout["id"], ex_name, weight_kg=set_w
                    )
                    st.toast(f"{ex_name} 剩余组已改为 {set_w:g} kg")
                    st.rerun()

        for s in ex_sets:
            sid = s["id"]
            if s.get("completed"):
                st.success(
                    f"第 {s['set_index']} 组已完成 · "
                    f"{s.get('weight_kg') or '-'} kg × {s.get('reps') or '-'} 次"
                    + (f" · RPE {s['rpe']}" if s.get("rpe") else "")
                )
                if st.button("撤销完成", key=f"undo_{sid}"):
                    repo.update_set(sid, completed=False)
                    st.rerun()
                continue

            weight = float(s["weight_kg"] or 0)
            reps = int(s["reps"] or 0)
            rpe = float(s["rpe"] or 0)

            st.markdown(f"**第 {s['set_index']} 组**　`{weight:g} kg × {reps} 次`")
            b1, b2, b3, b4, b5, b6 = st.columns(6)
            if b1.button("重量-2.5", key=f"wm_{sid}", width="stretch"):
                repo.bump_set_field(sid, "weight_kg", -2.5)
                st.rerun()
            if b2.button("重量+2.5", key=f"wp_{sid}", width="stretch"):
                repo.bump_set_field(sid, "weight_kg", 2.5)
                st.rerun()
            if b3.button("次数-1", key=f"rm_{sid}", width="stretch"):
                repo.bump_set_field(sid, "reps", -1)
                st.rerun()
            if b4.button("次数+1", key=f"rp_{sid}", width="stretch"):
                repo.bump_set_field(sid, "reps", 1)
                st.rerun()
            if b5.button("完成此组", key=f"ok_{sid}", type="primary", width="stretch"):
                repo.complete_set(
                    sid,
                    weight_kg=weight or None,
                    reps=reps or None,
                    rpe=rpe or None,
                )
                st.session_state["rest_until"] = time.time() + 90
                st.toast(f"已完成第 {s['set_index']} 组")
                st.rerun()
            with b6:
                with st.popover("更多"):
                    new_rpe = st.slider(
                        "RPE", 0.0, 10.0, rpe or 7.0, 0.5, key=f"rpe_{sid}"
                    )
                    if st.button("保存 RPE", key=f"save_rpe_{sid}"):
                        repo.update_set(sid, rpe=new_rpe)
                        st.rerun()
                    if st.button("跳过这一组", key=f"skip_one_{sid}"):
                        repo.delete_set(sid)
                        st.toast("已跳过本组")
                        st.rerun()
            st.divider()

st.divider()
with st.expander("快速追加一组 / 动作", expanded=False):
    with st.form("add_set"):
        name_in = st.text_input("动作名称")
        w = st.number_input("重量 kg", min_value=0.0, value=0.0, step=2.5)
        r = st.number_input("次数", min_value=0, value=8, step=1)
        p = st.number_input("RPE", min_value=0.0, max_value=10.0, value=7.0, step=0.5)
        submitted = st.form_submit_button("记录并完成")
        if submitted:
            if not name_in.strip():
                st.error("请填写动作名称")
            else:
                repo.log_set(
                    exercise_name=name_in.strip(),
                    weight_kg=w or None,
                    reps=int(r) or None,
                    rpe=p or None,
                    target_date=target.isoformat(),
                )
                st.success("已记录")
                st.rerun()

notes = st.text_area("训练备注", value=workout.get("notes") or "")
c1, c2 = st.columns(2)
if c1.button("保存备注", width="stretch"):
    repo.update_workout(workout["id"], notes=notes)
    st.success("备注已保存")
if c2.button("标记今日完成", width="stretch", type="primary"):
    repo.update_workout(workout["id"], status="done", notes=notes)
    st.success("今日训练已完成")
    st.rerun()
