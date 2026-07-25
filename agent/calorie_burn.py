"""Estimate workout calorie burn from profile + completed sets."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.meal_logger import _extract_json, _message_text
from bootstrap import get_repo

BURN_SYSTEM = """你是运动消耗估算助手。根据画像与当日已完成训练组，估算本次训练相对安静的额外消耗（kcal）。

只输出一个 JSON 对象（不要 markdown）：
{
  "calories_burned": 整数,
  "duration_min_estimate": 整数,
  "method": "一句话说明估算依据（含体重/强度/组数等）",
  "breakdown": [
    {"exercise": "动作名", "kcal": 整数}
  ]
}

规则：
1. 不要计入全天 BMR；EPOC 可轻度计入。
2. 参考 weight_kg、gender、age、body_fat_pct、height_cm、experience、session_minutes，以及重量×次数/秒与 RPE。
3. 必须遵守输入中的 set_conventions（计量约定）：
   - 哑铃等双手各持：weight_kg 是单手重量；
   - 单侧动作：reps 是单侧次数，左右做完通常记为 1 组；
   - measure=seconds 或 qty_unit=秒：reps 表示秒数，按静力时长估算，不要当成次数。
4. 力量训练粗算：体重越大、组数/负荷越高、RPE 越高，消耗越高；有氧动作可略高于纯力量；计时支撑按时长与紧张度。
5. 休息日或无完成组 → 接近 0；不确定也给合理整数。
6. breakdown 只列主要动作，各项之和应接近 calories_burned。
"""


def estimate_workout_calories(
    target_date: str | None = None,
    *,
    save: bool = True,
) -> dict[str, Any]:
    """Ask LLM to estimate burn; optionally write to workouts row."""
    from db.set_conventions import SET_CONVENTIONS_TEXT

    repo = get_repo()
    snapshot = repo.get_day_snapshot(target_date)
    ds = snapshot["date"]
    # only create workout row when we need to save burn onto it
    workout = repo.get_or_create_workout(date.fromisoformat(ds))

    llm = get_llm(temperature=0.2, thinking=False)
    payload = {
        "date": ds,
        "set_conventions": snapshot.get("set_conventions") or SET_CONVENTIONS_TEXT,
        "profile": snapshot.get("profile"),
        "plan": snapshot.get("plan"),
        "workout": snapshot.get("workout"),
    }
    resp = llm.invoke(
        [
            SystemMessage(content=BURN_SYSTEM),
            HumanMessage(
                content="请估算当日运动消耗：\n"
                + json.dumps(payload, ensure_ascii=False, default=str)
            ),
        ]
    )
    data = _extract_json(_message_text(resp))
    try:
        calories = int(round(float(data.get("calories_burned") or 0)))
    except (TypeError, ValueError):
        calories = 0
    calories = max(0, calories)

    duration = data.get("duration_min_estimate")
    try:
        duration_i = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_i = None

    method = str(data.get("method") or "AI 根据画像与完成组估算")[:300]
    breakdown = data.get("breakdown") if isinstance(data.get("breakdown"), list) else []
    note_parts = [method]
    if duration_i:
        note_parts.append(f"约 {duration_i} 分钟")
    if breakdown:
        bits = []
        for item in breakdown[:8]:
            if not isinstance(item, dict):
                continue
            name = item.get("exercise") or "?"
            kcal = item.get("kcal")
            bits.append(f"{name}:{kcal}" if kcal is not None else str(name))
        if bits:
            note_parts.append("分项 " + "、".join(bits))
    note = "；".join(note_parts)[:500]

    result = {
        "date": ds,
        "calories_burned": calories,
        "duration_min_estimate": duration_i,
        "method": method,
        "breakdown": breakdown,
        "calories_burned_note": note,
    }
    if save:
        updated = repo.update_workout(
            int(workout["id"]),
            calories_burned=float(calories),
            calories_burned_note=note,
        )
        result["workout"] = updated
    return result
