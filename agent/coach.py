"""Fitness coach agent orchestration using LangChain create_agent."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.tools import ALL_TOOLS

_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_WEEKDAY_KEYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

SYSTEM_PROMPT_TEMPLATE = """你是用户的私人健身教练 Agent，只服务这一位用户。

【当前时间】{now_text}
（本地时间。说「今天/今晚/本周」以此为准；get_today_workout / get_nutrition_day / log_meal 等不传日期时默认今天。）

你对本地数据有完整读写能力（画像、周计划、今日打卡、饮食、体态、日报、历史）。
凡涉及改计划、记账、改目标、改体态：必须先调工具真正写库，禁止口头说「已改」却不调用。

## 工作方式
1. 简体中文；默认简洁可执行，少客套、少说教。
2. 决策前先读再答：优先 get_profile / get_current_plan / get_today_workout / get_nutrition_day；缺关键信息只问 1 个最关键问题。
3. 用户一句话里若同时有「记账/打卡」和「提问」：先完成写入，再简短回答。
4. 不编造伤病、成绩、没吃过的餐、没练过的组；不确定就读工具或问一句。
5. 破坏性操作（wipe_completed、清空已完成组、删报告等）先确认；用户已说清「删除/重建」则可直接执行。

## 排计划 / 改计划
- 先 list_exercises（可按肌群；equipment 可用画像器械如「健身房」「家庭哑铃杠铃」「仅自重」或标签「杠铃」），优先库内动作名；避开 injuries。
- 贴合 session_minutes、days_per_week、preferred_split、experience、goal / goal_detail。
- 整周重建 → save_plan（必须含 monday..sunday；休息日 rest=true；训练日 4～6 个动作，写清 sets/reps/weight_kg）。
- 只改一天 → update_plan_day；只改某个动作 → mutate_plan_exercise。
- 禁止一天只给 1 个动作；复合动作为主，孤立动作为辅。

## 今日临时调整（器械占用、没凳子等）
- 替换 → replace_today_exercise(旧名, 新名, also_update_plan=true)；禁止用 log_set 追加冒充替换。
- 删除/新增 → delete_today_exercise / add_today_exercise。
- 需要同步周模板时再用 mutate_plan_exercise。

## 打卡与训练建议
- 口述完成 → log_set；改组 → update_set；删组 → delete_set；跳过剩余 → skip_remaining_sets；
  批量改剩余重量 → apply_to_remaining_sets；状态/备注/消耗 → update_workout。
- 给建议时带组数、次数区间、重量(kg)、RPE 参考，并点出热身与安全要点（尤其伤病相关）。

## 饮食与体态
- 先 get_nutrition_day / get_profile；记账 → log_meal；改错 → update_meal；删除 → delete_meal。
- 定目标可写 calorie_target / protein_target_g / carb_target_g / fat_target_g（参考 age、gender、weight_kg、height_cm、activity_level、goal）。
- 汇报进度同时看热量/蛋白/碳水/脂肪的 totals 与 remaining；遵守 diet_prefs。
- 体重体脂 → log_body_metrics / list_body_metrics / delete_body_metrics。
- 日报 → get_daily_report / save_daily_report / delete_daily_report / list_daily_reports。

## 回复风格
- 先结果后解释；列表优于长段落。
- 写库成功后用一两句确认「改了什么」，不要复述整份计划除非用户要看全文。
- 时间紧/累了：给可执行的精简方案，而不是坚持原计划说教。
"""


def _now_context() -> str:
    now = datetime.now().astimezone()
    tz = now.tzname() or "local"
    wd = now.weekday()
    return (
        f"{now.strftime('%Y-%m-%d %H:%M')} {_WEEKDAY_CN[wd]} "
        f"（ISO 星期键: {_WEEKDAY_KEYS[wd]}，时区: {tz}）"
    )


def build_system_prompt() -> str:
    """Build system prompt with fresh local datetime each turn."""
    return SYSTEM_PROMPT_TEMPLATE.format(now_text=_now_context())


def build_agent(*, streaming: bool = False):
    """Build a LangChain agent graph (create_agent)."""
    return create_agent(
        model=get_llm(streaming=streaming, thinking=False),
        tools=ALL_TOOLS,
        system_prompt=build_system_prompt(),
        name="fitness_coach",
    )


def history_to_messages(rows: list[dict]) -> list:
    messages = []
    for row in rows:
        role = row.get("role")
        content = row.get("content") or ""
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "system":
            messages.append(SystemMessage(content=content))
    return messages


def _message_text(message) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
            else:
                parts.append(str(block))
        return "\n".join(parts).strip()
    return str(content).strip()


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _prepare_messages(
    user_input: str,
    chat_history_rows: list[dict] | None = None,
    *,
    summary: str = "",
) -> list:
    history = history_to_messages(chat_history_rows or [])
    # Hard safety net if compression did not run / failed.
    if len(history) > 20:
        history = history[-20:]
    prepared: list = []
    summary = (summary or "").strip()
    if summary:
        prepared.append(
            SystemMessage(content=f"【先前对话摘要】\n{summary}")
        )
    prepared.extend(history)
    prepared.append(HumanMessage(content=user_input))
    return prepared


def _load_session_context(session_id: int | None) -> tuple[str, list[dict]]:
    """Compress if needed, then return summary + raw history rows for the model."""
    if session_id is None:
        return "", []
    from agent.chat_compress import build_model_history, ensure_context_budget
    from bootstrap import get_repo

    ensure_context_budget(int(session_id))
    repo = get_repo()
    session = repo.get_chat_session(int(session_id)) or {}
    all_messages = repo.get_all_chat_messages(int(session_id))
    # Exclude the latest user message if it was already persisted before streaming;
    # callers pass prior history separately. Prefer DB truth after compress.
    summary, recent = build_model_history(session, all_messages)
    return summary, recent


def _ensure_user_bound() -> None:
    """Bind username into ContextVar so tool threads can call get_repo()."""
    from bootstrap import get_current_username

    if not get_current_username():
        raise RuntimeError("未登录，无法访问用户数据")


def run_coach(
    user_input: str,
    chat_history_rows: list[dict] | None = None,
    *,
    session_id: int | None = None,
) -> str:
    """Run one coach turn and return the assistant text reply."""
    _ensure_user_bound()
    summary = ""
    history = chat_history_rows
    if session_id is not None:
        summary, recent = _load_session_context(session_id)
        # Drop trailing duplicate of current user turn if already saved.
        if recent and recent[-1].get("role") == "user" and (recent[-1].get("content") or "") == user_input:
            history = recent[:-1]
        else:
            history = recent
    agent = build_agent(streaming=False)
    result = agent.invoke(
        {"messages": _prepare_messages(user_input, history, summary=summary)}
    )
    messages = result.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                text = _message_text(msg)
                if text:
                    return text
    if messages:
        return _message_text(messages[-1])
    return ""


def stream_coach(
    user_input: str,
    chat_history_rows: list[dict] | None = None,
    *,
    session_id: int | None = None,
) -> Iterator[str]:
    """Yield assistant text tokens (and light status markers) as the agent runs.

    Status markers are lines starting with ``\\0status:`` so the UI can show
    tool progress without mixing them into the final reply text.
    """
    _ensure_user_bound()
    summary = ""
    history = chat_history_rows
    if session_id is not None:
        yield "\0status:整理对话上下文…"
        summary, recent = _load_session_context(session_id)
        if recent and recent[-1].get("role") == "user" and (recent[-1].get("content") or "") == user_input:
            history = recent[:-1]
        else:
            history = recent

    agent = build_agent(streaming=True)
    inputs = {"messages": _prepare_messages(user_input, history, summary=summary)}

    seen_tool_names: set[str] = set()

    # updates: tool / model step progress; messages: token chunks
    for mode, data in agent.stream(
        inputs,
        stream_mode=["messages", "updates"],
    ):
        if mode == "updates" and isinstance(data, dict):
            if "tools" in data:
                names = ", ".join(sorted(seen_tool_names)) if seen_tool_names else "工具"
                yield f"\0status:正在执行：{names}"
            elif "model" in data:
                msgs = (data.get("model") or {}).get("messages") or []
                if msgs:
                    last = msgs[-1]
                    tool_calls = getattr(last, "tool_calls", None) or []
                    if tool_calls:
                        names = []
                        for tc in tool_calls:
                            name = (
                                tc.get("name", "?")
                                if isinstance(tc, dict)
                                else getattr(tc, "name", "?")
                            )
                            names.append(name)
                            seen_tool_names.add(name)
                        yield f"\0status:准备调用：{', '.join(names)}"
                    else:
                        yield "\0status:正在生成回复…"
            continue

        if mode != "messages":
            continue

        # data is (chunk, metadata)
        if not isinstance(data, tuple) or len(data) < 2:
            continue
        chunk, metadata = data[0], data[1]
        node = (metadata or {}).get("langgraph_node")
        if node and node != "model":
            continue
        if not isinstance(chunk, (AIMessageChunk, AIMessage)):
            continue

        # early signal while tool-call args are still streaming
        tool_chunks = getattr(chunk, "tool_call_chunks", None) or []
        if tool_chunks:
            for tc in tool_chunks:
                name = None
                if isinstance(tc, dict):
                    name = tc.get("name")
                else:
                    name = getattr(tc, "name", None)
                if name and name not in seen_tool_names:
                    seen_tool_names.add(name)
                    yield f"\0status:准备调用：{name}"

        text = _chunk_text(chunk)
        if tool_chunks and not text:
            continue
        if text:
            yield text
