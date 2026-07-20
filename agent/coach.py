"""Fitness coach agent orchestration using LangChain create_agent."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.tools import ALL_TOOLS

SYSTEM_PROMPT = """你是用户的私人健身教练 Agent，只服务这一位用户。

规则：
1. 始终用简体中文回复，简洁可执行。
2. 做决策前先调用工具读取画像、当前计划、今日安排或近期历史，不要凭空假设。
   制定计划/饮食目标时重点参考 gender、age、goal、goal_detail、target_weight_kg、weight_kg、
   body_fat_pct、target_body_fat_pct、activity_level、session_minutes、preferred_split、diet_prefs、sleep_hours。
3. 制定或修改计划时：先 list_exercises 查阅动作库（可按肌群筛选；equipment 可传画像里的器械条件如「家庭哑铃杠铃」「仅自重」或具体标签如「杠铃」），优先使用库中动作名；考虑伤病禁忌。
   单次训练量需贴合 session_minutes；分化优先遵循 preferred_split。
4. 计划用 save_plan 写入，content_json 必须包含 monday 到 sunday 共 7 天；休息日设 rest=true。
   每个训练日安排 4～6 个动作（例如练胸：杠铃卧推 + 上斜/飞鸟类 + 肩/三头辅助），每个动作写清 sets/reps/weight_kg；禁止一天只给 1 个动作。
5. 给出组数、次数区间、建议重量（kg）和 RPE 参考；说明热身与安全要点。
6. 用户说今天累/时间紧时，调用 get_today_workout 后给出精简替代方案，必要时 save_plan 或口头调整。
7. 用户口述完成组数时，用 log_set 记录。
8. 饮食相关：先 get_nutrition_day / get_profile 看目标和今日摄入；可按目标用 update_profile 写入 calorie_target、protein_target_g 等；
   估算全天热量时参考 age、gender、weight_kg、height_cm、activity_level、days_per_week；遵守 diet_prefs 忌口；
   用户说吃了/喝了什么时，必须用 log_meal 记账（合理估算热量和宏量，不要只口头回复）；给一日三餐建议时要可执行、贴合目标。
9. 不要编造用户没说过的伤病史或成绩；信息不足就先问一句关键问题。
"""


def build_agent(*, streaming: bool = False):
    """Build a LangChain agent graph (create_agent)."""
    return create_agent(
        model=get_llm(streaming=streaming),
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
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
