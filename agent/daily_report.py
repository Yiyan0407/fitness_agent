"""Generate and persist end-of-day fitness reports."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from bootstrap import get_repo

REPORT_SYSTEM = """你是用户的私人健身教练，负责写「当日复盘报告」。
根据提供的当日训练、饮食与画像数据，输出一份简洁可执行的中文 Markdown 报告。

要求：
1. 只根据给定数据写，不要编造没出现的动作或餐食。
2. 语气鼓励但务实，适合晚上看完就睡觉。
3. 结构固定为以下小节（用 ## 标题）：
   ## 一句话总结
   ## 训练复盘
   ## 饮食复盘
   ## 做得好的点
   ## 可改进
   ## 明天建议
4. 训练复盘写完成组数、主要动作与重量；若有 calories_burned 必须写明预估运动消耗 kcal；休息日就写恢复建议。
5. 饮食复盘对照热量/蛋白目标（有目标才对比）；可把摄入与运动消耗对照着提一句。
6. 全文控制在 400～700 字。
7. 不要输出 JSON，不要用代码块包裹全文。
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


def generate_daily_report(
    target_date: str | None = None,
    user_note: str = "",
    *,
    save: bool = True,
    estimate_burn_if_missing: bool = True,
) -> dict[str, Any]:
    """Build day snapshot, ask LLM for report markdown, optionally save."""
    repo = get_repo()
    snapshot = repo.get_day_snapshot(target_date)
    ds = snapshot["date"]

    workout = snapshot.get("workout") or {}
    if (
        estimate_burn_if_missing
        and not workout.get("calories_burned")
        and int(workout.get("completed_sets") or 0) > 0
    ):
        from agent.calorie_burn import estimate_workout_calories

        estimate_workout_calories(ds, save=True)
        snapshot = repo.get_day_snapshot(ds)
    payload = {
        "snapshot": snapshot,
        "user_note": (user_note or "").strip(),
    }
    llm = get_llm(temperature=0.35)
    resp = llm.invoke(
        [
            SystemMessage(content=REPORT_SYSTEM),
            HumanMessage(
                content=(
                    "请根据以下 JSON 数据写当日复盘报告：\n"
                    + json.dumps(payload, ensure_ascii=False, default=str)
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
    result = {
        "date": ds,
        "title": title,
        "content": content,
        "stats": stats,
        "user_note": (user_note or "").strip(),
        "snapshot": snapshot,
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
