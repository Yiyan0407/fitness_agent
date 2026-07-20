"""LangChain tools for the fitness coach agent."""

from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.tools import tool

from bootstrap import get_repo


def _ok(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@tool
def get_profile() -> str:
    """读取用户的个人健身画像（目标、年龄、体重、体脂、活动量、训练时长、饮食偏好、伤病等）。"""
    return _ok(get_repo().get_profile())


@tool
def update_profile(
    goal: Optional[str] = None,
    goal_detail: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    experience: Optional[str] = None,
    days_per_week: Optional[int] = None,
    session_minutes: Optional[int] = None,
    activity_level: Optional[str] = None,
    preferred_split: Optional[str] = None,
    equipment: Optional[str] = None,
    injuries: Optional[str] = None,
    diet_prefs: Optional[str] = None,
    sleep_hours: Optional[float] = None,
    weight_kg: Optional[float] = None,
    target_weight_kg: Optional[float] = None,
    body_fat_pct: Optional[float] = None,
    target_body_fat_pct: Optional[float] = None,
    height_cm: Optional[float] = None,
    calorie_target: Optional[float] = None,
    protein_target_g: Optional[float] = None,
    carb_target_g: Optional[float] = None,
    fat_target_g: Optional[float] = None,
    notes: Optional[str] = None,
) -> str:
    """更新用户画像。age 为年龄；activity_level 如久坐/轻度活动/中度活动/重度活动；
    session_minutes 为单次可练分钟；preferred_split 如全身/推拉腿/上下肢/五分化/随教练；
    diet_prefs 为饮食偏好与忌口；target_body_fat_pct 为目标体脂%。"""
    fields = {
        "goal": goal,
        "goal_detail": goal_detail,
        "gender": gender,
        "age": age,
        "experience": experience,
        "days_per_week": days_per_week,
        "session_minutes": session_minutes,
        "activity_level": activity_level,
        "preferred_split": preferred_split,
        "equipment": equipment,
        "injuries": injuries,
        "diet_prefs": diet_prefs,
        "sleep_hours": sleep_hours,
        "weight_kg": weight_kg,
        "target_weight_kg": target_weight_kg,
        "body_fat_pct": body_fat_pct,
        "target_body_fat_pct": target_body_fat_pct,
        "height_cm": height_cm,
        "calorie_target": calorie_target,
        "protein_target_g": protein_target_g,
        "carb_target_g": carb_target_g,
        "fat_target_g": fat_target_g,
        "notes": notes,
    }
    updated = get_repo().update_profile(**{k: v for k, v in fields.items() if v is not None})
    return _ok({"updated": True, "profile": updated})


@tool
def get_current_plan() -> str:
    """获取当前生效的训练计划（按周一到周日的安排）。"""
    plan = get_repo().get_current_plan()
    if not plan:
        return _ok({"exists": False, "message": "当前没有训练计划，请先用 save_plan 创建。"})
    return _ok({"exists": True, "plan": plan})


@tool
def save_plan(content_json: str, name: str = "当前计划") -> str:
    """保存或替换一周训练计划。

    content_json 必须是 JSON 字符串。每个训练日应包含 4～6 个动作（复合为主 + 孤立辅助），
    不要只写一个动作。格式示例：
    {
      "monday": {"name": "胸肩推", "rest": false, "exercises": [
        {"name": "杠铃卧推", "sets": 4, "reps": "6-8", "weight_kg": 60, "notes": ""},
        {"name": "上斜卧推", "sets": 3, "reps": "8-10", "weight_kg": 20, "notes": ""},
        {"name": "绳索夹胸", "sets": 3, "reps": "12-15", "weight_kg": 15, "notes": ""},
        {"name": "哑铃推肩", "sets": 3, "reps": "8-12", "weight_kg": 14, "notes": ""},
        {"name": "绳索下压", "sets": 3, "reps": "10-12", "weight_kg": 25, "notes": ""}
      ]},
      "tuesday": {"name": "休息", "rest": true, "exercises": []},
      ...
      "sunday": {"name": "休息", "rest": true, "exercises": []}
    }
    键名使用 monday..sunday。动作名称优先使用 list_exercises 返回的名称。
    """
    try:
        content = json.loads(content_json)
    except json.JSONDecodeError as exc:
        return _ok({"ok": False, "error": f"JSON 解析失败: {exc}"})
    plan = get_repo().save_plan(content, name=name)
    # 计划更新后，若今日尚未开始打卡，自动按新计划刷新今日动作
    get_repo().sync_today_from_plan_if_idle()
    return _ok({"ok": True, "plan": plan})


@tool
def get_today_workout(target_date: Optional[str] = None) -> str:
    """获取今日（或指定日期 YYYY-MM-DD）的训练安排与已记录组数。"""
    return _ok(get_repo().get_today_workout(target_date))


@tool
def log_set(
    exercise_name: str,
    weight_kg: Optional[float] = None,
    reps: Optional[int] = None,
    rpe: Optional[float] = None,
    set_index: Optional[int] = None,
    notes: str = "",
    target_date: Optional[str] = None,
) -> str:
    """记录一组训练（动作名、重量kg、次数、RPE 可选）。"""
    row = get_repo().log_set(
        exercise_name=exercise_name,
        weight_kg=weight_kg,
        reps=reps,
        rpe=rpe,
        set_index=set_index,
        completed=True,
        notes=notes,
        target_date=target_date,
    )
    return _ok({"ok": True, "set": row})


@tool
def get_recent_history(days: int = 14) -> str:
    """获取近 N 天的训练历史摘要，用于判断是否该加重量或减量。"""
    days = max(1, min(int(days), 60))
    return _ok(get_repo().get_recent_history(days))


@tool
def list_exercises(query: str = "", muscle: str = "", equipment: str = "") -> str:
    """从本地动作库检索动作。

    equipment 可填动作标签（杠铃/哑铃/自重/绳索/器械…），也可填画像场景
    （健身房/家庭哑铃杠铃/仅自重/弹力带为主/综合）；含示范图 URL。
    """
    items = get_repo().list_exercises(
        query=query, muscle=muscle, equipment=equipment, limit=80
    )
    slim = [
        {
            "name": e.get("name"),
            "name_en": e.get("name_en"),
            "muscle": e.get("muscle"),
            "equipment": e.get("equipment"),
            "tips": (e.get("tips") or "")[:80],
            "image_url": e.get("image_url") or "",
        }
        for e in items
    ]
    return _ok({"returned": len(slim), "exercises": slim})


@tool
def get_nutrition_day(target_date: Optional[str] = None) -> str:
    """获取某日饮食记录与热量/蛋白总量，以及与目标的差值。默认今天。"""
    return _ok(get_repo().get_nutrition_day(target_date))


@tool
def get_recent_nutrition(days: int = 7) -> str:
    """获取近 N 天饮食汇总（热量、蛋白等），用于评估饮食执行情况。"""
    return _ok(get_repo().get_recent_nutrition(days))


@tool
def log_meal(
    name: str,
    meal_type: str = "正餐",
    calories: Optional[float] = None,
    protein_g: Optional[float] = None,
    carb_g: Optional[float] = None,
    fat_g: Optional[float] = None,
    notes: str = "",
    target_date: Optional[str] = None,
) -> str:
    """记录一餐。meal_type 可用：早餐/午餐/晚餐/加餐/蛋白粉/其他。热量和宏量营养可估算后写入。"""
    if not name.strip():
        return _ok({"ok": False, "error": "菜名/食物名不能为空"})
    row = get_repo().log_meal(
        name=name,
        meal_type=meal_type,
        calories=calories,
        protein_g=protein_g,
        carb_g=carb_g,
        fat_g=fat_g,
        notes=notes,
        target_date=target_date,
    )
    summary = get_repo().get_nutrition_day(target_date)
    return _ok({"ok": True, "meal": row, "day": summary})


@tool
def delete_meal(meal_id: int) -> str:
    """删除一条饮食记录。"""
    ok = get_repo().delete_meal(int(meal_id))
    return _ok({"ok": ok, "meal_id": meal_id})


ALL_TOOLS = [
    get_profile,
    update_profile,
    get_current_plan,
    save_plan,
    get_today_workout,
    log_set,
    get_recent_history,
    list_exercises,
    get_nutrition_day,
    get_recent_nutrition,
    log_meal,
    delete_meal,
]
