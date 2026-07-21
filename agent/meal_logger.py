"""Natural-language and image meal logging."""

from __future__ import annotations

import base64
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, get_vision_llm
from bootstrap import get_repo
from db.schema import DATA_DIR

MEAL_JSON_SPEC = """请只输出一个 JSON 对象（不要 markdown、不要解释），字段如下：
{
  "name": "简短食物名",
  "meal_type": "早餐|午餐|晚餐|加餐|蛋白粉|其他",
  "calories": 数字,
  "protein_g": 数字,
  "carb_g": 数字,
  "fat_g": 数字,
  "notes": "估算依据一句话"
}
规则：
- 按中国常见份量估算（一碗米饭约 150–200g 熟重；外卖套餐按整份）
- 炒菜要计入可见油脂；饮料按包装或常见容量
- 不确定也给出最接近的整数估算，热量不要留空或为 0（除非明确是白水）
- meal_type 无法判断时段时用「其他」或「加餐」
- notes 一句中文，不换行，不用英文双引号
- 输出必须是完整可解析的 JSON
"""

MEAL_PARSE_PROMPT = f"""你是饮食记账助手。用户会用一句话描述吃了/喝了什么。
{MEAL_JSON_SPEC}
- 若用户说了「半份/一小碗/喝了一口」，按比例下调
"""

MEAL_IMAGE_PROMPT = f"""你是饮食营养识别助手。根据餐食图片识别食物，并估算图中可见整份/整盘的营养成分。
{MEAL_JSON_SPEC}
- name 用中文概括盘中主要食物（2～12 字）
- 按图中实际份量估，不要按「理想健康餐」低估
- 有包装或饮料时按可见规格/毫升估算
- 看不清的部分在 notes 里如实写「可见部分估算」
"""

MEAL_IMAGES_DIR = DATA_DIR / "meal_images"


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    candidates = [text]
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        candidates.append(match.group(0))
    # first JSON object only (non-greedy until last })
    first = re.search(r"\{[\s\S]*", text)
    if first:
        candidates.append(_repair_json_object(first.group(0)))

    errors: list[Exception] = []
    for cand in candidates:
        for variant in (cand, _repair_json_object(cand)):
            try:
                data = json.loads(variant)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError) as exc:
                errors.append(exc)

    # last resort: pull fields with regex
    fallback = _extract_fields_loose(text)
    if fallback.get("name") or fallback.get("calories") is not None:
        return fallback

    detail = str(errors[-1]) if errors else "无法解析"
    raise ValueError(f"模型返回不是合法 JSON：{detail}\n原文片段：{text[:200]}")


def _repair_json_object(raw: str) -> str:
    """Best-effort fix for truncated / unescaped model JSON."""
    s = (raw or "").strip()
    # drop trailing junk after last plausible field
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # escape bare newlines inside strings is hard; flatten newlines to spaces
    # only outside of already-closed structure by replacing all newlines
    s = re.sub(r"[\n\t]+", " ", s)

    # if truncated mid-string, close the string and object
    in_string = False
    escape = False
    depth = 0
    out: list[str] = []
    for ch in s:
        out.append(ch)
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)

    repaired = "".join(out)
    if in_string:
        repaired += '"'
    while depth > 0:
        repaired += "}"
        depth -= 1
    # trailing comma before }
    repaired = re.sub(r",\s*}", "}", repaired)
    repaired = re.sub(r",\s*]", "]", repaired)
    return repaired


def _extract_fields_loose(text: str) -> dict[str, Any]:
    def _str(key: str) -> str | None:
        m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
        if m:
            return m.group(1)
        m = re.search(rf'"{key}"\s*:\s*"([^"]*)', text)  # truncated
        return m.group(1) if m else None

    def _num(key: str) -> float | None:
        m = re.search(rf'"{key}"\s*:\s*(-?\d+(?:\.\d+)?)', text)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    return {
        "name": _str("name"),
        "meal_type": _str("meal_type"),
        "calories": _num("calories"),
        "protein_g": _num("protein_g"),
        "carb_g": _num("carb_g"),
        "fat_g": _num("fat_g"),
        "notes": _str("notes") or "",
    }


def _message_text(resp) -> str:
    content = resp.content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            else:
                parts.append(str(block))
        text = "\n".join(parts).strip()
    elif content is None:
        text = ""
    else:
        text = str(content).strip()

    if text:
        return text

    # MiMo thinking mode may put output only in reasoning_content
    extra = getattr(resp, "additional_kwargs", None) or {}
    for key in ("reasoning_content", "reasoning"):
        val = extra.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _normalize_meal(data: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    name = str(data.get("name") or fallback_name)[:80]
    meal_type = str(data.get("meal_type") or "其他")
    if meal_type not in {"早餐", "午餐", "晚餐", "加餐", "蛋白粉", "其他"}:
        meal_type = "其他"

    def _num(key: str) -> float | None:
        val = data.get(key)
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    return {
        "name": name,
        "meal_type": meal_type,
        "calories": _num("calories"),
        "protein_g": _num("protein_g"),
        "carb_g": _num("carb_g"),
        "fat_g": _num("fat_g"),
        "notes": str(data.get("notes") or "")[:300],
    }


def parse_meal_text(user_text: str) -> dict[str, Any]:
    """Parse natural language into meal fields via MiMo."""
    llm = get_llm(temperature=0.2, thinking=False)
    resp = llm.invoke(
        [
            SystemMessage(content=MEAL_PARSE_PROMPT),
            HumanMessage(content=user_text.strip()),
        ]
    )
    raw = _message_text(resp)
    if not raw:
        raise ValueError(
            "模型返回空内容（可能仍在深度思考中耗尽 token）。请重试一次。"
        )
    data = _extract_json(raw)
    parsed = _normalize_meal(data, user_text.strip())
    if not parsed["notes"]:
        parsed["notes"] = f"AI文字估算：{user_text.strip()}"
    return parsed


def _guess_mime(filename: str | None, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def parse_meal_image(
    image_bytes: bytes,
    filename: str | None = None,
    hint: str = "",
) -> dict[str, Any]:
    """Recognize meal nutrition from an image via MiMo vision (mimo-v2.5)."""
    if not image_bytes:
        raise ValueError("图片为空")
    mime = _guess_mime(filename, image_bytes)
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    user_text = "请识别图中食物并估算营养成分。"
    if hint.strip():
        user_text += f" 补充说明：{hint.strip()}"

    llm = get_vision_llm(temperature=0.2)
    resp = llm.invoke(
        [
            SystemMessage(content=MEAL_IMAGE_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
            ),
        ]
    )
    raw = _message_text(resp)
    if not raw:
        raise ValueError(
            "看图模型返回空内容。请换一张更清晰的照片，或稍后重试。"
        )
    data = _extract_json(raw)
    parsed = _normalize_meal(data, filename or "餐食照片")
    if not parsed["notes"]:
        parsed["notes"] = "MiMo 看图估算"
    else:
        parsed["notes"] = f"MiMo 看图：{parsed['notes']}"
    return parsed


def _save_meal_image(image_bytes: bytes, filename: str | None, meal_id: int) -> str:
    MEAL_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename or "meal.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"
    path = MEAL_IMAGES_DIR / f"{date.today().isoformat()}_{meal_id}{suffix}"
    path.write_bytes(image_bytes)
    return str(path)


def log_meal_from_text(
    user_text: str,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Parse user text with AI and write a meal record."""
    text = (user_text or "").strip()
    if not text:
        raise ValueError("请先输入吃了什么")
    parsed = parse_meal_text(text)
    ds = target_date or date.today().isoformat()
    row = get_repo().log_meal(
        name=parsed["name"],
        meal_type=parsed["meal_type"],
        calories=parsed["calories"],
        protein_g=parsed["protein_g"],
        carb_g=parsed["carb_g"],
        fat_g=parsed["fat_g"],
        notes=parsed["notes"],
        target_date=ds,
    )
    return {"parsed": parsed, "meal": row, "day": get_repo().get_nutrition_day(ds)}


def log_meal_from_image(
    image_bytes: bytes,
    filename: str | None = None,
    hint: str = "",
    target_date: str | None = None,
) -> dict[str, Any]:
    """Recognize meal from image with MiMo vision and write a meal record."""
    parsed = parse_meal_image(image_bytes, filename=filename, hint=hint)
    ds = target_date or date.today().isoformat()
    row = get_repo().log_meal(
        name=parsed["name"],
        meal_type=parsed["meal_type"],
        calories=parsed["calories"],
        protein_g=parsed["protein_g"],
        carb_g=parsed["carb_g"],
        fat_g=parsed["fat_g"],
        notes=parsed["notes"],
        target_date=ds,
    )
    try:
        saved = _save_meal_image(image_bytes, filename, int(row["id"]))
        # append image path into notes for traceability
        note = (row.get("notes") or "") + f" | 图:{saved}"
        get_repo().conn.execute(
            "UPDATE meals SET notes = ? WHERE id = ?",
            (note[:500], row["id"]),
        )
        get_repo().conn.commit()
        row = dict(
            get_repo().conn.execute(
                "SELECT * FROM meals WHERE id = ?", (row["id"],)
            ).fetchone()
        )
        parsed["image_path"] = saved
    except OSError:
        pass
    return {"parsed": parsed, "meal": row, "day": get_repo().get_nutrition_day(ds)}
