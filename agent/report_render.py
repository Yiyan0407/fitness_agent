"""Build tabular views and PNG export for daily reports."""

from __future__ import annotations

import html
import io
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from db.schema import DATA_DIR

# System fonts that include Simplified Chinese glyphs (macOS / Linux)
_FONT_CANDIDATES = [
    # Prefer true TTF first — more reliable than TTC in some Pillow builds
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    str(Path.home() / "Library/Fonts/Arial Unicode.ttf"),
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
                "完成": "是" if s.get("completed") else "否",
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


def _font_supports_cjk(font) -> bool:
    """Reject fonts that only draw .notdef tofu for Chinese."""
    try:
        box = font.getbbox("日报")
        if not box:
            return False
        w = box[2] - box[0]
        # two CJK chars should be roughly 2× one Latin letter or wider
        return w >= 20
    except Exception:
        return False


@lru_cache(maxsize=1)
def _resolve_cjk_font_path() -> str:
    """Find a CJK font and cache a local copy under data/ so export is stable."""
    local_dir = DATA_DIR / "fonts"
    local_dir.mkdir(parents=True, exist_ok=True)

    # Prefer already-copied local font
    for local in sorted(local_dir.glob("*")):
        if local.suffix.lower() in {".ttf", ".otf", ".ttc"}:
            if _try_load_font(str(local), 24) is not None:
                return str(local)

    for path in _FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        if _try_load_font(path, 24) is None:
            continue
        # Copy into data/fonts for consistent later loads
        dest = local_dir / Path(path).name
        try:
            if not dest.exists() or dest.stat().st_size < 1000:
                shutil.copy2(path, dest)
            return str(dest)
        except OSError:
            return path

    raise RuntimeError(
        "未找到可用的中文字体，无法生成日报图片。"
        "请安装「Arial Unicode」或「冬青黑体/华文黑体」后重试。"
    )


def _try_load_font(path: str, size: int):
    from PIL import ImageFont

    for index in (0, 1, 2):
        try:
            font = ImageFont.truetype(path, size=size, index=index)
        except (OSError, ValueError):
            continue
        if _font_supports_cjk(font):
            # remember working index via path#index only if needed
            font._fitness_font_index = index  # type: ignore[attr-defined]
            return font
    return None


def _pick_font(size: int):
    from PIL import ImageFont

    path = _resolve_cjk_font_path()
    font = _try_load_font(path, size)
    if font is not None:
        return font
    # retry with stored index 0 only
    try:
        font = ImageFont.truetype(path, size=size, index=0)
        if _font_supports_cjk(font):
            return font
    except OSError:
        pass
    raise RuntimeError(f"无法用中文字体渲染：{path}")


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for para in (text or "").splitlines() or [""]:
        para = para.strip()
        if not para:
            lines.append("")
            continue
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
    t = re.sub(r"^\s*\|?\s*:?-{3,}:?\s*\|.*$", "", t, flags=re.M)
    t = re.sub(r"\|", "  ", t)
    return t.strip()


def _content_to_html(text: str) -> str:
    t = text or ""
    t = re.sub(r"^```(?:markdown|md)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t).strip()
    out: list[str] = []
    lines = t.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip()
                cells = [c.strip() for c in raw.strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c.replace(" ", "")) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                out.append("<table>")
                for ri, cells in enumerate(rows):
                    tag = "th" if ri == 0 else "td"
                    out.append(
                        "<tr>"
                        + "".join(
                            f"<{tag}>{html.escape(c)}</{tag}>" for c in cells
                        )
                        + "</tr>"
                    )
                out.append("</table>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if heading:
            level = min(len(heading.group(1)) + 1, 6)
            out.append(
                f"<h{level}>{html.escape(heading.group(2))}</h{level}>"
            )
            i += 1
            continue
        if re.match(r"^[-*·]\s+", line.strip()):
            out.append("<ul>")
            while i < len(lines) and re.match(r"^[-*·]\s+", lines[i].strip()):
                item = re.sub(r"^[-*·]\s+", "", lines[i].strip())
                out.append(f"<li>{html.escape(item)}</li>")
                i += 1
            out.append("</ul>")
            continue
        if line.strip():
            raw = re.sub(r"\*\*(.+?)\*\*", r"\1", line.strip())
            out.append(f"<p>{html.escape(raw)}</p>")
        i += 1
    return "\n".join(out)


def build_report_html(
    *,
    title: str,
    content: str,
    snapshot: dict[str, Any] | None = None,
    sets: list[dict[str, Any]] | None = None,
    user_note: str = "",
) -> str:
    """Build a self-contained HTML card (UTF-8) for browser screenshot export."""
    snapshot = snapshot or {}
    w = snapshot.get("workout") or {}
    n = snapshot.get("nutrition") or {}
    totals = n.get("totals") or {}
    targets = n.get("targets") or {}

    meta_bits = [
        f"训练 {w.get('completed_sets') or 0}/{w.get('total_sets') or 0} 组"
    ]
    burn = w.get("calories_burned")
    if burn is not None:
        meta_bits.append(f"消耗 {float(burn):.0f} kcal")
    cal_t = targets.get("calorie_target")
    cal_s = f"摄入 {_num0(totals.get('calories')):.0f}"
    if cal_t:
        cal_s += f" / 目标 {float(cal_t):.0f}"
    meta_bits.append(cal_s + " kcal")

    nutri_rows = ""
    for label, key, tkey, unit in [
        ("热量", "calories", "calorie_target", "kcal"),
        ("蛋白", "protein_g", "protein_target_g", "g"),
        ("碳水", "carb_g", "carb_target_g", "g"),
        ("脂肪", "fat_g", "fat_target_g", "g"),
    ]:
        tv = targets.get(tkey)
        nutri_rows += (
            f"<tr><td>{html.escape(label)}</td>"
            f"<td>{_num0(totals.get(key)):.0f}</td>"
            f"<td>{html.escape(_num_or_blank(tv) or '—')}</td>"
            f"<td>{html.escape(unit)}</td></tr>"
        )

    set_rows = ""
    for s in sets or []:
        set_rows += (
            "<tr>"
            f"<td>{html.escape(str(s.get('exercise_name') or ''))}</td>"
            f"<td>{html.escape(str(s.get('set_index') or ''))}</td>"
            f"<td>{html.escape(_num_or_blank(s.get('weight_kg')))}</td>"
            f"<td>{html.escape(_num_or_blank(s.get('reps')))}</td>"
            f"<td>{html.escape(_num_or_blank(s.get('rpe')))}</td>"
            f"<td>{'是' if s.get('completed') else '否'}</td>"
            "</tr>"
        )

    content_html = _content_to_html(content)
    note_html = (
        f'<p class="note">备注：{html.escape(user_note)}</p>' if user_note else ""
    )
    sets_block = (
        f"""<h3>训练组次</h3>
        <table>
          <tr><th>动作</th><th>组</th><th>重量</th><th>次数</th><th>RPE</th><th>完成</th></tr>
          {set_rows}
        </table>"""
        if set_rows
        else ""
    )

    return f"""
<div id="report-card" class="card">
  <h1>{html.escape(title or '每日报告')}</h1>
  <p class="meta">{html.escape(' · '.join(meta_bits))}</p>
  {note_html}
  <h3>营养对照</h3>
  <table>
    <tr><th>项目</th><th>摄入</th><th>目标</th><th>单位</th></tr>
    {nutri_rows}
  </table>
  {sets_block}
  <h3>教练复盘</h3>
  <div class="body">{content_html}</div>
  <p class="foot">Fitness Agent · 每日报告</p>
</div>
"""


def render_report_download_widget(
    *,
    title: str,
    content: str,
    snapshot: dict[str, Any] | None = None,
    sets: list[dict[str, Any]] | None = None,
    user_note: str = "",
    file_name: str = "日报.png",
    height: int = 72,
) -> None:
    """Browser-side PNG export using system Chinese fonts (avoids Pillow tofu/mojibake)."""
    import streamlit.components.v1 as components

    card = build_report_html(
        title=title,
        content=content,
        snapshot=snapshot,
        sets=sets,
        user_note=user_note,
    )
    safe_name = html.escape(file_name).replace("'", "")
    components.html(
        f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<style>
  html, body {{
    margin: 0; padding: 0;
    font-family: "PingFang SC", "Hiragino Sans GB", "Heiti SC",
      "Microsoft YaHei", "Noto Sans SC", "Source Han Sans SC", sans-serif;
    background: transparent;
  }}
  .toolbar {{
    display: flex; gap: 8px; align-items: center;
    padding: 4px 0 8px;
  }}
  button#save-btn {{
    appearance: none; border: none; cursor: pointer;
    background: #0f766e; color: #fff;
    padding: 0.55rem 1rem; border-radius: 0.5rem;
    font-size: 0.95rem; font-weight: 600;
    font-family: inherit;
  }}
  button#save-btn:disabled {{ opacity: 0.6; cursor: wait; }}
  .hint {{ color: #64748b; font-size: 0.8rem; }}
  /* off-screen render target — full width for crisp capture */
  .capture-host {{
    position: absolute; left: -10000px; top: 0;
    width: 900px;
  }}
  .card {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-left: 10px solid #0f766e;
    border-radius: 16px;
    padding: 28px 32px 20px;
    color: #1c2026;
    box-sizing: border-box;
  }}
  .card h1 {{
    margin: 0 0 8px; font-size: 26px; color: #0f766e; font-weight: 700;
  }}
  .card h3 {{
    margin: 22px 0 10px; font-size: 17px; color: #0f766e;
  }}
  .card h2, .card h4, .card h5 {{
    margin: 14px 0 8px; color: #0f766e;
  }}
  .meta {{ margin: 0 0 8px; color: #6e7681; font-size: 13px; }}
  .note {{ margin: 0 0 12px; color: #334155; }}
  .foot {{ margin: 24px 0 0; color: #94a3b8; font-size: 12px; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
    margin: 0 0 4px;
  }}
  th, td {{
    border: 1px solid #e2e8f0; padding: 8px 10px; text-align: left;
  }}
  th {{ background: #f1f5f9; color: #334155; }}
  .body p {{ margin: 0 0 8px; line-height: 1.55; font-size: 14px; }}
  .body ul {{ margin: 0 0 8px; padding-left: 1.2rem; }}
  .body li {{ margin: 0 0 4px; line-height: 1.5; font-size: 14px; }}
</style>
</head>
<body>
  <div class="toolbar">
    <button id="save-btn" type="button">保存日报图片</button>
    <span class="hint" id="hint">使用系统中文字体导出 PNG</span>
  </div>
  <div class="capture-host">{card}</div>
  <script>
    const btn = document.getElementById('save-btn');
    const hint = document.getElementById('hint');
    btn.addEventListener('click', async () => {{
      btn.disabled = true;
      hint.textContent = '正在生成图片…';
      try {{
        const el = document.getElementById('report-card');
        const canvas = await html2canvas(el, {{
          scale: 2,
          backgroundColor: '#ffffff',
          useCORS: true,
          logging: false,
        }});
        const a = document.createElement('a');
        a.download = '{safe_name}';
        a.href = canvas.toDataURL('image/png');
        a.click();
        hint.textContent = '已开始下载';
      }} catch (err) {{
        hint.textContent = '导出失败：' + (err && err.message ? err.message : err);
      }} finally {{
        btn.disabled = false;
      }}
    }});
  </script>
</body>
</html>""",
        height=height,
    )


def render_report_png(
    *,
    title: str,
    content: str,
    snapshot: dict[str, Any] | None = None,
    sets: list[dict[str, Any]] | None = None,
    user_note: str = "",
    width: int = 900,
) -> bytes:
    """Render a shareable daily-report card as PNG bytes (Pillow + CJK font)."""
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

    blocks: list[tuple[str, str]] = []
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

    content_w = width - pad * 2
    char_w = max(18, content_w // 15)
    y_est = pad
    measured: list[tuple[str, list[str], Any]] = []
    for kind, text in blocks:
        if kind == "title":
            lines = _wrap(text, 28)
            gap = section_gap
        elif kind == "meta":
            lines = _wrap(text, 48)
            gap = 12
        elif kind == "note":
            lines = _wrap(text, 42)
            gap = section_gap
        else:
            raw_lines = text.splitlines()
            lines = []
            for i, ln in enumerate(raw_lines):
                wrap_w = 22 if i == 0 else char_w
                lines.extend(_wrap(ln, wrap_w) if ln else [""])
            gap = section_gap
        measured.append((kind, lines, None))
        y_est += len(lines) * line_h + gap

    height = max(480, y_est + pad + 36)
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (16, 16, width - 16, height - 16), radius=18, fill=card, outline=line_c
    )
    draw.rectangle((16, 16, 28, height - 16), fill=accent)

    y = pad + 8
    for kind, lines, _ in measured:
        color = accent if kind == "title" else (muted if kind == "meta" else ink)
        if kind == "section" and lines:
            draw.text((pad + 12, y), lines[0], font=font_h, fill=accent)
            y += line_h + 4
            for ln in lines[1:]:
                draw.text((pad + 12, y), ln, font=font_body, fill=ink)
                y += line_h
            y += section_gap
            draw.line((pad + 12, y - 10, width - pad, y - 10), fill=line_c, width=1)
            continue
        font = font_title if kind == "title" else (
            font_small if kind == "meta" else font_body
        )
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
