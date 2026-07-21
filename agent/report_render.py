"""Build tabular views and PNG export for daily reports."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import pandas as pd

# Prefer Chinese-capable fonts on macOS / common Linux
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def nutrition_overview_df(nutrition: dict[str, Any]) -> pd.DataFrame:
    totals = nutrition.get("totals") or {}
    targets = nutrition.get("targets") or {}
    remaining = nutrition.get("remaining") or {}

    def _fmt(v: Any) -> str:
        if v is None or v == "":
            return "—"
        try:
            return f"{float(v):.0f}"
        except (TypeError, ValueError):
            return str(v)

    rows = [
        {
            "项目": "热量 (kcal)",
            "摄入": _fmt(totals.get("calories")),
            "目标": _fmt(targets.get("calorie_target")),
            "剩余": _fmt(remaining.get("calories")),
        },
        {
            "项目": "蛋白 (g)",
            "摄入": _fmt(totals.get("protein_g")),
            "目标": _fmt(targets.get("protein_target_g")),
            "剩余": _fmt(remaining.get("protein_g")),
        },
        {
            "项目": "碳水 (g)",
            "摄入": _fmt(totals.get("carb_g")),
            "目标": _fmt(targets.get("carb_target_g")),
            "剩余": _fmt(remaining.get("carb_g")),
        },
        {
            "项目": "脂肪 (g)",
            "摄入": _fmt(totals.get("fat_g")),
            "目标": _fmt(targets.get("fat_target_g")),
            "剩余": _fmt(remaining.get("fat_g")),
        },
    ]
    return pd.DataFrame(rows)


def meals_df(meals: list[dict[str, Any]] | None) -> pd.DataFrame:
    rows = []
    for m in meals or []:
        rows.append(
            {
                "餐次": m.get("meal_type") or "其他",
                "食物": m.get("name") or "",
                "热量": _num0(m.get("calories")),
                "蛋白": _num0(m.get("protein_g")),
                "碳水": _num0(m.get("carb_g")),
                "脂肪": _num0(m.get("fat_g")),
            }
        )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["餐次", "食物", "热量", "蛋白", "碳水", "脂肪"]
    )


def sets_df(sets: list[dict[str, Any]] | None) -> pd.DataFrame:
    rows = []
    for s in sets or []:
        rows.append(
            {
                "动作": s.get("exercise_name") or "",
                "组": s.get("set_index") or "",
                "重量 kg": _num_or_blank(s.get("weight_kg")),
                "次数": _num_or_blank(s.get("reps")),
                "RPE": _num_or_blank(s.get("rpe")),
                "完成": "✓" if s.get("completed") else "—",
            }
        )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["动作", "组", "重量 kg", "次数", "RPE", "完成"]
    )


def _num0(v: Any) -> float:
    try:
        return round(float(v or 0), 1)
    except (TypeError, ValueError):
        return 0.0


def _num_or_blank(v: Any) -> str:
    if v is None or v == "":
        return ""
    try:
        n = float(v)
        return str(int(n)) if n == int(n) else f"{n:.1f}"
    except (TypeError, ValueError):
        return str(v)


def _pick_font(size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=0)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for para in (text or "").splitlines() or [""]:
        para = para.strip()
        if not para:
            lines.append("")
            continue
        # Chinese-friendly wrap: count chars roughly
        while len(para) > width:
            lines.append(para[:width])
            para = para[width:]
        lines.append(para)
    return lines


def _strip_md(text: str) -> str:
    t = text or ""
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^\s*[-*]\s+", "· ", t, flags=re.M)
    # simplify markdown tables to plain lines
    t = re.sub(r"^\s*\|?\s*:?-{3,}:?\s*\|.*$", "", t, flags=re.M)
    t = re.sub(r"\|", "  ", t)
    return t.strip()


def render_report_png(
    *,
    title: str,
    content: str,
    snapshot: dict[str, Any] | None = None,
    sets: list[dict[str, Any]] | None = None,
    user_note: str = "",
    width: int = 900,
) -> bytes:
    """Render a shareable daily-report card as PNG bytes."""
    from PIL import Image, ImageDraw

    snapshot = snapshot or {}
    w = snapshot.get("workout") or {}
    n = snapshot.get("nutrition") or {}
    totals = n.get("totals") or {}
    targets = n.get("targets") or {}

    pad = 40
    line_h = 28
    section_gap = 22
    bg = (248, 249, 251)
    card = (255, 255, 255)
    ink = (28, 32, 38)
    muted = (110, 118, 129)
    accent = (15, 118, 110)
    line_c = (226, 232, 240)

    font_title = _pick_font(30)
    font_h = _pick_font(20)
    font_body = _pick_font(16)
    font_small = _pick_font(14)

    blocks: list[tuple[str, str]] = []  # kind, text
    blocks.append(("title", title or "每日报告"))
    meta_bits = []
    done = w.get("completed_sets")
    total = w.get("total_sets")
    if done is not None or total is not None:
        meta_bits.append(f"训练 {done or 0}/{total or 0} 组")
    burn = w.get("calories_burned")
    if burn is not None:
        meta_bits.append(f"消耗 {float(burn):.0f} kcal")
    if totals.get("calories") is not None:
        cal_t = targets.get("calorie_target")
        cal_s = f"摄入 {float(totals.get('calories') or 0):.0f}"
        if cal_t:
            cal_s += f" / 目标 {float(cal_t):.0f}"
        meta_bits.append(cal_s + " kcal")
    if meta_bits:
        blocks.append(("meta", "  ·  ".join(meta_bits)))
    if user_note:
        blocks.append(("note", f"备注：{user_note}"))

    # nutrition mini table as text
    nutri_lines = ["营养对照"]
    nutri_lines.append(
        f"热量  {_num0(totals.get('calories')):>6}  /  {_num_or_blank(targets.get('calorie_target')) or '—':>6} kcal"
    )
    nutri_lines.append(
        f"蛋白  {_num0(totals.get('protein_g')):>6}  /  {_num_or_blank(targets.get('protein_target_g')) or '—':>6} g"
    )
    nutri_lines.append(
        f"碳水  {_num0(totals.get('carb_g')):>6}  /  {_num_or_blank(targets.get('carb_target_g')) or '—':>6} g"
    )
    nutri_lines.append(
        f"脂肪  {_num0(totals.get('fat_g')):>6}  /  {_num_or_blank(targets.get('fat_target_g')) or '—':>6} g"
    )
    blocks.append(("section", "\n".join(nutri_lines)))

    sdf = sets_df(sets)
    if not sdf.empty:
        train_lines = ["训练组次"]
        for _, row in sdf.iterrows():
            train_lines.append(
                f"{row['完成']} {row['动作']}  第{row['组']}组  "
                f"{row['重量 kg'] or '-'}kg × {row['次数'] or '-'}  RPE {row['RPE'] or '-'}"
            )
        blocks.append(("section", "\n".join(train_lines[:40])))

    body = _strip_md(content)
    if body:
        blocks.append(("section", "教练复盘\n" + body))

    # measure height
    content_w = width - pad * 2
    char_w = max(18, content_w // 15)
    y_est = pad
    measured: list[tuple[str, list[str], Any]] = []
    for kind, text in blocks:
        if kind == "title":
            lines = _wrap(text, 28)
            font = font_title
            gap = section_gap
        elif kind == "meta":
            lines = _wrap(text, 48)
            font = font_small
            gap = 12
        elif kind == "note":
            lines = _wrap(text, 42)
            font = font_body
            gap = section_gap
        else:
            raw_lines = text.splitlines()
            lines = []
            for i, ln in enumerate(raw_lines):
                wrap_w = 22 if i == 0 else char_w
                lines.extend(_wrap(ln, wrap_w) if ln else [""])
            font = font_body
            gap = section_gap
        measured.append((kind, lines, font))
        y_est += len(lines) * line_h + gap

    height = max(480, y_est + pad + 36)
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    # card
    draw.rounded_rectangle(
        (16, 16, width - 16, height - 16), radius=18, fill=card, outline=line_c
    )
    # accent bar
    draw.rectangle((16, 16, 28, height - 16), fill=accent)

    y = pad + 8
    for kind, lines, font in measured:
        color = accent if kind == "title" else (muted if kind == "meta" else ink)
        if kind == "section" and lines:
            # first line as heading
            draw.text((pad + 12, y), lines[0], font=font_h, fill=accent)
            y += line_h + 4
            for ln in lines[1:]:
                draw.text((pad + 12, y), ln, font=font, fill=ink)
                y += line_h
            y += section_gap
            # separator
            draw.line((pad + 12, y - 10, width - pad, y - 10), fill=line_c, width=1)
            continue
        for ln in lines:
            draw.text((pad + 12, y), ln, font=font, fill=color)
            y += line_h
        y += 12 if kind == "meta" else section_gap

    draw.text(
        (pad + 12, height - 40),
        "Fitness Agent · 每日报告",
        font=font_small,
        fill=muted,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
