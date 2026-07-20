"""每日报告 — 晚上生成当日训练+饮食复盘并入库。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from agent.daily_report import generate_daily_report
from agent.llm import MissingAPIKeyError
from bootstrap import get_api_key, get_repo, load_env
from db.schema import init_db
from ui import render_sidebar

st.set_page_config(page_title="每日报告", page_icon="📝", layout="wide")
load_env()
init_db()
repo = get_repo()
render_sidebar()

st.title("每日报告")
st.caption("练完、吃完后来这里生成当日复盘，保存后可随时回看。")

if not get_api_key() or get_api_key().startswith("sk-xxxxx"):
    st.error("请先在「设置」配置 MIMO_API_KEY。")
    st.page_link("pages/6_设置.py", label="去设置", icon="⚙️")
    st.stop()

today = date.today()
# 从历史日历跳转时，强制写入 date_input 的 widget state
jump = st.session_state.pop("daily_report_date", None)
if isinstance(jump, date):
    st.session_state["daily_report_date_input"] = jump
elif "daily_report_date_input" not in st.session_state:
    st.session_state["daily_report_date_input"] = today

target = st.date_input(
    "报告日期",
    max_value=today,
    key="daily_report_date_input",
)
ds = target.isoformat()

snapshot = repo.get_day_snapshot(ds)
w = snapshot["workout"]
n = snapshot["nutrition"]
plan = snapshot.get("plan") or {}

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("训练组数", f"{w.get('completed_sets') or 0}/{w.get('total_sets') or 0}")
burn = w.get("calories_burned")
c2.metric("运动消耗", f"{float(burn):.0f}" if burn is not None else "未估")
c3.metric("摄入热量", f"{(n.get('totals') or {}).get('calories') or 0:.0f}")
c4.metric("蛋白 g", f"{(n.get('totals') or {}).get('protein_g') or 0:.0f}")
c5.metric("餐次", len(n.get("meals") or []))
if w.get("calories_burned_note"):
    st.caption(w["calories_burned_note"])
if plan.get("rest"):
    st.info("这一天计划是休息日。")
elif (w.get("total_sets") or 0) == 0 and not (n.get("meals") or []):
    st.warning("这一天还没有训练打卡或饮食记录，报告会较空，也可以先记再生成。")

existing = repo.get_daily_report(ds)
user_note = st.text_area(
    "今晚想补充一句（可选）",
    value=(existing or {}).get("user_note") or "",
    placeholder="例如：深蹲感觉膝盖有点紧；晚饭多吃了半碗饭",
    height=68,
)

b1, b2 = st.columns([2, 1])
gen_label = "重新生成并保存" if existing else "生成并保存今日报告"
with b1:
    do_gen = st.button(gen_label, type="primary", width="stretch")
with b2:
    st.page_link("pages/2_今日训练.py", label="今日训练", icon="🏋️")

with st.expander("消耗估算选项", expanded=False):
    est_missing = st.checkbox(
        "生成报告前若无消耗则先 AI 估算",
        value=True,
        help="根据画像与已完成组估算运动消耗并写入当日训练",
    )
    if st.button(
        "仅估算消耗",
        width="stretch",
        disabled=int(w.get("completed_sets") or 0) == 0,
    ):
        from agent.calorie_burn import estimate_workout_calories

        with st.spinner("正在估算运动消耗…"):
            try:
                result = estimate_workout_calories(ds, save=True)
            except Exception as exc:  # noqa: BLE001
                st.error(f"估算失败：{exc}")
            else:
                st.toast(f"约 {result['calories_burned']} kcal")
                st.rerun()
    st.page_link("pages/4_饮食管理.py", label="饮食明细", icon="🥗")

if do_gen:
    with st.spinner("正在根据今日训练与饮食写报告…"):
        try:
            result = generate_daily_report(
                ds,
                user_note=user_note,
                save=True,
                estimate_burn_if_missing=est_missing,
            )
        except MissingAPIKeyError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"生成失败：{exc}")
        else:
            st.toast(f"已保存：{result['title']}")
            st.rerun()

existing = repo.get_daily_report(ds)
if existing:
    st.divider()
    with st.expander(
        existing.get("title") or f"{ds} 报告",
        expanded=True,
    ):
        st.caption(
            f"更新于 {existing.get('updated_at') or existing.get('created_at') or '-'}"
        )
        if existing.get("user_note"):
            st.markdown(f"**你的备注：** {existing['user_note']}")
        st.markdown(existing.get("content") or "")
        if st.button("删除这份报告", type="secondary"):
            repo.delete_daily_report(ds)
            st.toast("已删除")
            st.rerun()
else:
    st.info("这一天还没有报告。确认数据后点上方按钮生成。")

with st.expander("最近报告", expanded=False):
    recent = repo.list_daily_reports(limit=14)
    if not recent:
        st.caption("暂无历史报告。")
    else:
        for row in recent:
            col_a, col_b = st.columns([4, 1])
            with col_a:
                st.markdown(f"**{row.get('title') or row['date']}**")
                st.caption((row.get("preview") or "").replace("\n", " ")[:80])
            with col_b:
                if st.button("查看", key=f"open_report_{row['date']}", width="stretch"):
                    st.session_state["daily_report_date"] = date.fromisoformat(
                        row["date"]
                    )
                    st.rerun()
