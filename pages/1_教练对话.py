"""教练对话页 — ChatGPT 式多会话对话。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from agent.coach import stream_coach
from agent.llm import MissingAPIKeyError
from bootstrap import get_api_key, get_repo, load_env
from ui import render_sidebar

st.set_page_config(
    page_title="教练",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed",
)
load_env()
render_sidebar()
repo = get_repo()

st.markdown(
    """
    <style>
    /* 不要压低 padding-top，否则会被 Streamlit 顶栏挡住 */
    .block-container {
        padding-top: 4.75rem !important;
        padding-bottom: 5rem !important;
        max-width: 960px !important;
    }
    header[data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0.92);
    }
    /* 按钮文字完整显示，允许换行 */
    div[data-testid="stButton"] > button {
        white-space: normal !important;
        height: auto !important;
        min-height: 2.5rem;
        line-height: 1.35 !important;
        padding-top: 0.45rem !important;
        padding-bottom: 0.45rem !important;
    }
    div[data-testid="stPopover"] > button {
        white-space: nowrap !important;
        width: 100%;
    }
    div[data-testid="stChatMessage"] p {
        line-height: 1.55;
        overflow-wrap: anywhere;
        word-break: break-word;
    }
    .coach-empty {
        text-align: center;
        padding: 3rem 0.5rem 1.5rem;
        color: #5b6b63;
    }
    .coach-empty h3 {
        color: #1a2421;
        font-weight: 600;
        margin-bottom: 0.35rem;
    }
    .coach-hint {
        color: #7a8a82;
        font-size: 0.92rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if not get_api_key() or get_api_key().startswith("sk-xxxxx"):
    st.error("请先在「设置」配置 MIMO_API_KEY。")
    st.page_link("pages/6_设置.py", label="去设置", icon="⚙️")
    st.stop()


def _active_session_id() -> int:
    sessions = repo.list_chat_sessions()
    if not sessions:
        created = repo.create_chat_session("新对话")
        st.session_state.active_chat_session_id = int(created["id"])
        return int(created["id"])

    current = st.session_state.get("active_chat_session_id")
    ids = {int(s["id"]) for s in sessions}
    if current is None or int(current) not in ids:
        st.session_state.active_chat_session_id = int(sessions[0]["id"])
    return int(st.session_state.active_chat_session_id)


def _log_meal_photo(session_id: int, uploaded, hint: str) -> None:
    from agent.llm import MissingAPIKeyError
    from agent.meal_logger import log_meal_from_image

    with st.spinner("识别餐食中…"):
        try:
            result = log_meal_from_image(
                uploaded.getvalue(),
                filename=getattr(uploaded, "name", None) or "meal.jpg",
                hint=hint,
                target_date=date.today().isoformat(),
            )
        except MissingAPIKeyError as exc:
            st.error(str(exc))
            st.page_link("pages/6_设置.py", label="去配置 MiMo Key", icon="⚙️")
            return
        except Exception as exc:  # noqa: BLE001
            st.error(f"识别失败：{exc}")
            return

    p = result["parsed"]
    user_line = "【拍照记账】上传了餐食照片"
    if hint.strip():
        user_line += f"（{hint.strip()}）"
    reply = (
        f"已记：{p.get('meal_type') or ''} · **{p['name']}**\n"
        f"热量 {p.get('calories') or '-'} kcal · "
        f"蛋白 {p.get('protein_g') or '-'} / "
        f"碳水 {p.get('carb_g') or '-'} / "
        f"脂肪 {p.get('fat_g') or '-'} g"
    )
    if p.get("notes"):
        reply += f"\n_{p['notes']}_"
    rem = (result["day"] or {}).get("remaining") or {}
    extras = []
    if rem.get("calories") is not None:
        extras.append(f"热量剩 {rem['calories']:.0f}")
    if rem.get("protein_g") is not None:
        extras.append(f"蛋白差 {rem['protein_g']:.0f}g")
    if rem.get("carb_g") is not None:
        extras.append(f"碳水差 {rem['carb_g']:.0f}g")
    if rem.get("fat_g") is not None:
        extras.append(f"脂肪差 {rem['fat_g']:.0f}g")
    if extras:
        reply += "\n今日：" + "，".join(extras)
    repo.add_chat_message("user", user_line, session_id=session_id)
    repo.add_chat_message("assistant", reply, session_id=session_id)
    st.toast(f"已记：{p['name']}")
    st.rerun()


session_id = _active_session_id()
sessions = repo.list_chat_sessions()
session_map = {int(s["id"]): s for s in sessions}
cur = session_map.get(session_id) or {}
cur_title = (cur.get("title") or "新对话").strip() or "新对话"
labels = {
    int(s["id"]): ((s.get("title") or f"会话 {s['id']}").strip() or f"会话 {s['id']}")
    for s in sessions
}

# ---------- 顶栏：会话切换（避免窄列裁切） ----------
t1, t2, t3, t4 = st.columns([5.2, 1.2, 1.2, 1.2], gap="small")
with t1:
    selected = st.selectbox(
        "会话",
        options=list(labels.keys()),
        index=list(labels.keys()).index(session_id)
        if session_id in labels
        else 0,
        format_func=lambda i: labels.get(int(i), str(i)),
        label_visibility="collapsed",
    )
    if int(selected) != session_id:
        st.session_state.active_chat_session_id = int(selected)
        st.session_state.pop("pending_chat", None)
        st.rerun()
with t2:
    if st.button("新对话", width="stretch", type="primary"):
        created = repo.create_chat_session("新对话")
        st.session_state.active_chat_session_id = int(created["id"])
        st.session_state.pop("pending_chat", None)
        st.rerun()
with t3:
    with st.popover("附件", use_container_width=True):
        st.markdown("**餐食照片记账**")
        uploaded = st.file_uploader(
            "照片",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=False,
            key="coach_meal_image",
            label_visibility="collapsed",
        )
        hint = st.text_input(
            "补充说明",
            placeholder="可选，如：半份 / 晚餐",
            key="coach_meal_hint",
        )
        if uploaded is not None:
            st.image(uploaded, width=220)
            if st.button("识别并发送", type="primary", width="stretch"):
                _log_meal_photo(session_id, uploaded, hint or "")
with t4:
    with st.popover("更多", use_container_width=True):
        new_title = st.text_input("会话名称", value=cur_title, key="coach_rename")
        if st.button("保存名称", width="stretch"):
            if new_title.strip():
                repo.rename_chat_session(session_id, new_title.strip())
                st.rerun()
        if st.button("清空本对话", width="stretch"):
            repo.clear_chat(session_id)
            st.session_state.pop("pending_chat", None)
            st.rerun()
        if st.button("删除会话", width="stretch"):
            repo.delete_chat_session(session_id)
            st.session_state.pop("active_chat_session_id", None)
            st.session_state.pop("pending_chat", None)
            st.rerun()

nutri = repo.get_nutrition_day()
tot = nutri["totals"]
tgt = nutri["targets"]
diet_bits = [f"今日已记 {len(nutri['meals'])} 餐", f"{tot['calories']:.0f} kcal"]
if tgt.get("calorie_target"):
    diet_bits[-1] = f"{tot['calories']:.0f}/{tgt['calorie_target']:.0f} kcal"
st.caption(" · ".join(diet_bits))

st.divider()

messages = repo.get_chat_messages(limit=200, session_id=session_id)

if not messages:
    st.markdown(
        """
        <div class="coach-empty">
          <h3>有什么可以帮你的？</h3>
          <p class="coach-hint">排训练、改动作、记饮食，直接说就行</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    samples = [
        "根据我的画像生成一周训练计划",
        "今天只有 40 分钟，帮我精简训练",
        "中午吃了鸡胸肉饭，帮我记账",
    ]
    for i, text in enumerate(samples):
        if st.button(text, width="stretch", key=f"tip_{i}"):
            st.session_state["pending_chat"] = text
            st.rerun()
else:
    for msg in messages:
        role = "user" if msg["role"] == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(msg["content"])

pending = st.session_state.pop("pending_chat", None)
prompt = st.chat_input("发给教练…") or pending

if prompt:
    repo.add_chat_message("user", prompt, session_id=session_id)
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        status = st.empty()
        status.caption("思考中…")
        bubble = st.empty()
        assembled: list[str] = []
        reply = ""

        try:
            for piece in stream_coach(prompt, session_id=session_id):
                if isinstance(piece, str) and piece.startswith("\0status:"):
                    status.caption(piece[len("\0status:") :])
                    continue
                assembled.append(piece)
                reply = "".join(assembled)
                bubble.markdown(reply)
            status.empty()
        except MissingAPIKeyError as exc:
            status.empty()
            reply = str(exc)
            bubble.markdown(reply)
        except Exception as exc:  # noqa: BLE001
            status.empty()
            reply = f"调用失败：{exc}"
            bubble.markdown(reply)

    repo.add_chat_message(
        "assistant",
        (reply or "").strip() or "（无回复）",
        session_id=session_id,
    )
    st.rerun()
