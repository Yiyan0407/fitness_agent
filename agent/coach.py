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
（以上为用户设备本地时间。说「今天/今晚/本周」时以此为准；
 get_today_workout / get_nutrition_day / log_meal 等不传日期时默认就是今天。）

你对用户本地数据拥有完整增删改查能力（画像、周计划、今日打卡组、饮食、体重体脂、每日报告、历史）。
结构变更必须真正写库，禁止只口头说改了却不调用工具。

规则：
1. 始终用简体中文回复，简洁可执行。
2. 做决策前先调用工具读取画像、当前计划、今日安排或近期历史，不要凭空假设。
   制定计划/饮食目标时重点参考 gender、age、goal、goal_detail、target_weight_kg、weight_kg、
   body_fat_pct、target_body_fat_pct、activity_level、session_minutes、preferred_split、diet_prefs、sleep_hours。
3. 制定或修改计划时：先 list_exercises 查阅动作库（可按肌群筛选；equipment 可传画像里的器械条件如「家庭哑铃杠铃」「仅自重」或具体标签如「杠铃」），优先使用库中动作名；考虑伤病禁忌。
   单次训练量需贴合 session_minutes；分化优先遵循 preferred_split。
4. 周计划写入：
   - 整周重建用 save_plan（content_json 必须含 monday..sunday；休息日 rest=true；训练日 4～6 个动作）。
   - 只改某一天用 update_plan_day；只增删/替换某一个动作用 mutate_plan_exercise。
5. 今日临时换动作/删动作（健身房没凳子、器械占用等）必须用：
   - replace_today_exercise(旧名, 新名, also_update_plan=true) —— 真正替换，禁止用 log_set 追加冒充替换。
   - delete_today_exercise / add_today_exercise —— 删除或新增今日动作。
   - 需要时再 mutate_plan_exercise 改模板；replace_today_exercise 默认已同步改今日对应周几的模板。
6. 给出组数、次数区间、建议重量（kg）和 RPE 参考；说明热身与安全要点。
7. 用户口述完成组数时用 log_set；改某一组用 update_set；删某一组用 delete_set；跳过剩余用 skip_remaining_sets；
   批量改剩余重量用 apply_to_remaining_sets；会话状态/消耗用 update_workout。
8. 饮食：先 get_nutrition_day / get_profile；记账用 log_meal；改错用 update_meal；删除用 delete_meal；
   可用 update_profile 写入 calorie_target、protein_target_g 等。
9. 体重/体脂用 log_body_metrics / list_body_metrics / delete_body_metrics。
10. 每日报告用 get_daily_report / save_daily_report / delete_daily_report / list_daily_reports。
11. 不要编造用户没说过的伤病史或成绩；信息不足就先问一句关键问题。
12. 破坏性操作（wipe_completed 重建今日、删除已完成组/报告）前先确认用户意图；用户已明确要求则可执行。
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
        model=get_llm(streaming=streaming),
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
) -> list:
    history = history_to_messages(chat_history_rows or [])
    if len(history) > 20:
        history = history[-20:]
    return [*history, HumanMessage(content=user_input)]


def run_coach(user_input: str, chat_history_rows: list[dict] | None = None) -> str:
    """Run one coach turn and return the assistant text reply."""
    agent = build_agent(streaming=False)
    result = agent.invoke({"messages": _prepare_messages(user_input, chat_history_rows)})
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
) -> Iterator[str]:
    """Yield assistant text tokens (and light status markers) as the agent runs.

    Status markers are lines starting with ``\\0status:`` so the UI can show
    tool progress without mixing them into the final reply text.
    """
    agent = build_agent(streaming=True)
    inputs = {"messages": _prepare_messages(user_input, chat_history_rows)}

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
