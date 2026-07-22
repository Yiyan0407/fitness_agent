"""Daily energy balance: baseline (NEAT) + workout burn − intake."""

from __future__ import annotations

from typing import Any

# 画像「日常活动量」已是非训练日口径，再叠加上运动消耗即可
_ACTIVITY_FACTOR = {
    "久坐": 1.2,
    "轻度活动": 1.375,
    "中度活动": 1.55,
    "重度活动": 1.725,
    # 兼容旧文案
    "久坐少动": 1.2,
    "轻度": 1.375,
    "中度": 1.55,
    "重度": 1.725,
    "高度活动": 1.725,
}


def estimate_bmr(profile: dict[str, Any] | None) -> float | None:
    """Mifflin–St Jeor BMR (kcal/day). Needs weight, height, age."""
    p = profile or {}
    try:
        weight = float(p.get("weight_kg") or 0)
        height = float(p.get("height_cm") or 0)
        age = float(p.get("age") or 0)
    except (TypeError, ValueError):
        return None
    if weight <= 0 or height <= 0 or age <= 0:
        return None

    gender = str(p.get("gender") or "").strip().lower()
    base = 10.0 * weight + 6.25 * height - 5.0 * age
    if gender in {"男", "male", "m", "man"}:
        return base + 5.0
    if gender in {"女", "female", "f", "woman"}:
        return base - 161.0
    # 未填性别：取男女均值，避免整块算不出
    return base - 78.0


def estimate_baseline_burn(profile: dict[str, Any] | None) -> float | None:
    """日常常规消耗 ≈ BMR × 活动系数（不含专项训练）。"""
    bmr = estimate_bmr(profile)
    if bmr is None:
        return None
    raw = str((profile or {}).get("activity_level") or "轻度活动").strip()
    factor = _ACTIVITY_FACTOR.get(raw, 1.375)
    return round(bmr * factor)


def energy_balance(
    *,
    profile: dict[str, Any] | None,
    intake_kcal: float | None,
    exercise_kcal: float | None = None,
) -> dict[str, Any]:
    """缺口 = 常规消耗 + 运动消耗 − 摄入（正数=热量缺口，负数=盈余）。"""
    baseline = estimate_baseline_burn(profile)
    bmr = estimate_bmr(profile)
    try:
        intake = float(intake_kcal or 0)
    except (TypeError, ValueError):
        intake = 0.0
    try:
        exercise = float(exercise_kcal) if exercise_kcal is not None else None
    except (TypeError, ValueError):
        exercise = None

    missing: list[str] = []
    p = profile or {}
    if not p.get("weight_kg"):
        missing.append("体重")
    if not p.get("height_cm"):
        missing.append("身高")
    if not p.get("age"):
        missing.append("年龄")

    exercise_val = 0.0 if exercise is None else max(0.0, exercise)
    if baseline is None:
        return {
            "ok": False,
            "bmr": None,
            "baseline": None,
            "exercise": exercise,
            "exercise_used": exercise_val,
            "intake": intake,
            "total_out": None,
            "deficit": None,
            "missing": missing,
            "activity_level": p.get("activity_level") or "轻度活动",
        }

    total_out = baseline + exercise_val
    deficit = total_out - intake
    return {
        "ok": True,
        "bmr": round(bmr) if bmr is not None else None,
        "baseline": round(baseline),
        "exercise": exercise,
        "exercise_used": round(exercise_val),
        "intake": round(intake),
        "total_out": round(total_out),
        "deficit": round(deficit),
        "missing": missing,
        "activity_level": p.get("activity_level") or "轻度活动",
    }


def deficit_delta_text(balance: dict[str, Any]) -> str | None:
    """Streamlit metric delta: 缺口为正、盈余为负。"""
    if not balance.get("ok") or balance.get("deficit") is None:
        return None
    d = float(balance["deficit"])
    if d >= 0:
        return f"缺口 {d:.0f}"
    return f"盈余 {-d:.0f}"
