"""LangChain tools for the fitness coach agent — full CRUD over user data."""

from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.tools import tool

from bootstrap import get_repo


def _ok(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _parse_json_obj(raw: str, *, label: str = "JSON") -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} 必须是对象")
    return data


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


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
    calorie_target_rest: Optional[float] = None,
    protein_target_g_rest: Optional[float] = None,
    carb_target_g_rest: Optional[float] = None,
    fat_target_g_rest: Optional[float] = None,
    notes: Optional[str] = None,
) -> str:
    """更新用户画像。饮食目标分两套：
    calorie/protein/carb/fat_target(_g) = 训练日目标；
    同名字段加 _rest = 休息日目标（未设时休息日回退用训练日目标）。
    activity_level 如久坐/轻度活动/中度活动/重度活动；
    session_minutes 为单次可练分钟；preferred_split 如全身/推拉腿/上下肢/五分化/随教练。"""
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
        "calorie_target_rest": calorie_target_rest,
        "protein_target_g_rest": protein_target_g_rest,
        "carb_target_g_rest": carb_target_g_rest,
        "fat_target_g_rest": fat_target_g_rest,
        "notes": notes,
    }
    updated = get_repo().update_profile(**{k: v for k, v in fields.items() if v is not None})
    return _ok({"updated": True, "profile": updated})


# ---------------------------------------------------------------------------
# Weekly plan template
# ---------------------------------------------------------------------------


@tool
def get_current_plan() -> str:
    """获取当前生效的训练计划（按周一到周日的安排）。"""
    plan = get_repo().get_current_plan()
    if not plan:
        return _ok({"exists": False, "message": "当前没有训练计划，请先用 save_plan 创建。"})
    return _ok({"exists": True, "plan": plan})


@tool
def save_plan(content_json: str, name: str = "当前计划") -> str:
    """保存或替换一周训练计划（整周覆盖）。

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
    若只需改某一天/某一个动作，优先用 update_plan_day 或 mutate_plan_exercise。
    """
    try:
        content = json.loads(content_json)
    except json.JSONDecodeError as exc:
        return _ok({"ok": False, "error": f"JSON 解析失败: {exc}"})
    plan = get_repo().save_plan(content, name=name)
    get_repo().sync_today_from_plan_if_idle()
    return _ok({"ok": True, "plan": plan})


@tool
def update_plan_day(weekday: str, day_json: str, sync_today: bool = True) -> str:
    """只更新周计划中某一天（不全量重写一周）。

    weekday: monday..sunday 或 周一..周日 / 今天。
    day_json 示例：{"name":"胸肩推","rest":false,"exercises":[{"name":"杠铃卧推","sets":3,"reps":"8-10","weight_kg":30}]}
    sync_today=true 时：若今日尚未开始打卡，会按新模板刷新今日组数。
    """
    try:
        day = _parse_json_obj(day_json, label="day_json")
        plan = get_repo().update_plan_day(weekday, day, sync_today=sync_today)
        return _ok({"ok": True, "plan": plan})
    except (ValueError, json.JSONDecodeError) as exc:
        return _ok({"ok": False, "error": str(exc)})


@tool
def mutate_plan_exercise(
    weekday: str,
    action: str,
    exercise_name: Optional[str] = None,
    new_exercise_json: Optional[str] = None,
    sync_today: bool = True,
) -> str:
    """在周计划某一天里增删改单个动作（模板层）。

    action: add / remove / replace
    - add: 需要 new_exercise_json，如 {"name":"上斜卧推","sets":3,"reps":"10-12","weight_kg":40}
    - remove: 需要 exercise_name
    - replace: 需要 exercise_name + new_exercise_json（用新动作替换旧动作）
    weekday 可用「今天」。换器械/换动作优先用本工具（改模板）+ replace_today_exercise（改今日）。
    """
    try:
        new_ex = None
        if new_exercise_json:
            new_ex = _parse_json_obj(new_exercise_json, label="new_exercise_json")
            if new_ex.get("name"):
                new_ex["name"] = get_repo().resolve_exercise_name(str(new_ex["name"]))
        result = get_repo().mutate_plan_exercise(
            weekday,
            action=action,
            exercise_name=exercise_name,
            new_exercise=new_ex,
            sync_today=sync_today,
        )
        return _ok(result)
    except (ValueError, json.JSONDecodeError) as exc:
        return _ok({"ok": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Today workout / sets
# ---------------------------------------------------------------------------


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
    measure: Optional[str] = None,
) -> str:
    """用户口述完成一组时必须调用。不要只口头确认却不写库。

    计量：哑铃 weight_kg=单手；单侧 reps=单侧次数（左右做完通常 1 组）；
    平板/静蹲等静力传 measure='seconds'，reps 为秒数。
    注意：本工具只追加打卡，不会删除旧动作。换动作请用 replace_today_exercise。
    """
    name = get_repo().resolve_exercise_name(exercise_name)
    row = get_repo().log_set(
        exercise_name=name,
        weight_kg=weight_kg,
        reps=reps,
        rpe=rpe,
        set_index=set_index,
        completed=True,
        notes=notes,
        target_date=target_date,
        measure=measure,
    )
    return _ok({"ok": True, "set": row})


@tool
def update_set(
    set_id: int,
    exercise_name: Optional[str] = None,
    set_index: Optional[int] = None,
    weight_kg: Optional[float] = None,
    reps: Optional[int] = None,
    rpe: Optional[float] = None,
    completed: Optional[bool] = None,
    notes: Optional[str] = None,
) -> str:
    """按 set_id 修改某一组（重量/次数/RPE/是否完成/动作名等）。"""
    fields: dict[str, Any] = {}
    if exercise_name is not None:
        fields["exercise_name"] = get_repo().resolve_exercise_name(exercise_name)
    if set_index is not None:
        fields["set_index"] = set_index
    if weight_kg is not None:
        fields["weight_kg"] = weight_kg
    if reps is not None:
        fields["reps"] = reps
    if rpe is not None:
        fields["rpe"] = rpe
    if completed is not None:
        fields["completed"] = completed
    if notes is not None:
        fields["notes"] = notes
    row = get_repo().update_set(int(set_id), **fields)
    return _ok({"ok": True, "set": row})


@tool
def delete_set(set_id: int) -> str:
    """按 set_id 删除某一组打卡记录。"""
    get_repo().delete_set(int(set_id))
    return _ok({"ok": True, "set_id": set_id})


@tool
def add_today_exercise(
    exercise_name: str,
    sets: int = 3,
    reps: str = "8-12",
    weight_kg: Optional[float] = None,
    notes: str = "",
    target_date: Optional[str] = None,
    also_update_plan: bool = False,
) -> str:
    """在今日打卡列表中新增一个动作（生成未完成的计划组）。

    also_update_plan=true 时同时写入周计划模板对应星期。
    """
    result = get_repo().add_today_exercise(
        exercise_name,
        sets=sets,
        reps=reps,
        weight_kg=weight_kg,
        notes=notes,
        target_date=target_date,
        also_update_plan=also_update_plan,
    )
    return _ok(result)


@tool
def delete_today_exercise(
    exercise_name: str,
    include_completed: bool = True,
    target_date: Optional[str] = None,
    also_update_plan: bool = False,
) -> str:
    """从今日打卡列表删除某个动作的全部组。

    include_completed=false 时只删未完成组（等同跳过剩余）。
    also_update_plan=true 时同时从周计划模板对应星期移除。
    """
    result = get_repo().delete_today_exercise(
        exercise_name,
        include_completed=include_completed,
        target_date=target_date,
        also_update_plan=also_update_plan,
    )
    return _ok(result)


@tool
def replace_today_exercise(
    old_name: str,
    new_name: str,
    weight_kg: Optional[float] = None,
    reps: Optional[int] = None,
    sets: Optional[int] = None,
    notes: Optional[str] = None,
    target_date: Optional[str] = None,
    also_update_plan: bool = True,
) -> str:
    """把今日某个动作替换成另一个（真正替换，不是追加）。

    用户说「把上斜哑铃卧推换成上斜杠铃卧推」时必须用本工具。
    默认 also_update_plan=true，同时改周计划模板，避免今日与计划不一致。
    动作名会尽量映射到动作库标准名（如上斜杠铃卧推→上斜卧推）。
    """
    result = get_repo().replace_today_exercise(
        old_name,
        new_name,
        weight_kg=weight_kg,
        reps=reps,
        sets=sets,
        notes=notes,
        target_date=target_date,
        also_update_plan=also_update_plan,
    )
    return _ok(result)


@tool
def skip_remaining_sets(
    exercise_name: Optional[str] = None,
    target_date: Optional[str] = None,
) -> str:
    """跳过/删除未完成组。不传 exercise_name 则跳过今日全部剩余组。"""
    workout = get_repo().get_today_workout(target_date)["workout"]
    n = get_repo().skip_remaining_sets(workout["id"], exercise_name)
    return _ok({"ok": True, "deleted_incomplete_sets": n})


@tool
def apply_to_remaining_sets(
    exercise_name: str,
    weight_kg: Optional[float] = None,
    reps: Optional[int] = None,
    weight_delta: Optional[float] = None,
    reps_delta: Optional[int] = None,
    target_date: Optional[str] = None,
) -> str:
    """批量调整某动作今日剩余未完成组的重量/次数。
    weight_delta 如 -2.5 表示减 2.5kg；reps_delta 如 -1 表示次数减 1。
    """
    workout = get_repo().get_today_workout(target_date)["workout"]
    n = get_repo().apply_to_remaining_sets(
        workout["id"],
        exercise_name,
        weight_kg=weight_kg,
        reps=reps,
        weight_delta=weight_delta,
        reps_delta=reps_delta,
    )
    return _ok({"ok": True, "updated_sets": n})


@tool
def update_workout(
    status: Optional[str] = None,
    notes: Optional[str] = None,
    calories_burned: Optional[float] = None,
    calories_burned_note: Optional[str] = None,
    clear_calories_burned: bool = False,
    target_date: Optional[str] = None,
) -> str:
    """更新某日训练会话状态/备注/消耗热量。status: planned / in_progress / done。"""
    workout = get_repo().get_today_workout(target_date)["workout"]
    row = get_repo().update_workout(
        workout["id"],
        status=status,
        notes=notes,
        calories_burned=calories_burned,
        calories_burned_note=calories_burned_note,
        clear_calories_burned=clear_calories_burned,
    )
    return _ok({"ok": True, "workout": row})


@tool
def resync_today_from_plan(
    target_date: Optional[str] = None,
    wipe_completed: bool = False,
) -> str:
    """按周计划模板重建今日组数。

    wipe_completed=false（默认）：若已有完成组则拒绝，避免误删打卡。
    wipe_completed=true：清空今日全部组（含已完成）后按模板重建——需用户明确要求。
    """
    return _ok(get_repo().resync_today_from_plan(target_date, wipe_completed=wipe_completed))


@tool
def defer_workout(
    from_date: str,
    to_date: str,
    note: str = "",
) -> str:
    """本周临时把某天的训练挪到另一天，不改周计划模板。

    典型：「周五太忙，挪到周六」→ from_date=周五, to_date=周六。
    日期可用 YYYY-MM-DD / 今天 / 明天 / 周一..周日 / monday..sunday（星期名按本周该日）。
    效果：源日变休息（饮食按休息日），目标日出现原课表（饮食按训练日）；下周模板仍不变。
    目标日若已有完成组会拒绝。要永久改排期请用 update_plan_day / save_plan，不要用本工具。
    """
    try:
        result = get_repo().defer_workout(from_date, to_date, note=note or "")
        return _ok(result)
    except ValueError as exc:
        return _ok({"ok": False, "error": str(exc)})


@tool
def clear_day_override(
    target_date: str,
    clear_pair: bool = True,
) -> str:
    """撤销某日的临时课表覆盖（含 defer_workout 产生的延期）。

    默认 clear_pair=true：若该日是延期对的一端，源日与目标日一起恢复周模板。
    """
    try:
        result = get_repo().clear_day_override(
            target_date, clear_pair=clear_pair, resync=True
        )
        return _ok(result)
    except ValueError as exc:
        return _ok({"ok": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# History / progress
# ---------------------------------------------------------------------------


@tool
def get_recent_history(days: int = 14) -> str:
    """获取近 N 天的训练历史摘要，用于判断是否该加重量或减量。"""
    days = max(1, min(int(days), 60))
    return _ok(get_repo().get_recent_history(days))


@tool
def get_exercise_progress(exercise_name: Optional[str] = None, days: int = 60) -> str:
    """查看某动作（或不限动作）近 N 天完成组的重量/次数进度。"""
    days = max(1, min(int(days), 180))
    name = get_repo().resolve_exercise_name(exercise_name) if exercise_name else None
    return _ok(get_repo().get_exercise_progress(name, days=days))


@tool
def get_day_detail(target_date: Optional[str] = None) -> str:
    """只读查看某日训练详情（不自动生成计划组）。默认今天。"""
    return _ok(get_repo().get_day_detail(target_date))


# ---------------------------------------------------------------------------
# Exercise library (read-only)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Nutrition / meals
# ---------------------------------------------------------------------------


@tool
def get_nutrition_day(target_date: Optional[str] = None) -> str:
    """获取某日饮食记录与热量/蛋白总量，以及与目标的差值。
    targets 已按周计划自动选用训练日或休息日目标（含 day_kind）。默认今天。"""
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
    """记录一餐到本地库。用户说吃了/喝了某样东西时必须调用（多食物优先用 log_meals）。
    meal_type：早餐/午餐/晚餐/加餐/蛋白粉/其他。热量与宏量可估算后写入，不要只口头回复。"""
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
def log_meals(meals_json: str, target_date: Optional[str] = None) -> str:
    """一次写入多条饮食记录。用户一句话里报了多种食物时优先用本工具，不要只回复建议。

    meals_json 为 JSON 数组，每项字段：
    name(必填), meal_type(早餐/午餐/晚餐/加餐/蛋白粉/其他), calories, protein_g, carb_g, fat_g, notes。
    示例：[{"name":"牛奶半杯","meal_type":"晚餐","calories":82,"protein_g":4,"carb_g":6,"fat_g":4},
           {"name":"西红柿炒蛋","meal_type":"晚餐","calories":180,"protein_g":10,"carb_g":8,"fat_g":12}]
    热量宏量自行按常见份量估算后写入。"""
    try:
        data = json.loads(meals_json)
    except json.JSONDecodeError as exc:
        return _ok({"ok": False, "error": f"meals_json 解析失败: {exc}"})
    if not isinstance(data, list) or not data:
        return _ok({"ok": False, "error": "meals_json 必须是非空数组"})

    repo = get_repo()
    saved: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"第{i + 1}项不是对象")
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            errors.append(f"第{i + 1}项缺少 name")
            continue
        row = repo.log_meal(
            name=name,
            meal_type=str(item.get("meal_type") or "正餐"),
            calories=item.get("calories"),
            protein_g=item.get("protein_g"),
            carb_g=item.get("carb_g"),
            fat_g=item.get("fat_g"),
            notes=str(item.get("notes") or ""),
            target_date=target_date,
        )
        saved.append(row)

    summary = repo.get_nutrition_day(target_date)
    return _ok(
        {
            "ok": bool(saved),
            "saved_count": len(saved),
            "meals": saved,
            "errors": errors,
            "day": summary,
        }
    )


@tool
def update_meal(
    meal_id: int,
    name: Optional[str] = None,
    meal_type: Optional[str] = None,
    calories: Optional[float] = None,
    protein_g: Optional[float] = None,
    carb_g: Optional[float] = None,
    fat_g: Optional[float] = None,
    notes: Optional[str] = None,
    target_date: Optional[str] = None,
) -> str:
    """按 meal_id 修改一条饮食记录。"""
    try:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if meal_type is not None:
            fields["meal_type"] = meal_type
        if calories is not None:
            fields["calories"] = calories
        if protein_g is not None:
            fields["protein_g"] = protein_g
        if carb_g is not None:
            fields["carb_g"] = carb_g
        if fat_g is not None:
            fields["fat_g"] = fat_g
        if notes is not None:
            fields["notes"] = notes
        if target_date is not None:
            fields["date"] = target_date
        row = get_repo().update_meal(int(meal_id), **fields)
        return _ok({"ok": True, "meal": row})
    except ValueError as exc:
        return _ok({"ok": False, "error": str(exc)})


@tool
def delete_meal(meal_id: int) -> str:
    """删除一条饮食记录。"""
    ok = get_repo().delete_meal(int(meal_id))
    return _ok({"ok": ok, "meal_id": meal_id})


# ---------------------------------------------------------------------------
# Body metrics
# ---------------------------------------------------------------------------


@tool
def list_body_metrics(days: int = 90) -> str:
    """读取近 N 天体重/体脂记录。"""
    return _ok({"days": days, "metrics": get_repo().list_body_metrics(days=days)})


@tool
def log_body_metrics(
    weight_kg: Optional[float] = None,
    body_fat_pct: Optional[float] = None,
    notes: str = "",
    target_date: Optional[str] = None,
    also_update_profile: bool = True,
) -> str:
    """用户报了体重/体脂数字时必须调用。默认同时写回画像中的当前体重/体脂。"""
    row = get_repo().log_body_metrics(
        weight_kg=weight_kg,
        body_fat_pct=body_fat_pct,
        notes=notes,
        target_date=target_date,
    )
    if also_update_profile:
        from datetime import date as _date

        ds = target_date or _date.today().isoformat()
        if ds == _date.today().isoformat():
            fields: dict[str, Any] = {}
            if weight_kg is not None:
                fields["weight_kg"] = weight_kg
            if body_fat_pct is not None:
                fields["body_fat_pct"] = body_fat_pct
            if fields:
                # update_profile 会再次 upsert 当日 body_metrics，幂等
                get_repo().update_profile(**fields)
    return _ok({"ok": True, "metrics": row})


@tool
def delete_body_metrics(target_date: str) -> str:
    """删除某日体重/体脂记录（YYYY-MM-DD）。"""
    ok = get_repo().delete_body_metrics(target_date)
    return _ok({"ok": ok, "date": target_date})


# ---------------------------------------------------------------------------
# Daily reports
# ---------------------------------------------------------------------------


@tool
def get_daily_report(target_date: Optional[str] = None) -> str:
    """读取某日已保存的每日报告。默认今天。"""
    report = get_repo().get_daily_report(target_date)
    if not report:
        return _ok({"exists": False, "date": target_date, "message": "该日尚无报告"})
    return _ok({"exists": True, "report": report})


@tool
def list_daily_reports(limit: int = 30) -> str:
    """列出最近的每日报告摘要。"""
    return _ok({"reports": get_repo().list_daily_reports(limit=limit)})


@tool
def save_daily_report(
    content: str,
    title: str = "每日报告",
    user_note: str = "",
    target_date: Optional[str] = None,
) -> str:
    """保存或覆盖某日每日报告正文。"""
    from datetime import date as _date

    ds = target_date or _date.today().isoformat()
    snapshot = get_repo().get_day_snapshot(ds)
    row = get_repo().save_daily_report(
        target_date=ds,
        title=title,
        content=content,
        stats={
            "workout": snapshot.get("workout"),
            "nutrition": {
                "totals": (snapshot.get("nutrition") or {}).get("totals"),
                "targets": (snapshot.get("nutrition") or {}).get("targets"),
            },
        },
        user_note=user_note,
    )
    return _ok({"ok": True, "report": row})


@tool
def delete_daily_report(target_date: str) -> str:
    """删除某日每日报告。"""
    get_repo().delete_daily_report(target_date)
    return _ok({"ok": True, "date": target_date})


# ---------------------------------------------------------------------------
# Analysis / convenience (high-value coach actions)
# ---------------------------------------------------------------------------


@tool
def estimate_workout_burn(
    target_date: Optional[str] = None,
    save: bool = True,
) -> str:
    """AI 估算某日训练的额外运动消耗（kcal，不含全天 BMR），默认写入该日 workout。
    练完后、算热量缺口或写日报前可先调用。无完成组时接近 0。"""
    from agent.calorie_burn import estimate_workout_calories

    result = estimate_workout_calories(target_date, save=save)
    return _ok({"ok": True, **result})


@tool
def generate_daily_report_ai(
    target_date: Optional[str] = None,
    user_note: str = "",
    estimate_burn_if_missing: bool = True,
) -> str:
    """用 AI 生成并保存某日专业复盘报告（训练/饮食/恢复/明天建议）。
    用户说「写日报」「生成今日报告」时用本工具，不要只用 save_daily_report 手写空壳。"""
    from agent.daily_report import generate_daily_report

    result = generate_daily_report(
        target_date,
        user_note=user_note or "",
        save=True,
        estimate_burn_if_missing=estimate_burn_if_missing,
    )
    return _ok(
        {
            "ok": True,
            "date": result.get("date"),
            "title": result.get("title"),
            "content": result.get("content"),
            "stats": result.get("stats"),
        }
    )


@tool
def get_energy_balance(target_date: Optional[str] = None) -> str:
    """查询某日热量账：常规消耗（画像 BMR×活动量）+ 运动消耗 − 摄入 = 缺口。
    deficit 正数=缺口，负数=盈余。运动消耗未估时按 0。"""
    from agent.energy import energy_balance

    repo = get_repo()
    ds = target_date or None
    snapshot = repo.get_day_snapshot(ds)
    nutri = (snapshot.get("nutrition") or {}).get("totals") or {}
    burn = (snapshot.get("workout") or {}).get("calories_burned")
    balance = energy_balance(
        profile=snapshot.get("profile") or repo.get_profile(),
        intake_kcal=nutri.get("calories"),
        exercise_kcal=burn,
    )
    return _ok(
        {
            "date": snapshot.get("date"),
            "balance": balance,
            "nutrition_targets": (snapshot.get("nutrition") or {}).get("targets"),
            "hint": "缺口 = baseline + exercise − intake；练完可先 estimate_workout_burn",
        }
    )


@tool
def get_day_snapshot(target_date: Optional[str] = None) -> str:
    """读取某日综合快照：画像摘要、计划、训练完成情况、饮食合计与目标、运动消耗。
    需要一眼看懂整天时优先用本工具，比分别多次查询更省。"""
    return _ok(get_repo().get_day_snapshot(target_date))


@tool
def add_planned_set(
    exercise_name: str,
    weight_kg: Optional[float] = None,
    reps: Optional[int] = None,
    notes: str = "",
    target_date: Optional[str] = None,
) -> str:
    """给某日某个动作追加 1 组未完成计划组（「再加一组」）。
    不传重量/次数则沿用该动作上一组。"""
    name = get_repo().resolve_exercise_name(exercise_name)
    workout = get_repo().get_today_workout(target_date)["workout"]
    row = get_repo().add_planned_set(
        int(workout["id"]),
        name,
        weight_kg=weight_kg,
        reps=reps,
        notes=notes or "",
    )
    return _ok({"ok": True, "set": row})


@tool
def drop_last_incomplete_set(
    exercise_name: str,
    target_date: Optional[str] = None,
) -> str:
    """删除某动作最后一组未完成计划组（「少一组」）。不影响已完成组。"""
    name = get_repo().resolve_exercise_name(exercise_name)
    workout = get_repo().get_today_workout(target_date)["workout"]
    ok = get_repo().drop_last_incomplete_set(int(workout["id"]), name)
    return _ok({"ok": bool(ok), "exercise_name": name})


@tool
def get_last_completed_set(
    exercise_name: str,
    before_date: Optional[str] = None,
) -> str:
    """查询某动作最近一次已完成组（重量/次数/RPE/日期），用于建议今日负荷。
    before_date 不传则截至今天（不含强制排除今天时由仓库逻辑处理）。"""
    name = get_repo().resolve_exercise_name(exercise_name)
    row = get_repo().get_last_completed_set(name, before_date=before_date)
    if not row:
        return _ok({"ok": False, "exercise_name": name, "message": "暂无该动作完成记录"})
    return _ok({"ok": True, "exercise_name": name, "set": row})


@tool
def get_week_completion(days: int = 7) -> str:
    """近 N 天训练完成度一览（每日计划名、完成组/总组、是否完成）。默认 7 天。"""
    return _ok({"days": get_repo().get_completion_last_n_days(int(days))})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    # profile
    get_profile,
    update_profile,
    # plan
    get_current_plan,
    save_plan,
    update_plan_day,
    mutate_plan_exercise,
    # today / sets
    get_today_workout,
    log_set,
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
    resync_today_from_plan,
    defer_workout,
    clear_day_override,
    # history / analysis
    get_recent_history,
    get_exercise_progress,
    get_day_detail,
    get_day_snapshot,
    get_last_completed_set,
    get_week_completion,
    get_energy_balance,
    estimate_workout_burn,
    # library
    list_exercises,
    # nutrition
    get_nutrition_day,
    get_recent_nutrition,
    log_meal,
    log_meals,
    update_meal,
    delete_meal,
    # body
    list_body_metrics,
    log_body_metrics,
    delete_body_metrics,
    # reports
    get_daily_report,
    list_daily_reports,
    save_daily_report,
    generate_daily_report_ai,
    delete_daily_report,
]
