"""Shared conventions for how sets are measured and displayed."""

from __future__ import annotations

from typing import Any

# Shown in UI, coach prompt, and calorie estimation.
SET_CONVENTIONS_TEXT = """【组数计量约定】
1. 哑铃/壶铃等双手各持一只器械：weight_kg = 单手重量（两手各 10kg 记 10，不是 20）。
2. 单侧动作（保加利亚蹲、弓步、单臂划船等）：次数 = 单侧次数；左右各做完算 1 组（不要把两侧相加写成 20）。若用户明确要分侧打卡，可左右各记 1 组。
3. 静力/计时动作（平板支撑、靠墙静蹲、悬垂、空心支撑、鸟狗静撑等）：measure=seconds，reps 字段存秒数；展示为「N 秒」而非「N 次」。估算消耗时按时长与紧张程度计，不要按次数计。
4. 普通双侧杠铃/器械推拉蹲：weight_kg = 杠上或器械总负荷；reps = 次数。
"""

_TIMED_STRONG = (
    "平板支撑",
    "侧平板",
    "靠墙静蹲",
    "悬垂静挂",
    "空心支撑",
    "dead hang",
    "wall sit",
    "hollow body hold",
    "hollow hold",
    "plank",
)


def infer_measure(
    exercise_name: str,
    *,
    explicit: str | None = None,
    reps_hint: Any = None,
) -> str:
    """Return 'reps' or 'seconds'."""
    if explicit in ("seconds", "reps", "sec", "s", "秒"):
        if explicit in ("seconds", "sec", "s", "秒"):
            return "seconds"
        return "reps"

    hint = str(reps_hint or "").strip().lower()
    if hint.endswith("s") or hint.endswith("秒") or "秒" in hint:
        return "seconds"

    name = (exercise_name or "").strip().lower()
    name_raw = exercise_name or ""
    # counted variations of timed-looking names
    if any(x in name_raw for x in ("升降", "拍肩", "收膝", "登山", "卷腹", "起坐")):
        return "reps"
    for kw in _TIMED_STRONG:
        if kw.lower() in name or kw in name_raw:
            return "seconds"
    for kw in ("静蹲", "静挂", "静撑", "wall sit", "dead hang", "hollow hold"):
        if kw in name or kw in name_raw:
            return "seconds"
    return "reps"


def parse_reps_value(reps: Any) -> int | None:
    """Parse plan reps which may be 8, '6-8', '45s', '45秒'."""
    if reps is None:
        return None
    if isinstance(reps, (int, float)):
        return int(reps)
    text = str(reps).strip().lower().replace("秒", "s")
    if text.endswith("s") and text[:-1].strip().isdigit():
        return int(text[:-1].strip())
    if text.isdigit():
        return int(text)
    if "-" in text:
        left = text.split("-", 1)[0].strip()
        if left.isdigit():
            return int(left)
    return None


def annotate_set(row: dict[str, Any]) -> dict[str, Any]:
    """Add measure / display helpers onto a set dict (non-destructive copy)."""
    out = dict(row)
    name = str(out.get("exercise_name") or "")
    stored = str(out.get("measure") or "").strip().lower()
    name_guess = infer_measure(name, explicit=None, reps_hint=out.get("reps"))
    if stored in ("seconds", "sec", "s", "秒") or name_guess == "seconds":
        measure = "seconds"
    else:
        measure = "reps"
    out["measure"] = measure
    qty = out.get("reps")
    if measure == "seconds":
        out["qty_unit"] = "秒"
        out["qty_label"] = f"{qty} 秒" if qty is not None else "- 秒"
        out["display"] = (
            f"{out.get('weight_kg') or '-'} kg · {out['qty_label']}"
            if out.get("weight_kg")
            else out["qty_label"]
        )
    else:
        out["qty_unit"] = "次"
        out["qty_label"] = f"{qty} 次" if qty is not None else "- 次"
        w = out.get("weight_kg")
        out["display"] = f"{w if w is not None else '-'} kg × {qty if qty is not None else '-'}"
    out["weight_means"] = "单手重量（双手各持器械时）"
    return out


def annotate_sets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [annotate_set(r) for r in rows]
