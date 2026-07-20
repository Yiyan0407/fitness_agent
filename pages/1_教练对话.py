"""教练对话页 — 训练 + 饮食记账（文字 / 拍照）。"""

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
st.caption("训练计划、改练、饮食记账：直接说，或上传餐食照片")

if not get_api_key() or get_api_key().startswith("sk-xxxxx"):
    st.error("请先在「设置」配置 MIMO_API_KEY。")
    st.page_link("pages/6_设置.py", label="去设置", icon="⚙️")
    st.stop()

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

QUICK_PROMPTS = [
    "根据我的画像生成一周训练计划，并保存",
    "今天只有40分钟，帮我精简今日训练",
    "根据我的画像设定每日热量和蛋白目标，并写入",
    "喝了一瓶可乐，帮我记到饮食里",
    "中午吃了鸡胸肉饭，帮我记账",
    "看看我今天饮食还差多少蛋白，推荐加餐",
]

messages = repo.get_chat_messages(limit=80)
if not messages:
    st.info(
        "还没有对话。可以说训练需求，或「喝了一瓶可乐」让我记账；也可展开下方上传餐食照片。"
    )

with st.expander("快捷提示", expanded=not messages):
    cols = st.columns(2)
    for i, text in enumerate(QUICK_PROMPTS):
        with cols[i % 2]:
            if st.button(text, key=f"quick_{i}", width="stretch"):
                st.session_state["pending_chat"] = text
                st.rerun()

with st.expander("拍照记账（豆包看图）", expanded=False):
    st.caption("默认从相册选图；需要时再点按钮打开摄像头。")
    if "coach_use_camera" not in st.session_state:
        st.session_state["coach_use_camera"] = False

    camera_img = None
    uploaded = None
    if st.session_state["coach_use_camera"]:
        camera_img = st.camera_input("对准餐食拍照", key="coach_meal_camera")
        if st.button("返回相册选择", key="coach_meal_back_album"):
            st.session_state["coach_use_camera"] = False
            st.rerun()
    else:
        uploaded = st.file_uploader(
            "从相册选择餐食照片",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=False,
            key="coach_meal_image",
        )
        if st.button("打开摄像头拍照", key="coach_meal_open_camera"):
            st.session_state["coach_use_camera"] = True
            st.rerun()

    meal_image = camera_img or uploaded
    hint = st.text_input(
        "补充说明（可选）",
        placeholder="半份 / 晚餐 / 加了米饭",
        key="coach_meal_hint",
    )
    if meal_image is not None:
        st.image(meal_image, width=280)
    if st.button("识别并记入对话", type="primary", key="coach_meal_submit"):
        if meal_image is None:
            st.error("请先选择或拍摄图片")
        else:
            from agent.doubao import MissingDoubaoKeyError
            from agent.meal_logger import log_meal_from_image

            with st.spinner("豆包看图识别中…"):
                try:
                    result = log_meal_from_image(
                        meal_image.getvalue(),
                        filename=getattr(meal_image, "name", None) or "camera.jpg",
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
                    st.session_state["coach_use_camera"] = False
                    st.toast(f"已记：{p['name']}")
                    st.rerun()

_, top_r = st.columns([3, 1])
with top_r:
    if st.button("清空对话", width="stretch"):
        repo.clear_chat()
        st.session_state.pop("pending_chat", None)
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
        # write_stream 内更新 empty 往往不刷新；用 status + 手动拼字
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
