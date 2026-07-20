"""Map profile equipment scenarios to exercise-library tags."""

from __future__ import annotations

# 设置页「器械条件」→ 动作库 equipment 标签（None = 不限制）
PROFILE_EQUIPMENT_TAGS: dict[str, list[str] | None] = {
    "健身房": None,
    "综合": None,
    "家庭哑铃杠铃": ["哑铃", "杠铃", "自重", "弹力带", "壶铃", "曲杆", "六角杠", "无"],
    "家庭哑铃": ["哑铃", "自重", "弹力带", "壶铃", "无"],
    "仅自重": ["自重", "无"],
    "弹力带为主": ["弹力带", "自重", "无"],
}


def resolve_equipment_filter(equipment: str) -> list[str] | None:
    """Return allowed tags, empty list meaning match-nothing, None meaning no filter.

    - Profile scenario keys use PROFILE_EQUIPMENT_TAGS
    - Raw library tags (杠铃/哑铃/…) filter by substring/equality
    """
    eq = (equipment or "").strip()
    if not eq:
        return None
    if eq in PROFILE_EQUIPMENT_TAGS:
        return PROFILE_EQUIPMENT_TAGS[eq]
    # treat as single library tag
    return [eq]
