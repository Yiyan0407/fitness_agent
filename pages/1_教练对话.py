"""教练对话页 — 训练 + 饮食记账（文字 / 传图）。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from agent.coach import stream_coach
from agent.llm import MissingAPIKeyError
from bootstrap import get_api_key, get_repo, load_env
from db.schema import init_db
from ui import render_sidebar

st.set_page_config(page_title="教练对话", page_icon="🗣️", layout="wide")
load_env()
init_db()
repo = get_repo()
render_sidebar()

st.title("教练对话")
st.caption("训练计划、改练、饮食记账：直接说；手机上传图片时可直接拍照")

if not get_api_key() or get_api_key().startswith("sk-xxxxx"):
    st.error("请先在「设置」配置 MIMO_API_KEY。")
    st.page_link("pages/6_设置.py", label="去设置", icon="⚙️")
    st.stop()

messages = repo.get_chat_messages(limit=80)

# 顶部：饮食摘要 + 传图记账（避免被长对话顶到很下面）
sum_l, sum_r = st.columns([3, 1])
with sum_l:
    with st.expander("今日饮食摘要", expanded=False):
        nutri = repo.get_nutrition_day()
        tot, tgt = nutri["totals"], nutri["targets"]
        n1, n2, n3 = st.columns(3)
        cal_label = f"{tot['calories']:.0f}"
        if tgt.get("calorie_target"):
            cal_label += f" / {tgt['calorie_target']:.0f}"
        pro_label = f"{tot['protein_g']:.0f}"
        if tgt.get("protein_target_g"):
            pro_label += f" / {tgt['protein_target_g']:.0f}"
        n1.metric("今日热量", cal_label)
        n2.metric("今日蛋白", pro_label)
        n3.metric("已记餐次", len(nutri["meals"]))
        st.page_link("pages/4_饮食管理.py", label="查看饮食明细", icon="🥗")
with sum_r:
    if st.button("清空对话", width="stretch"):
        repo.clear_chat()
        st.session_state.pop("pending_chat", None)
        st.rerun()

with st.expander("上传餐食照片记账", expanded=False):
    st.caption("选图即可；手机上点上传后可选「拍照」或「相册」，无需单独摄像头入口。")
    uploaded = st.file_uploader(
        "餐食照片",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=False,
        key="coach_meal_image",
        label_visibility="collapsed",
    )
    hint = st.text_input(
        "补充说明（可选）",
        placeholder="半份 / 晚餐 / 加了米饭",
        key="coach_meal_hint",
    )
    if uploaded is not None:
        st.image(uploaded, width=280)
    if st.button("识别并记入对话", type="primary", key="coach_meal_submit", width="stretch"):
        if uploaded is None:
            st.error("请先选择或拍摄图片")
        else:
            from agent.doubao import MissingDoubaoKeyError
            from agent.meal_logger import log_meal_from_image

            with st.spinner("豆包看图识别中…"):
                try:
                    result = log_meal_from_image(
                        uploaded.getvalue(),
                        filename=getattr(uploaded, "name", None) or "meal.jpg",
                        hint=hint,
                        target_date=date.today().isoformat(),
                    )
                except MissingDoubaoKeyError as exc:
                    st.error(str(exc))
                    st.page_link("pages/6_设置.py", label="去配置豆包 Key", icon="⚙️")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"看图记账失败：{exc}")
                else:
                    p = result["parsed"]
                    user_line = "【拍照记账】上传了餐食照片"
                    if hint.strip():
                        user_line += f"（{hint.strip()}）"
                    reply = (
                        f"已根据照片记账：\n"
                        f"- {p['meal_type']} · **{p['name']}**\n"
                        f"- 热量约 **{p.get('calories') or '-'}** kcal\n"
                        f"- 蛋白 **{p.get('protein_g') or '-'}** g / "
                        f"碳水 **{p.get('carb_g') or '-'}** g / "
                        f"脂肪 **{p.get('fat_g') or '-'}** g\n"
                    )
                    if p.get("notes"):
                        reply += f"\n_{p['notes']}_"
                    rem = (result["day"] or {}).get("remaining") or {}
                    extras = []
                    if rem.get("calories") is not None:
                        extras.append(f"热量还剩约 **{rem['calories']:.0f}** kcal")
                    if rem.get("protein_g") is not None:
                        extras.append(f"蛋白还差约 **{rem['protein_g']:.0f}** g")
                    if extras:
                        reply += "\n\n今日：" + "，".join(extras)
                    repo.add_chat_message("user", user_line)
                    repo.add_chat_message("assistant", reply)
                    st.toast(f"已记：{p['name']}")
                    st.rerun()

QUICK_PROMPTS = [
    "根据我的画像生成一周训练计划，并保存",
    "今天只有40分钟，帮我精简今日训练",
    "根据我的画像设定每日热量和蛋白目标，并写入",
    "喝了一瓶可乐，帮我记到饮食里",
    "中午吃了鸡胸肉饭，帮我记账",
    "看看我今天饮食还差多少蛋白，推荐加餐",
]

if not messages:
    st.info(
        "还没有对话。可以说训练需求，或「喝了一瓶可乐」让我记账；"
        "也可展开上方「上传餐食照片记账」。"
    )

with st.expander("快捷提示", expanded=not messages):
    cols = st.columns(2)
    for i, text in enumerate(QUICK_PROMPTS):
        with cols[i % 2]:
            if st.button(text, key=f"quick_{i}", width="stretch"):
                st.session_state["pending_chat"] = text
                st.rerun()

for msg in messages:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg["content"])

pending = st.session_state.pop("pending_chat", None)
prompt = (
    st.chat_input("训练或饮食都可以，例如：喝了一瓶可乐 / 帮我加卧推重量")
    or pending
)

if prompt:
    repo.add_chat_message("user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    history = repo.get_chat_messages(limit=40)
    prior = history[:-1] if history else []

    with st.chat_message("assistant"):
        progress = st.status("教练处理中…", expanded=True)
        bubble = st.empty()
        assembled: list[str] = []
        reply = ""

        try:
            for piece in stream_coach(prompt, prior):
                if isinstance(piece, str) and piece.startswith("\0status:"):
                    progress.update(label=piece[len("\0status:") :], state="running")
                    continue
                assembled.append(piece)
                reply = "".join(assembled)
                bubble.markdown(reply)
            progress.update(label="完成", state="complete")
        except MissingAPIKeyError as exc:
            reply = str(exc)
            bubble.markdown(reply)
            progress.update(label="未配置 Key", state="error")
        except Exception as exc:  # noqa: BLE001
            reply = f"调用失败：{exc}"
            bubble.markdown(reply)
            progress.update(label="调用失败", state="error")

    repo.add_chat_message("assistant", (reply or "").strip() or "（无回复）")
    st.rerun()
