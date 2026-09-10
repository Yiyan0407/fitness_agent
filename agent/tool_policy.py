"""Intent-based coach tool mounting: CORE always, extra bundles on demand."""

from __future__ import annotations

import re
from typing import Any, Iterable

from agent.tools import (
    add_planned_set,
    add_today_exercise,
    apply_to_remaining_sets,
    clear_day_override,
    defer_workout,
    delete_body_metrics,
    delete_daily_report,
    delete_meal,
    delete_set,
    delete_today_exercise,
    drop_last_incomplete_set,
    estimate_workout_burn,
    generate_daily_report_ai,
    get_current_plan,
    get_daily_report,
    get_day_snapshot,
    get_energy_balance,
    get_exercise_progress,
    get_last_completed_set,
    get_nutrition_day,
    get_profile,
    get_recent_history,
    get_recent_nutrition,
    get_today_workout,
    get_week_completion,
    list_body_metrics,
    list_daily_reports,
    list_exercises,
    log_body_metrics,
    log_meals,
    log_set,
    mutate_plan_exercise,
    replace_today_exercise,
    resync_today_from_plan,
    save_daily_report,
    save_plan,
    skip_remaining_sets,
    update_meal,
    update_plan_day,
    update_profile,
    update_set,
    update_workout,
)

CORE_TOOLS = [
    get_profile,
    update_profile,
    get_current_plan,
    get_today_workout,
    get_day_snapshot,
    get_nutrition_day,
    list_exercises,
    get_last_completed_set,
    get_energy_balance,
    log_meals,
    log_set,
    log_body_metrics,
]

BUNDLES: dict[str, list] = {
    "plan": [
        save_plan,
        update_plan_day,
        mutate_plan_exercise,
        defer_workout,
        clear_day_override,
        resync_today_from_plan,
    ],
    "workout": [
        update_set,
        delete_set,
        add_today_exercise,
        delete_today_exercise,
        replace_today_exercise,
        skip_remaining_sets,
        apply_to_remaining_sets,
        add_planned_set,
        drop_last_incomplete_set,
        update_workout,
    ],
    "nutrition": [
        update_meal,
        delete_meal,
        get_recent_nutrition,
    ],
    "body": [
        list_body_metrics,
        delete_body_metrics,
    ],
    "history": [
        get_recent_history,
        get_exercise_progress,
        get_week_completion,
    ],
    "reports": [
        get_daily_report,
        list_daily_reports,
        save_daily_report,
        generate_daily_report_ai,
        delete_daily_report,
        estimate_workout_burn,
    ],
}

_BUNDLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "plan": (
        "排计划",
        "排课",
        "周计划",
        "课表",
        "训练计划",
        "改计划",
        "重建计划",
        "生成计划",
        "一周计划",
        "整周",
        "分化",
        "推拉腿",
        "上下肢",
        "改期",
        "挪到",
        "延期",
        "推迟",
        "撤销延期",
        "覆盖",
        "周模板",
        "同步计划",
        "按计划重建",
        "休息日改",
        "训练日改成",
        "save_plan",
        "update_plan",
    ),
    "workout": (
        "打卡",
        "练完",
        "完成一组",
        "完成了",
        "换动作",
        "换成",
        "替换动作",
        "跳过",
        "剩余组",
        "加一组",
        "再加一组",
        "少一组",
        "删一组",
        "改组",
        "改重量",
        "调重量",
        "rpe",
        "RPE",
        "器械占用",
        "没凳子",
        "结束训练",
        "今日训练",
        "加动作",
        "删动作",
        "未完成组",
        "apply_to_remaining",
        "replace_today",
    ),
    "nutrition": (
        "改餐",
        "改饮食",
        "删餐",
        "删除饮食",
        "记错",
        "记错了",
        "近几天吃",
        "近7日",
        "近七日",
        "饮食汇总",
        "饮食记录",
        "改热量",
        "改蛋白",
        "update_meal",
        "delete_meal",
    ),
    "body": (
        "体重记录",
        "体脂记录",
        "体重曲线",
        "体脂曲线",
        "历史体重",
        "历史体脂",
        "删除体重",
        "删除体脂",
        "体态记录",
        "list_body",
    ),
    "history": (
        "进度",
        "历史",
        "完成度",
        "进步",
        "上周练",
        "近几天练",
        "重量趋势",
        "动作进步",
        "练了哪些",
        "完成情况",
        "get_recent_history",
        "get_week_completion",
    ),
    "reports": (
        "日报",
        "复盘",
        "生成报告",
        "写报告",
        "估消耗",
        "运动消耗",
        "热量消耗",
        "estimate_workout",
        "generate_daily",
        "每日报告",
    ),
}

_BROAD_KEYWORDS = (
    "全部",
    "所有功能",
    "随便看看",
    "今天怎么样",
    "今天如何",
    "帮我看看所有",
    "全面看看",
    "总览一下",
)

_FOLLOW_UP_RE = re.compile(
    r"^(?:"
    r"[\d.\s,，kgKG公斤组次秒rpeRPE]+"
    r"|改成.+"
    r"|换成.+"
    r"|改成\s*\d+"
    r"|好的|嗯|对|是的|继续|就这个|这个"
    r")$",
)

_HISTORY_LOOKBACK = 6


def _dedupe_tools(tools: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for item in tools:
        name = getattr(item, "name", None) or id(item)
        if name in seen:
            continue
        seen.add(str(name))
        out.append(item)
    return out


COACH_TOOLS = _dedupe_tools(
    [*CORE_TOOLS, *[t for bundle in BUNDLES.values() for t in bundle]]
)


def _match_bundles(text: str) -> set[str]:
    if not text:
        return set()
    lowered = text.lower()
    hits: set[str] = set()
    for name, keywords in _BUNDLE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in lowered:
                hits.add(name)
                break
    return hits


def _is_broad(text: str) -> bool:
    return any(kw in (text or "") for kw in _BROAD_KEYWORDS)


def _is_short_followup(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    if len(stripped) > 24:
        return False
    if _FOLLOW_UP_RE.match(stripped):
        return True
    if re.fullmatch(r"[\d.\s]+(?:kg|公斤|组|次|秒)?", stripped, flags=re.I):
        return True
    return False


def _history_texts(history_rows: list[dict] | None, *, limit: int) -> list[str]:
    rows = history_rows or []
    texts: list[str] = []
    for row in reversed(rows):
        if row.get("role") != "user":
            continue
        content = str(row.get("content") or "").strip()
        if content:
            texts.append(content)
        if len(texts) >= limit:
            break
    return texts


def select_coach_tools(
    user_input: str,
    history_rows: list[dict] | None = None,
) -> list[Any]:
    """Pick CORE plus intent bundles; fall back to full COACH_TOOLS when very broad."""
    current = (user_input or "").strip()
    hits = _match_bundles(current)

    if _is_broad(current):
        return list(COACH_TOOLS)

    if not hits and _is_short_followup(current):
        for past in _history_texts(history_rows, limit=_HISTORY_LOOKBACK):
            hits |= _match_bundles(past)
            if hits:
                break

    selected = list(CORE_TOOLS)
    for name in ("plan", "workout", "nutrition", "body", "history", "reports"):
        if name in hits:
            selected.extend(BUNDLES[name])
    return _dedupe_tools(selected)
