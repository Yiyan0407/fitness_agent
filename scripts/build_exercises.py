#!/usr/bin/env python3
"""Build data/exercises.json from free-exercise-db + local Chinese overrides.

Usage:
  python scripts/build_exercises.py
  python scripts/build_exercises.py --source /path/to/exercises.json
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "exercises.json"
LEGACY_PATH = ROOT / "data" / "exercises.json"
CACHE_PATH = ROOT / "data" / "_free_exercises_cache.json"

# Prefer jsDelivr (more reachable than raw.githubusercontent in some networks)
SOURCE_URL = (
    "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/dist/exercises.json"
)
IMAGE_BASE = (
    "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/exercises/"
)

EQUIP_MAP = {
    "bands": "弹力带",
    "barbell": "杠铃",
    "body only": "自重",
    "cable": "绳索",
    "dumbbell": "哑铃",
    "e-z curl bar": "曲杆",
    "exercise ball": "健身球",
    "foam roll": "泡沫轴",
    "kettlebells": "壶铃",
    "machine": "器械",
    "medicine ball": "药球",
    "none": "无",
    "other": "其他",
}

MUSCLE_MAP = {
    "abdominals": "核心",
    "abductors": "臀中肌",
    "adductors": "内收肌",
    "biceps": "肱二头",
    "calves": "小腿",
    "chest": "胸",
    "forearms": "前臂",
    "glutes": "臀",
    "hamstrings": "腘绳肌",
    "lats": "背阔肌",
    "lower back": "下背",
    "middle back": "中背",
    "neck": "颈",
    "quadriceps": "股四头",
    "shoulders": "肩",
    "traps": "斜方肌",
    "triceps": "肱三头",
}

# Multi-word phrases (lowercase), longest match first
PHRASE_DICT: dict[str, str] = {
    "smith machine": "史密斯机",
    "ez bar": "曲杆",
    "e z bar": "曲杆",
    "pull up": "引体向上",
    "pull ups": "引体向上",
    "chin up": "反握引体向上",
    "push up": "俯卧撑",
    "push ups": "俯卧撑",
    "sit up": "仰卧起坐",
    "bench press": "卧推",
    "incline bench press": "上斜卧推",
    "decline bench press": "下斜卧推",
    "overhead press": "过头推举",
    "military press": "军事推举",
    "shoulder press": "推肩",
    "lateral raise": "侧平举",
    "front raise": "前平举",
    "rear delt": "后束",
    "face pull": "面拉",
    "face pulls": "面拉",
    "upright row": "直立划船",
    "bent over row": "俯身划船",
    "seated row": "坐姿划船",
    "lat pulldown": "高位下拉",
    "t bar row": "T杠划船",
    "one arm": "单臂",
    "one leg": "单腿",
    "single leg": "单腿",
    "single arm": "单臂",
    "close grip": "窄距",
    "wide grip": "宽距",
    "neutral grip": "对握",
    "leg press": "腿举",
    "leg extension": "腿伸展",
    "leg curl": "腿弯举",
    "calf raise": "提踵",
    "hip thrust": "臀推",
    "glute bridge": "臀桥",
    "good morning": "早安式",
    "romanian deadlift": "罗马尼亚硬拉",
    "sumo deadlift": "相扑硬拉",
    "farmer walk": "农夫行走",
    "farmers walk": "农夫行走",
    "farmer s walk": "农夫行走",
    "wrist roller": "卷腕器",
    "ankle circles": "踝关节绕环",
    "balance board": "平衡板",
    "carioca": "卡里奥卡步",
    "quick step": "快步",
    "lateral cone hops": "侧向锥桶跳",
    "cone hops": "锥桶跳",
    "hyperextensions": "背伸",
    "back extensions": "背伸",
    "adductor": "内收肌",
    "groin": "大腿内侧",
    "world s greatest stretch": "世界最强拉伸",
    "scapular pull up": "肩胛引体",
    "scapular": "肩胛",
    "bodyweight": "自重",
    "body weight": "自重",
    "freehand": "徒手",
    "chair": "椅子",
    "frankenstein": "科学怪人",
    "overhead squat": "过头深蹲",
    "jump squat": "跳深蹲",
    "pull ups": "引体向上",
    "push ups": "俯卧撑",
    "sit ups": "仰卧起坐",
    "deadlift": "硬拉",
    "squat": "深蹲",
    "lunge": "弓步",
    "plank": "平板支撑",
    "crunch": "卷腹",
    "burpee": "波比",
    "shrug": "耸肩",
    "dip": "双杠臂屈伸",
    "dips": "双杠臂屈伸",
    "fly": "飞鸟",
    "flyes": "飞鸟",
    "row": "划船",
    "curl": "弯举",
    "press": "推举",
    "pulldown": "下拉",
    "pullup": "引体向上",
    "pushup": "俯卧撑",
    "situp": "仰卧起坐",
    "barbell": "杠铃",
    "dumbbell": "哑铃",
    "dumbbells": "哑铃",
    "kettlebell": "壶铃",
    "cable": "绳索",
    "machine": "器械",
    "band": "弹力带",
    "bands": "弹力带",
    "smith": "史密斯",
    "standing": "站姿",
    "seated": "坐姿",
    "lying": "卧姿",
    "incline": "上斜",
    "decline": "下斜",
    "hanging": "悬垂",
    "alternating": "交替",
    "alternate": "交替",
    "weighted": "负重",
    "assisted": "辅助",
    "bodyweight": "自重",
    "freehand": "徒手",
    "chair": "椅子",
    "frankenstein": "科学怪人",
    "overhead": "过头",
    "stretch": "拉伸",
    "smr": "筋膜放松",
}

# Exact English name -> Chinese (covers awkward leftovers)
EXACT_NAME_OVERRIDES = {
    "3/4 Sit-Up": "四分之三仰卧起坐",
    "Air Bike": "空中自行车",
    "Atlas Stones": "阿特拉斯石",
    "Atlas Stone Trainer": "阿特拉斯石训练器",
    "Axle Deadlift": "粗杠硬拉",
    "Balance Board": "平衡板",
    "Cat Stretch": "猫式拉伸",
    "Child's Pose": "婴儿式",
    "Dancer's Stretch": "舞者式拉伸",
    "Deficit Deadlift": "垫高硬拉",
    "Farmer's Walk": "农夫行走",
    "Hug A Ball": "抱球",
    "Keg Load": "酒桶搬运",
    "Pyramid": "金字塔支撑",
    "Wrist Roller": "卷腕器",
    "Ankle Circles": "踝关节绕环",
    "Adductor/Groin": "内收肌拉伸",
    "Carioca Quick Step": "卡里奥卡快步",
    "Lateral Cone Hops": "侧向锥桶跳",
    "Hyperextensions (Back Extensions)": "背伸",
    "Standing Pelvic Tilt": "站姿骨盆倾斜",
    "Deadlift with Bands": "弹力带硬拉",
    "Deadlift with Chains": "铁链硬拉",
}

WORD_MAP = {
    "the": "",
    "a": "",
    "an": "",
    "and": "",
    "or": "",
    "with": "",
    "on": "",
    "to": "",
    "from": "",
    "for": "",
    "of": "",
    "into": "",
    "no": "无",
    "using": "",
    "plie": "相扑站距",
    "speed": "速度",
    "split": "分腿",
    "barbell": "杠铃",
    "dumbbell": "哑铃",
    "dumbbells": "哑铃",
    "two": "双",
    "one": "单",
    "arm": "臂",
    "arms": "臂",
    "leg": "腿",
    "legs": "腿",
    "hand": "手",
    "foot": "脚",
    "knee": "膝",
    "knees": "膝",
    "high": "高",
    "low": "低",
    "mid": "中",
    "middle": "中",
    "upper": "上",
    "lower": "下",
    "inner": "内",
    "outer": "外",
    "front": "前",
    "back": "背",
    "rear": "后",
    "side": "侧",
    "sides": "侧",
    "full": "完整",
    "half": "半",
    "wide": "宽距",
    "close": "窄距",
    "narrow": "窄",
    "neutral": "对握",
    "underhand": "反握",
    "overhand": "正握",
    "pronation": "旋前",
    "supination": "旋后",
    "internal": "内",
    "external": "外",
    "rotation": "旋转",
    "raise": "举起",
    "lift": "提起",
    "hold": "静撑",
    "extension": "伸展",
    "flexion": "屈曲",
    "twist": "转体",
    "swing": "摆荡",
    "kick": "踢",
    "kickback": "后踢",
    "thrust": "推",
    "bridge": "桥",
    "carry": "搬运",
    "walk": "走",
    "walking": "行走",
    "run": "跑",
    "jump": "跳",
    "jumping": "跳跃",
    "box": "箱式",
    "bench": "凳",
    "floor": "地板",
    "wall": "靠墙",
    "rack": "架",
    "rope": "绳",
    "bar": "杆",
    "ball": "球",
    "plate": "铃片",
    "handle": "把手",
    "stance": "站距",
    "grip": "握法",
    "hammer": "锤式",
    "preacher": "牧师凳",
    "concentration": "集中",
    "arnold": "阿诺德",
    "goblet": "高脚杯",
    "hack": "哈克",
    "pistol": "手枪",
    "zercher": "泽彻",
    "stiff": "直腿",
    "straight": "直",
    "bent": "屈",
    "behind": "颈后",
    "neck": "颈",
    "chest": "胸",
    "shoulder": "肩",
    "shoulders": "肩",
    "abs": "腹",
    "core": "核心",
    "glute": "臀",
    "glutes": "臀",
    "hamstring": "腘绳",
    "hamstrings": "腘绳",
    "quad": "股四",
    "quads": "股四",
    "calf": "小腿",
    "calves": "小腿",
    "trap": "斜方",
    "traps": "斜方",
    "lat": "背阔",
    "lats": "背阔",
    "delt": "三角肌",
    "delts": "三角肌",
    "bicep": "二头",
    "biceps": "二头",
    "tricep": "三头",
    "triceps": "三头",
    "forearm": "前臂",
    "forearms": "前臂",
    "ab": "腹",
    "abdominal": "腹",
    "pelvic": "骨盆",
    "tilt": "倾斜",
    "pyramid": "金字塔",
    "atlas": "阿特拉斯",
    "stone": "石",
    "stones": "石",
    "axle": "粗杠",
    "deficit": "垫高",
    "chain": "铁链",
    "chains": "铁链",
    "keg": "酒桶",
    "load": "搬运",
    "hug": "抱",
    "cat": "猫式",
    "cow": "牛式",
    "dancer": "舞者",
    "child": "婴儿",
    "pose": "式",
    "crossover": "交叉",
    "cross": "交叉",
    "reverse": "反向",
    "inverted": "倒立",
    "suspended": "悬挂",
    "kneeling": "跪姿",
    "prone": "俯卧",
    "supine": "仰卧",
    "isometric": "等长",
    "dynamic": "动态",
    "static": "静态",
    "plyo": "增强式",
    "olympic": "举重",
    "power": "爆发",
    "clean": "高翻",
    "jerk": "挺举",
    "snatch": "抓举",
    "tire": "轮胎",
    "sled": "雪橇",
    "landmine": "地雷架",
    "hex": "六角",
    "v": "V字",
    "up": "",
    "down": "",
    "out": "",
    "in": "",
    "over": "",
    "under": "",
    "s": "",
}


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "exercise"


def translate_name(english: str, equipment_zh: str = "") -> str:
    """Greedy multi-token phrase map -> Chinese; fallback keep English with equip tag."""
    if english in EXACT_NAME_OVERRIDES:
        return EXACT_NAME_OVERRIDES[english]
    tokens = re.findall(r"[A-Za-z]+|\d+", english)
    if not tokens:
        return english
    lower_tokens = [t.lower() for t in tokens]
    mapped: list[str] = []
    i = 0
    while i < len(lower_tokens):
        matched = False
        for n in range(min(4, len(lower_tokens) - i), 0, -1):
            phrase = " ".join(lower_tokens[i : i + n])
            if phrase in PHRASE_DICT:
                mapped.append(PHRASE_DICT[phrase])
                i += n
                matched = True
                break
        if matched:
            continue
        w = lower_tokens[i]
        zh = WORD_MAP.get(w)
        if zh is None:
            mapped.append(tokens[i])  # keep original casing token
        elif zh:
            mapped.append(zh)
        i += 1
    zh_name = "".join(mapped)
    zh_name = re.sub(r"\s+", "", zh_name)
    chinese_chars = sum(1 for c in zh_name if "\u4e00" <= c <= "\u9fff")
    if chinese_chars < 2:
        prefix = equipment_zh if equipment_zh and equipment_zh not in {"其他", "无"} else ""
        return f"{prefix}·{english}" if prefix else english
    # too short weird remnants
    if len(zh_name) <= 1:
        return f"{equipment_zh}·{english}" if equipment_zh else english
    return zh_name


def tips_from_instructions(instructions: list | None) -> str:
    if not instructions:
        return ""
    text = " ".join(str(x).strip() for x in instructions if str(x).strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180]


def muscle_zh(primary: list | None) -> str:
    if not primary:
        return "全身"
    mapped = [MUSCLE_MAP.get(m, m) for m in primary]
    # keep primary only (first), or join top 2 if useful
    if len(mapped) == 1:
        return mapped[0]
    return f"{mapped[0]}/{mapped[1]}"


def image_url(images: list | None, ex_id: str) -> str:
    if images:
        rel = images[0].lstrip("/")
        return IMAGE_BASE + rel
    # fallback guess
    return IMAGE_BASE + f"{ex_id}/0.jpg"


def fetch_source(path: Path | None) -> list[dict]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    print(f"Downloading {SOURCE_URL} ...")
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "fitness-agent/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_bytes(raw)
    return json.loads(raw.decode("utf-8"))


def load_legacy() -> list[dict]:
    if not LEGACY_PATH.exists():
        return []
    try:
        data = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    # If already rebuilt (has name_en), still use as overrides by Chinese name
    return data if isinstance(data, list) else []


def build(source: list[dict], legacy: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    by_slug: dict[str, dict] = {}
    for ex in legacy:
        eid = str(ex.get("id") or "").strip()
        name = str(ex.get("name") or "").strip()
        if eid:
            by_id[eid] = ex
            by_slug[slugify(eid)] = ex
        if name:
            by_name[name] = ex
        name_en = str(ex.get("name_en") or "").strip()
        if name_en:
            by_name[name_en.lower()] = ex
            by_slug[slugify(name_en)] = ex

    out: list[dict] = []
    seen_ids: set[str] = set()
    seen_zh: dict[str, int] = {}  # chinese name -> index in out

    for raw in source:
        en_name = str(raw.get("name") or "").strip()
        if not en_name:
            continue
        eid = str(raw.get("id") or slugify(en_name))
        if eid in seen_ids:
            continue
        seen_ids.add(eid)

        equip = EQUIP_MAP.get((raw.get("equipment") or "other").lower(), "其他")
        zh_name = translate_name(en_name, equip)
        muscle = muscle_zh(raw.get("primaryMuscles"))
        tips = tips_from_instructions(raw.get("instructions"))
        img = image_url(raw.get("images"), eid)

        legacy_hit = (
            by_id.get(eid)
            or by_slug.get(slugify(eid))
            or by_slug.get(slugify(en_name))
            or by_name.get(en_name.lower())
            or by_name.get(zh_name)
        )
        if legacy_hit:
            ln = str(legacy_hit.get("name") or "")
            if re.search(r"[\u4e00-\u9fff]", ln):
                zh_name = ln
            lt = str(legacy_hit.get("tips") or "")
            if lt and re.search(r"[\u4e00-\u9fff]", lt):
                tips = lt
            if legacy_hit.get("muscle"):
                muscle = str(legacy_hit["muscle"])
            le = str(legacy_hit.get("equipment") or "")
            if re.search(r"[\u4e00-\u9fff]", le):
                equip = le.split("/")[0]
            if legacy_hit.get("image_url"):
                img = str(legacy_hit["image_url"])

        item = {
            "id": eid,
            "name": zh_name,
            "name_en": en_name,
            "muscle": muscle,
            "equipment": equip,
            "tips": tips,
            "image_url": img,
        }
        # prefer entry with image when Chinese name collides
        if zh_name in seen_zh:
            prev = out[seen_zh[zh_name]]
            if not prev.get("image_url") and img:
                out[seen_zh[zh_name]] = item
            continue
        seen_zh[zh_name] = len(out)
        out.append(item)

    for ex in legacy:
        eid = str(ex.get("id") or slugify(str(ex.get("name") or "ex")))
        name = str(ex.get("name") or "").strip()
        if not name:
            continue
        if eid in seen_ids or slugify(eid) in {slugify(x) for x in seen_ids}:
            continue
        if name in seen_zh:
            # merge tips into existing if missing chinese tips
            idx = seen_zh[name]
            if ex.get("tips") and not re.search(
                r"[\u4e00-\u9fff]", str(out[idx].get("tips") or "")
            ):
                out[idx]["tips"] = str(ex["tips"])
            continue
        seen_ids.add(eid)
        seen_zh[name] = len(out)
        out.append(
            {
                "id": eid,
                "name": name,
                "name_en": str(ex.get("name_en") or ""),
                "muscle": str(ex.get("muscle") or "全身"),
                "equipment": str(ex.get("equipment") or "其他").split("/")[0],
                "tips": str(ex.get("tips") or ""),
                "image_url": str(ex.get("image_url") or ""),
            }
        )

    out.sort(key=lambda x: (x.get("muscle") or "", x.get("name") or ""))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=None, help="Local free-exercise-db JSON")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    # Prefer /tmp cache from earlier download if present
    tmp = Path("/tmp/free_exercises.json")
    source_path = args.source
    if source_path is None and tmp.exists():
        source_path = tmp

    source = fetch_source(source_path)
    # If reading from legacy OUT that we will overwrite, snapshot first
    legacy_backup = ROOT / "data" / "exercises_legacy_zh.json"
    if LEGACY_PATH.exists() and not legacy_backup.exists():
        # only backup if current file looks like old Chinese-only (no name_en majority)
        cur = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
        has_en = sum(1 for e in cur if e.get("name_en"))
        if has_en < max(10, len(cur) // 2):
            legacy_backup.write_text(
                json.dumps(cur, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Backed up legacy Chinese library -> {legacy_backup}")

    legacy = []
    if legacy_backup.exists():
        legacy = json.loads(legacy_backup.read_text(encoding="utf-8"))
    else:
        legacy = load_legacy()

    built = build(source, legacy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(built, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    equips = sorted({e["equipment"] for e in built})
    muscles = sorted({e["muscle"] for e in built})
    print(f"Wrote {len(built)} exercises -> {args.out}")
    print(f"Equipment ({len(equips)}): {', '.join(equips)}")
    print(f"Muscles ({len(muscles)}): {', '.join(muscles[:20])}...")


if __name__ == "__main__":
    main()
