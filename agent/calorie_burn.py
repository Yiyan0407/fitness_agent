"""Estimate workout calorie burn from profile + completed sets."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.meal_logger import _extract_json, _message_text
from bootstrap import get_repo

BURN_SYSTEM = """你是运动消耗估算助手。根据用户画像与当日已完成训练组，估算本次训练额外消耗的热量（kcal）。

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
1. calories_burned 是相对安静状态的额外消耗（EPOC 可轻度计入），不要把全天 BMR 算进去。
2. 优先参考 weight_kg、gender、body_fat_pct、height_cm、experience，以及完成组的重量×次数与 RPE。
3. 力量训练通常按组数/动作强度估算；休息日或无完成组则接近 0。
4. 不确定也给出合理整数，不要留空。
5. breakdown 可只列主要动作，kcal 之和应接近 totals。
"""


def estimate_workout_calories(
    target_date: str | None = None,
    *,
    save: bool = True,
) -> dict[str, Any]:
    """Ask LLM to estimate burn; optionally write to workouts row."""
    repo = get_repo()
    snapshot = repo.get_day_snapshot(target_date)
    ds = snapshot["date"]
    # only create workout row when we need to save burn onto it
    workout = repo.get_or_create_workout(date.fromisoformat(ds))

    llm = get_llm(temperature=0.2)
    resp = llm.invoke(
        [
            SystemMessage(content=BURN_SYSTEM),
            HumanMessage(
                content=(
                    "请估算当日运动消耗：\n"
                    + json.dumps(
                        {
                            "date": ds,
                            "profile": snapshot.get("profile"),
                            "plan": snapshot.get("plan"),
                            "workout": snapshot.get("workout"),
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                )
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
