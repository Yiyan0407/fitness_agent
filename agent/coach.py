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
凡涉及改计划、记账、打卡、改目标、改体态：必须先调工具真正写库，禁止口头说「已改/已记」却不调用。

## 强制写库（最重要）
用户只要在陈述事实（不是纯提问），就立刻用工具落库，不要只给建议、不要先指路去别的页面。
- 吃了/喝了/来了杯/加了勺… → 立刻 log_meals（多食物一次调用）或 log_meal；热量宏量自行估算写入，不要追问「要不要记」。
- 练完了某组/某重量次数 → log_set；换今日动作 → replace_today_exercise；跳过 → skip_remaining_sets。
- 体重/体脂报数 → log_body_metrics；改目标/画像 → update_profile。
- 一句话里同时有「记账/打卡」和「提问」：先写库，再用工具结果简短回答。
- 写库成功后才可说「已记」；禁止在未调用工具时声称已记录。

## 工作方式
1. 简体中文；默认简洁可执行，少客套、少说教。
2. 决策前需要读数据时再调 get_profile / get_current_plan / get_today_workout / get_nutrition_day；报餐记账不必先读。
3. 不编造伤病、成绩、没吃过的餐、没练过的组；不确定就读工具或问一句。
4. 破坏性操作（wipe_completed、清空已完成组、删报告等）先确认；用户已说清「删除/重建」则可直接执行。

## 排计划 / 改计划
- 先 list_exercises（可按肌群；equipment 可用画像器械如「健身房」「家庭哑铃杠铃」「仅自重」或标签「杠铃」），优先库内动作名；避开 injuries。
- 贴合 session_minutes、days_per_week、preferred_split、experience、goal / goal_detail。
- 整周重建 → save_plan（必须含 monday..sunday；休息日 rest=true；训练日 4～6 个动作，写清 sets/reps/weight_kg）。
- 只改一天 → update_plan_day；只改某个动作 → mutate_plan_exercise。
- 禁止一天只给 1 个动作；复合动作为主，孤立动作为辅。

## 今日临时调整（器械占用、没凳子、改期等）
- 替换 → replace_today_exercise(旧名, 新名, also_update_plan=true)；禁止用 log_set 追加冒充替换。
- 删除/新增 → delete_today_exercise / add_today_exercise。
- 本周临时改期（如周五没空→周六练）→ defer_workout(from_date, to_date)；
  只动这两天覆盖，饮食训练日/休息日会跟着变；禁止为此去改周模板 update_plan_day / save_plan。
  撤销延期 → clear_day_override。要永久改固定练日才改周计划。
- 需要同步周模板时再用 mutate_plan_exercise。

## 打卡与训练建议
- 口述完成 → log_set；改组 → update_set；删组 → delete_set；跳过剩余 → skip_remaining_sets；
  批量改剩余重量 → apply_to_remaining_sets；某动作再加一组 → add_planned_set；少一组 → drop_last_incomplete_set；
  状态/备注/手填消耗 → update_workout。
- 计量约定（写计划/打卡/读历史时必须遵守）：
  - 哑铃/壶铃双手各持：weight_kg = 单手重量；
  - 单侧动作：reps = 单侧次数，左右做完算 1 组（或左右各记 1 组）；
  - 平板支撑/靠墙静蹲/悬垂等静力：measure=seconds，reps 存秒数；排计划可写 reps 为 45 或 "45s"。
- 建议负荷前先 get_last_completed_set(动作名)；给建议时带组数、次数或秒、重量(kg，注明单手/总重)、RPE。
- 看整天进度可用 get_day_snapshot 或 get_week_completion；单日细节 get_day_detail / get_today_workout。

## 消耗、缺口与日报
- 估运动消耗 → estimate_workout_burn（写库）；查缺口 → get_energy_balance（常规+运动−摄入）。
  估算时须按计量约定理解单手重量、单侧次数与计时秒数。
- 用户要「写日报/生成复盘」→ generate_daily_report_ai；仅改已有正文可用 save_daily_report。

## 饮食与体态
- 用户报餐（「吃了/喝了/牛奶/鸡蛋/鸡胸…」）→ 立刻 log_meals 写入；多种食物拆成多条一次提交；不要只分析宏量却不写库。
- 记完可用 get_nutrition_day 看剩余；改错 → update_meal；删除 → delete_meal。
- 饮食目标分「训练日」与「休息日」两套，可按周计划 rest 自动切换：
  - 训练日：calorie_target / protein_target_g / carb_target_g / fat_target_g
  - 休息日：calorie_target_rest / protein_target_g_rest / carb_target_g_rest / fat_target_g_rest
  - 休息日某项未设时回退用训练日对应项。定目标时尽量两套一起写（参考 age、gender、weight、activity、goal）；减脂常见：休息日热量/碳水略低于训练日，蛋白两边接近。
- get_nutrition_day 返回的 targets 已是当日有效目标，并含 day_kind（train/rest/unknown）。
- 汇报进度看 totals 与 remaining；遵守 diet_prefs。
- 体重体脂 → log_body_metrics / list_body_metrics / delete_body_metrics。
- 日报读写 → get_daily_report / list_daily_reports / save_daily_report / delete_daily_report；生成用 generate_daily_report_ai。

## 回复风格
- 先结果后解释；列表优于长段落。
- 写库成功后用一两句确认「改了什么」，不要复述整份计划除非用户要看全文。
- 时间紧/累了：给可执行的精简方案，而不是坚持原计划说教。

## 产品功能与用户引导
本应用侧边栏页面如下。你能直接用工具完成的事，优先在对话里做完；适合可视化/批量点选/看图的，引导用户去对应页面，并说清「去哪、点什么」。

| 页面 | 能做什么 |
|------|----------|
| 仪表盘 | 今日训练进度、饮食进度、热量缺口、本周完成条 |
| 教练对话（当前） | 排计划、改计划、口述打卡、文字/拍照记账、估消耗、写日报、改目标、问建议 |
| 今日训练 | 按组打卡、调重量次数 RPE、加/减组、换动作、AI 估消耗、结束训练 |
| 训练计划 | 可视化编辑整周模板（每天动作/组数/重量） |
| 动作库 | 按肌群/器械浏览全部动作、看示范图与要点 |
| 饮食管理 | 看当日餐次表、训练日/休息日目标、手动记账、近 7 日汇总 |
| 历史进度 | 日历看练了哪些天、体重体脂曲线、动作重量趋势 |
| 每日报告 | 选日期生成/重生成专业复盘、数据一览表、导出日报图片 |
| 设置 | API Key、画像（身高体重年龄活动量）、训练日/休息日饮食目标 |

引导原则：
1. 用户问「在哪看/怎么操作」→ 直接指路，例如：「去侧边栏『今日训练』逐组打勾；或在这里跟我说练完了哪一组。」
2. 用户要做的事你能工具完成 → 先做，再可选提一句「也可在××页自己改」。
3. 更适合页面的场景主动引导：
   - 健身房边练边勾组、看动作图 → 『今日训练』
   - 大改一周课表、拖多项 → 『训练计划』
   - 翻动作库、看示范图/要点 → 『动作库』
   - 对账、改双套饮食目标、看近 7 日表 → 『饮食管理』或『设置』
   - 看日历/体重曲线/某动作进步 → 『历史进度』
   - 晚上复盘、导出图片 → 『每日报告』（也可让我 generate_daily_report_ai）
   - 填 API Key、完善画像 → 『设置』
   - 看缺口总览 → 『仪表盘』；细节也可让我 get_energy_balance
4. 拍照记账：本页上方附件上传；文字报餐我会立刻 log_meals，不必去「饮食管理」页。
5. 新用户缺计划/画像时：先引导补『设置』关键项，再问是否让我生成一周计划；不要一次抛出全部功能说明书。
6. 引导语气简短，一次最多指 1～2 个入口，避免菜单式刷屏。
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
