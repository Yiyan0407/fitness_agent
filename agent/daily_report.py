"""Generate and persist end-of-day fitness reports."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from bootstrap import get_repo

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

REPORT_SYSTEM = """你是用户的私人健身教练，负责写「当日复盘报告」。
根据提供的 JSON 数据，输出一份简洁可执行的中文 Markdown 报告。

要求：
1. 只根据给定数据写，不要编造没出现的动作、餐食或计划。
2. 语气鼓励但务实，适合晚上看完就睡觉。
3. 结构固定为以下小节（用 ## 标题）：
   ## 一句话总结
   ## 训练复盘
   ## 饮食复盘
   ## 做得好的点
   ## 可改进
   ## 明天建议
4. 训练复盘写完成组数、主要动作与重量/RPE；若有 calories_burned 必须写明预估运动消耗 kcal；
   对照 today_plan 看有没有跳过的动作；休息日就写恢复建议。
5. 饮食复盘对照热量/蛋白目标（有目标才对比）；可把摄入与运动消耗对照着提一句。
6. 「明天建议」必须严格依据 upcoming_plans（尤其是明天那一天）：
   - 若明天 rest=false 且有 exercises：明确写出明天要练什么（课次名称 + 主要动作），
     可给睡眠/碳水/热身提醒，但禁止写成「明天休息 / 以恢复为主、不要训练」。
   - 若明天 rest=true 或无安排：再给恢复、拉伸、步行等建议。
   - 可顺带提一句 upcoming_plans 里后天的安排，但不要喧宾夺主。
7. 结合 recent_training 判断是否连续练太狠；若明天有硬课且近期完成度很高，可建议早点睡、控制力竭，
   但仍以执行明天计划为前提，不要擅自改成休息日。
8. 全文控制在 450～800 字。
9. 不要输出 JSON，不要用代码块包裹全文。
"""


def _message_text(resp) -> str:
    content = resp.content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _default_title(snapshot: dict[str, Any]) -> str:
    plan = snapshot.get("plan") or {}
    if plan.get("rest"):
        return f"{snapshot['date']} 休息日复盘"
    name = plan.get("name") or "训练"
    return f"{snapshot['date']} {name} 日报"


def _compact_stats(snapshot: dict[str, Any]) -> dict[str, Any]:
    w = snapshot.get("workout") or {}
    n = snapshot.get("nutrition") or {}
    return {
        "date": snapshot.get("date"),
        "plan_name": (snapshot.get("plan") or {}).get("name"),
        "rest": bool((snapshot.get("plan") or {}).get("rest")),
        "completed_sets": w.get("completed_sets"),
        "total_sets": w.get("total_sets"),
        "calories_burned": w.get("calories_burned"),
        "calories": (n.get("totals") or {}).get("calories"),
        "protein_g": (n.get("totals") or {}).get("protein_g"),
        "meal_count": len(n.get("meals") or []),
        "weight_kg": (snapshot.get("profile") or {}).get("weight_kg"),
        "body_fat_pct": (snapshot.get("profile") or {}).get("body_fat_pct"),
    }


def _slim_exercises(exercises: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    slim = []
    for ex in exercises or []:
        name = ex.get("name") or ex.get("exercise") or ""
        if not name:
            continue
        slim.append(
            {
                "name": name,
                "sets": ex.get("sets"),
                "reps": ex.get("reps"),
                "weight_kg": ex.get("weight_kg") or ex.get("weight"),
            }
        )
    return slim


def _plan_day_summary(repo, target: date) -> dict[str, Any]:
    plan = repo.get_plan_for_date(target) or {}
    rest = bool(plan.get("rest"))
    exercises = _slim_exercises(plan.get("exercises"))
    return {
        "date": target.isoformat(),
        "weekday": WEEKDAY_CN[target.weekday()],
        "weekday_key": [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ][target.weekday()],
        "name": plan.get("name") or ("休息" if rest else "训练"),
        "rest": rest or not exercises,
        "exercise_count": len(exercises),
        "exercises": exercises,
    }


def _today_plan_vs_done(snapshot: dict[str, Any], detail_sets: list[dict[str, Any]]) -> dict[str, Any]:
    plan = snapshot.get("plan") or {}
    planned = _slim_exercises(plan.get("exercises"))
    done_names = set((snapshot.get("workout") or {}).get("exercises") or {})
    incomplete = []
    for s in detail_sets:
        if s.get("completed"):
            continue
        incomplete.append(
            {
                "exercise_name": s.get("exercise_name"),
                "set_index": s.get("set_index"),
                "weight_kg": s.get("weight_kg"),
                "reps": s.get("reps"),
            }
        )
    skipped_planned = [
        ex["name"] for ex in planned if ex["name"] not in done_names
    ]
    return {
        "planned_exercises": planned,
        "completed_exercise_names": sorted(done_names),
        "skipped_or_undone_planned": skipped_planned,
        "incomplete_sets_count": len(incomplete),
        "incomplete_sets_preview": incomplete[:12],
    }


def build_report_context(target_date: str | None = None) -> dict[str, Any]:
    """Richer context for daily report: today + upcoming plans + recent training."""
    repo = get_repo()
    snapshot = repo.get_day_snapshot(target_date)
    ds = date.fromisoformat(snapshot["date"])
    detail = repo.get_day_detail(ds.isoformat())
    sets = detail.get("sets") or []

    upcoming = [_plan_day_summary(repo, ds + timedelta(days=i)) for i in range(1, 4)]
    recent = repo.get_completion_last_n_days(7)
    history = repo.get_recent_history(7)
    # Keep history compact for the prompt
    recent_sets_preview = []
    for row in (history.get("sets") or [])[:20]:
        recent_sets_preview.append(
            {
                "date": row.get("workout_date"),
                "exercise": row.get("exercise_name"),
                "weight_kg": row.get("weight_kg"),
                "reps": row.get("reps"),
                "rpe": row.get("rpe"),
            }
        )

    return {
        "snapshot": snapshot,
        "today_execution": _today_plan_vs_done(snapshot, sets),
        "upcoming_plans": upcoming,
        "tomorrow": upcoming[0] if upcoming else None,
        "recent_training": {
            "last_7_days_completion": recent,
            "recent_completed_sets_preview": recent_sets_preview,
        },
    }


def generate_daily_report(
    target_date: str | None = None,
    user_note: str = "",
    *,
    save: bool = True,
    estimate_burn_if_missing: bool = True,
) -> dict[str, Any]:
    """Build day snapshot, ask LLM for report markdown, optionally save."""
    repo = get_repo()
    context = build_report_context(target_date)
    snapshot = context["snapshot"]
    ds = snapshot["date"]

    workout = snapshot.get("workout") or {}
    if (
        estimate_burn_if_missing
        and not workout.get("calories_burned")
        and int(workout.get("completed_sets") or 0) > 0
    ):
        from agent.calorie_burn import estimate_workout_calories

        estimate_workout_calories(ds, save=True)
        context = build_report_context(ds)
        snapshot = context["snapshot"]

    payload = {
        **context,
        "user_note": (user_note or "").strip(),
    }
    tomorrow = context.get("tomorrow") or {}
    hint = ""
    if tomorrow and not tomorrow.get("rest") and tomorrow.get("exercises"):
        names = "、".join(ex["name"] for ex in tomorrow["exercises"][:5])
        hint = (
            f"\n\n重要提醒：明天（{tomorrow.get('date')} {tomorrow.get('weekday')}）"
            f"计划是「{tomorrow.get('name')}」，动作为：{names}。"
            "「明天建议」必须围绕执行该训练计划来写，不要写成休息日。"
        )
    elif tomorrow and tomorrow.get("rest"):
        hint = (
            f"\n\n重要提醒：明天（{tomorrow.get('date')} {tomorrow.get('weekday')}）"
            "在周计划里是休息日，「明天建议」可以给恢复建议。"
        )

    llm = get_llm(temperature=0.35)
    resp = llm.invoke(
        [
            SystemMessage(content=REPORT_SYSTEM),
            HumanMessage(
                content=(
                    "请根据以下 JSON 数据写当日复盘报告：\n"
                    + json.dumps(payload, ensure_ascii=False, default=str)
                    + hint
                )
            ),
        ]
    )
    content = _message_text(resp).strip()
    content = re.sub(r"^```(?:markdown|md)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content).strip()
    if not content:
        raise ValueError("模型未返回报告内容")

    title = _default_title(snapshot)
    # use first heading line as title if present
    first_line = content.splitlines()[0].strip() if content else ""
    if first_line.startswith("# ") and not first_line.startswith("## "):
        title = first_line.lstrip("# ").strip() or title

    stats = _compact_stats(snapshot)
    stats["tomorrow_rest"] = bool(tomorrow.get("rest"))
    stats["tomorrow_name"] = tomorrow.get("name")
    result = {
        "date": ds,
        "title": title,
        "content": content,
        "stats": stats,
        "user_note": (user_note or "").strip(),
        "snapshot": snapshot,
        "context": {
            "tomorrow": tomorrow,
            "upcoming_plans": context.get("upcoming_plans"),
        },
    }
    if save:
        row = repo.save_daily_report(
            target_date=ds,
            title=title,
            content=content,
            stats=stats,
            user_note=user_note,
        )
        result["saved"] = row
    return result
