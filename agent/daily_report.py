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

REPORT_SYSTEM = """你是资深私人健身教练兼运动营养顾问，撰写「当日专业复盘报告」。
只根据给定 JSON 写中文 Markdown；禁止编造未出现的动作、餐食、重量或计划。

界面「数据一览」已有营养对照、餐次、训练组次表格——正文禁止再输出 Markdown 表格，也不要整段复述组次/餐次清单。
用专业分析段落展开；关键数字（完成度、代表组重量×次数×RPE、热量/蛋白相对目标、消耗 kcal）可嵌入论述，但重点是判断、因果与下一步。

结构（用 ## 标题，不要改名；可在节内用 ### 小节）：
## 一句话总结
## 训练复盘
## 饮食与能量
## 恢复与状态
## 做得好的点
## 可改进与风险
## 明天建议
## 本周视角（可选，有 recent_training 时写）

写作要求：
1. 语气专业、清晰、可执行；像教练写的课后报告，不是口号文案。
2. 「一句话总结」：用 1～2 句概括今日训练执行 + 饮食/能量是否匹配目标。
3. 「训练复盘」（核心，写充分）：
   - 计划执行：完成组数/总组、是否按 today_plan；跳过或未完成动作的影响与优先级。
   - 强度与质量：挑 2～4 个关键动作点评负荷、次数、RPE 是否合理（过易/到位/过高）；模式问题（如全程 RPE 偏高、大重量次数崩）要点明。
   - 有 calories_burned 时结合训练量解读消耗是否合理；休息日则写恢复日安排与建议。
   - 不要只报数字，要给「所以下次怎么调」的一句结论。
4. 「饮食与能量」：
   - 相对目标分析热量、蛋白、碳水、脂肪是否匹配今日训练（练日蛋白/碳水、休息日可略降等）。
   - 若 JSON 含 energy_balance 且 ok=true，据此解读常规消耗/运动消耗/摄入与缺口（deficit 正为缺口）；勿另编 TDEE。
   - 没记账写「今日饮食记录不足」，并说明这对评估恢复与下周调整的影响。
5. 「恢复与状态」：结合 user_note、睡眠字段（若有）、伤病史、今日 RPE 谈恢复风险与简单恢复手段（睡眠、拉伸、步行、下一次课热身注意）。
6. 「做得好的点」：3～5 条，具体到行为（例如某动作完成度、蛋白达标、按计划收工）。
7. 「可改进与风险」：3～5 条，写清问题 → 原因假设 → 可执行改法；涉及伤痛只给保守建议。
8. 「明天建议」必须严格跟 upcoming_plans（尤其明天）：
   - 明天有训练：课次名、重点动作、强度预期、睡眠/碳水/热身/可能的替代思路；禁止写成「明天休息」。
   - 明天休息：恢复内容与活动上限。
   - 后天可一句带过。
9. 「本周视角」：用 recent_training 看完成度趋势与疲劳堆积，给 2～4 句节奏建议；数据不足可省略整节。
10. 全文约 800～1400 字；禁止表格、禁止代码块包全文、不要输出 JSON。
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
    try:
        from agent.energy import energy_balance

        nutri = (snapshot.get("nutrition") or {}).get("totals") or {}
        burn = (snapshot.get("workout") or {}).get("calories_burned")
        payload["energy_balance"] = energy_balance(
            profile=snapshot.get("profile") or repo.get_profile(),
            intake_kcal=nutri.get("calories"),
            exercise_kcal=burn,
        )
    except Exception:
        pass

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

    llm = get_llm(temperature=0.4, thinking=False)
    resp = llm.invoke(
        [
            SystemMessage(content=REPORT_SYSTEM),
            HumanMessage(
                content=(
                    "请根据以下 JSON 数据撰写详细专业的当日复盘报告"
                    "（分析充分，仍禁止表格）：\n"
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
