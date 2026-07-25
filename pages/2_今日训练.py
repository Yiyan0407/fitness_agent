"""今日训练打卡页 — 直接改重量/次数，界面尽量干净。"""

from __future__ import annotations

from datetime import date
import time

import streamlit as st

from agent.calorie_burn import estimate_workout_calories
from agent.llm import MissingAPIKeyError
from bootstrap import get_api_key, get_repo, load_env
from ui import page_header, render_sidebar

st.set_page_config(page_title="今日训练", page_icon="🏋️", layout="wide")
load_env()
render_sidebar()
repo = get_repo()

page_header("今日训练", "按组打卡、调重量次数（或秒），练完可估算消耗。")

st.caption(
    "计量约定：哑铃等双手各持 → 重量填**单手**；"
    "保加利亚蹲等单侧 → 次数为**单侧**，左右做完算 1 组；"
    "平板支撑/静蹲等 → 按**秒**计。"
)
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
name = (plan or {}).get("name") or "训练"
st.subheader(name)
st.caption(f"{target.isoformat()} · {workout.get('status')} · 改动只影响今天")
if total:
    st.progress(done / total, text=f"{done}/{total} 组")


def _safe_key(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)[:48]


# 对用户展示自然语言；入库仍存 RPE 数值便于统计
FEEL_OPTIONS = [
    (6.0, "很轻松", "还能再做很多下"),
    (7.0, "比较轻松", "大概还能再做 3 下"),
    (8.0, "有点吃力", "大概还能再做 1～2 下"),
    (9.0, "非常吃力", "最多再挤 1 下"),
    (10.0, "完全力竭", "一根都做不动了"),
]


def _feel_label(rpe: float | None) -> str:
    if rpe is None:
        return "未填感觉"
    best = min(FEEL_OPTIONS, key=lambda item: abs(item[0] - float(rpe)))
    return best[1]


def _save_feel(set_id: int, rpe: float, label: str) -> None:
    repo.update_set(int(set_id), rpe=float(rpe))
    st.session_state.pop("rpe_prompt", None)
    st.toast(f"已记：{label}")
    st.rerun()


def _render_feel_choices(prompt: dict, *, key_prefix: str) -> None:
    sid = int(prompt["set_id"])
    st.caption(
        f"{prompt.get('exercise_name')} · 第 {prompt.get('set_index')} 组 · "
        f"{prompt.get('display') or ((str(prompt.get('weight_kg') or '-') + ' kg × ' + str(prompt.get('reps') or '-')))}"
    )
    for val, title, desc in FEEL_OPTIONS:
        if st.button(
            f"{title}（{desc}）",
            key=f"{key_prefix}_{sid}_{int(val * 10)}",
            width="stretch",
        ):
            _save_feel(sid, val, title)
    if st.button("这组先不填", key=f"{key_prefix}_skip_{sid}", width="stretch"):
        st.session_state.pop("rpe_prompt", None)
        st.toast("已跳过")
        st.rerun()


_HAS_DIALOG = hasattr(st, "dialog")
if _HAS_DIALOG:

    @st.dialog("这组练完感觉怎么样？")
    def _feel_dialog() -> None:
        prompt = st.session_state.get("rpe_prompt")
        if not prompt:
            st.caption("没有待记录的组。")
            return
        _render_feel_choices(prompt, key_prefix="feel_dlg")

else:
    _feel_dialog = None  # type: ignore[assignment]


# 校验待填感觉的组是否还有效
rpe_prompt = st.session_state.get("rpe_prompt")
if rpe_prompt:
    still = next(
        (s for s in sets if s["id"] == rpe_prompt.get("set_id") and s.get("completed")),
        None,
    )
    if not still or still.get("rpe") is not None:
        st.session_state.pop("rpe_prompt", None)
        rpe_prompt = None

# 完成组后弹窗询问感觉
if rpe_prompt and _feel_dialog is not None:
    _feel_dialog()

if st.session_state.get("rest_until"):
    remaining = int(st.session_state["rest_until"] - time.time())
    if remaining > 0:
        r1, r2 = st.columns([4, 1])
        r1.info(f"休息 **{remaining}** 秒")
        if r2.button("跳过", key="skip_rest"):
            st.session_state.pop("rest_until", None)
            st.rerun()
    else:
        st.session_state.pop("rest_until", None)
        st.toast("休息结束")


# --- 动作列表 ---
if not sets:
    st.info("今日暂无动作，可在下方添加，或让教练改计划。")
else:
    by_ex: dict[str, list] = {}
    for s in sets:
        by_ex.setdefault(s["exercise_name"], []).append(s)

    waiting_rpe = rpe_prompt is not None

    for ex_name, ex_sets in by_ex.items():
        ex_key = _safe_key(ex_name)
        finished = sum(1 for s in ex_sets if s.get("completed"))
        pending_sets = [s for s in ex_sets if not s.get("completed")]
        done_sets = [s for s in ex_sets if s.get("completed")]

        head, demo_col = st.columns([5, 1])
        with head:
            st.markdown(f"### {ex_name}　`{finished}/{len(ex_sets)}`")
            last = repo.get_last_completed_set(ex_name, before_date=target.isoformat())
            if last:
                st.caption(
                    f"上次 {last['workout_date']}："
                    f"{last.get('weight_kg') or '-'} kg × {last.get('reps') or '-'}"
                    + (f" · RPE {last['rpe']}" if last.get("rpe") else "")
                )
        with demo_col:
            demo = repo.get_exercise_by_name(ex_name)
            if demo:
                with st.popover("演示"):
                    if demo.get("image_url"):
                        try:
                            st.image(demo["image_url"], width=260)
                        except Exception:
                            st.caption("配图加载失败")
                    if demo.get("tips"):
                        st.caption(demo["tips"])

        # 无弹窗时：把感觉选择画在刚完成的那组所属动作下面
        if (
            rpe_prompt
            and not _HAS_DIALOG
            and rpe_prompt.get("exercise_name") == ex_name
        ):
            st.info("这组练完感觉怎么样？")
            _render_feel_choices(rpe_prompt, key_prefix="feel_inline")

        # 当前待做组（有未填感觉时先不让打下一组）
        if pending_sets and not waiting_rpe:
            focus = pending_sets[0]
            sid = focus["id"]
            weight = float(focus["weight_kg"] or 0)
            reps = int(focus["reps"] or 0)
            later_n = len(pending_sets) - 1
            is_timed = (focus.get("measure") or "") == "seconds"
            qty_label = "秒数" if is_timed else "次数"
            weight_label = "重量 kg（单手/总重见约定）"

            st.caption(
                f"第 {focus['set_index']} 组"
                + (" · 计时" if is_timed else "")
                + (f" · 后面还有 {later_n} 组" if later_n else "")
            )
            with st.form(f"set_form_{sid}", clear_on_submit=False):
                f1, f2 = st.columns(2)
                w_in = f1.number_input(
                    weight_label, min_value=0.0, value=weight, step=1.0, format="%.1f"
                )
                r_in = f2.number_input(qty_label, min_value=0, value=reps, step=1)
                sync_rest = st.checkbox("同步到本动作剩余组", value=True)
                c1, c2 = st.columns([3, 1])
                do_complete = c1.form_submit_button(
                    "完成此组", type="primary", width="stretch"
                )
                do_skip = c2.form_submit_button("跳过", width="stretch")

            if do_complete:
                w_val, r_val = float(w_in), int(r_in)
                repo.update_set(
                    sid,
                    weight_kg=w_val,
                    reps=r_val,
                    measure="seconds" if is_timed else "reps",
                )
                if sync_rest:
                    repo.apply_to_remaining_sets(
                        workout["id"], ex_name, weight_kg=w_val, reps=r_val
                    )
                done_row = repo.complete_set(sid, weight_kg=w_val, reps=r_val)
                st.session_state["rpe_prompt"] = {
                    "set_id": sid,
                    "set_index": focus["set_index"],
                    "exercise_name": ex_name,
                    "weight_kg": w_val,
                    "reps": r_val,
                    "measure": done_row.get("measure"),
                    "display": done_row.get("display"),
                }
                st.session_state["rest_until"] = time.time() + 90
                st.rerun()
            if do_skip:
                repo.delete_set(sid)
                st.toast("已跳过")
                st.rerun()
        elif pending_sets and waiting_rpe:
            st.caption("先选一下刚刚那组的感觉，再继续。")

        a1, a2, a3, a4 = st.columns(4)
        if a1.button("加一组", key=f"ex_add_{ex_key}", width="stretch"):
            repo.add_planned_set(workout["id"], ex_name)
            st.rerun()
        if a2.button(
            "减一组",
            key=f"ex_drop_{ex_key}",
            width="stretch",
            disabled=not pending_sets or waiting_rpe,
        ):
            repo.drop_last_incomplete_set(workout["id"], ex_name)
            st.rerun()
        with a3:
            with st.popover("换动作"):
                new_name = st.text_input("新动作", key=f"swap_name_{ex_key}")
                sync_plan = st.checkbox("同步周计划", value=False, key=f"swap_plan_{ex_key}")
                if st.button("确认", key=f"swap_ok_{ex_key}", type="primary"):
                    if new_name.strip():
                        out = repo.replace_today_exercise(
                            ex_name,
                            new_name.strip(),
                            also_update_plan=sync_plan,
                            target_date=target.isoformat(),
                        )
                        if out.get("ok"):
                            st.toast(f"已换成 {out.get('new_name')}")
                            st.rerun()
                        else:
                            st.error(out.get("error") or "失败")
        with a4:
            with st.popover("更多"):
                if st.button("跳过剩余", key=f"ex_skip_{ex_key}", width="stretch"):
                    n = repo.skip_remaining_sets(workout["id"], ex_name)
                    st.toast(f"已跳过 {n} 组")
                    st.rerun()
                if st.button("删除本动作", key=f"ex_del_{ex_key}", width="stretch"):
                    out = repo.delete_today_exercise(
                        ex_name,
                        include_completed=True,
                        target_date=target.isoformat(),
                    )
                    st.toast(f"已删 {out.get('deleted_sets', 0)} 组")
                    st.rerun()

        if done_sets:
            missing_rpe = [s for s in done_sets if s.get("rpe") is None]
            label = f"已完成 {len(done_sets)} 组"
            if missing_rpe:
                label += f" · {len(missing_rpe)} 组未填感觉"
            with st.expander(label, expanded=bool(missing_rpe and not waiting_rpe)):
                for s in done_sets:
                    sid = s["id"]
                    feel = _feel_label(s.get("rpe"))
                    line = (
                        f"第 {s['set_index']} 组 · "
                        f"{s.get('display') or ((str(s.get('weight_kg') or '-') + ' kg × ' + str(s.get('reps') or '-')))} · {feel}"
                    )
                    d1, d2 = st.columns([4, 1])
                    d1.write(line)
                    if d2.button("撤销", key=f"undo_{sid}"):
                        repo.update_set(sid, completed=False)
                        prompt = st.session_state.get("rpe_prompt") or {}
                        if prompt.get("set_id") == sid:
                            st.session_state.pop("rpe_prompt", None)
                        st.rerun()
                    if s.get("rpe") is None:
                        st.caption("补选这组感觉：")
                        for val, title, desc in FEEL_OPTIONS:
                            if st.button(
                                f"{title}（{desc}）",
                                key=f"feel_fill_{sid}_{int(val * 10)}",
                                width="stretch",
                            ):
                                _save_feel(sid, val, title)

        st.divider()


st.subheader("加动作")
with st.form("add_exercise_planned"):
    name_in = st.text_input("动作名称")
    c1, c2, c3 = st.columns(3)
    sets_n = c1.number_input("组数", min_value=1, value=3, step=1)
    w = c2.number_input("重量 kg", min_value=0.0, value=0.0, step=1.0)
    r = c3.text_input("次数", value="8-12")
    if st.form_submit_button("加入今日", type="primary"):
        if not name_in.strip():
            st.error("请填写动作名称")
        else:
            out = repo.add_today_exercise(
                name_in.strip(),
                sets=int(sets_n),
                reps=r.strip() or "8-12",
                weight_kg=w or None,
                target_date=target.isoformat(),
            )
            if out.get("ok"):
                st.rerun()
            else:
                st.error(out.get("error") or "添加失败")

st.subheader("消耗 / 备注")
burn = workout.get("calories_burned")
can_ai = get_api_key() and not get_api_key().startswith("sk-xxxxx")
b1, b2 = st.columns(2)
with b1:
    if st.button("AI 估算消耗", disabled=not can_ai or done == 0, width="stretch"):
        with st.spinner("估算中…"):
            try:
                result = estimate_workout_calories(target.isoformat(), save=True)
                st.toast(f"约 {result['calories_burned']} kcal")
                st.rerun()
            except MissingAPIKeyError as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    if burn is not None:
        st.caption(f"当前消耗 {float(burn):.0f} kcal")
with b2:
    if st.button("结束剩余组并收工", width="stretch"):
        n = repo.skip_remaining_sets(workout["id"])
        repo.update_workout(workout["id"], status="done")
        st.toast(f"已去掉 {n} 组")
        st.rerun()

notes = st.text_area("训练备注", value=workout.get("notes") or "")
n1, n2 = st.columns(2)
if n1.button("保存备注", width="stretch"):
    repo.update_workout(workout["id"], notes=notes)
    st.toast("已保存")
if n2.button("标记今日完成", type="primary", width="stretch"):
    repo.update_workout(workout["id"], status="done", notes=notes)
    st.rerun()

st.page_link("pages/3_训练计划.py", label="改一周模板", icon="📋")
if st.button("按周计划重置今日（清空本日）"):
    for s in repo.get_sets(workout["id"]):
        repo.conn.execute("DELETE FROM sets WHERE id = ?", (s["id"],))
    repo.conn.commit()
    repo.ensure_today_sets_from_plan(target, force=True)
    st.rerun()
