#!/usr/bin/env python3
"""Build data/exercises.json from free-exercise-db + local Chinese overrides + extras.

Usage:
  python scripts/build_exercises.py
  python scripts/build_exercises.py --source /path/to/exercises.json

Curated bodyweight / variations live in data/exercises_extra.json and are merged last.
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
EXTRA_PATH = ROOT / "data" / "exercises_extra.json"
CACHE_PATH = ROOT / "data" / "_free_exercises_cache.json"

# Prefer jsDelivr (more reachable than raw.githubusercontent in some networks)
SOURCE_URL = (
    "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/dist/exercises.json"
)
IMAGE_BASE = (
    "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/exercises/"
)

# 纠正已有烂译（按 id 或当前中文名）
NAME_FIX_BY_ID: dict[str, str] = {
    "Superman": "超人式",
    "Cat_Stretch": "猫牛",
    "Worlds_Greatest_Stretch": "世界最伟大拉伸",
    "Pushups": "俯卧撑",
    "Wide_Pushup": "宽距俯卧撑",
}
NAME_FIX_BY_NAME: dict[str, str] = {
    "自重·Superman": "超人式",
    "猫牛式": "猫牛",
    "世界最好拉伸": "世界最伟大拉伸",
    "俯卧撑宽距": "宽距俯卧撑",
    "Handstand俯卧撑": "倒立俯卧撑",
    "Clock俯卧撑": "时钟俯卧撑",
}

# 旧中文库 id → free-exercise-db id（用于补配图、合并重复）
LEGACY_ID_TO_FREE: dict[str, str] = {
    "incline_press": "Barbell_Incline_Bench_Press_-_Medium_Grip",
    "decline_press": "Decline_Barbell_Bench_Press",
    "lateral_raise": "Side_Lateral_Raise",
    "cable_lateral_raise": "Cable_Seated_Lateral_Raise",
    "adduction_machine": "Thigh_Adductor",
    "abduction_machine": "Thigh_Abductor",
    "front_raise": "Front_Dumbbell_Raise",
    "reverse_wrist_curl": "Palms-Down_Wrist_Curl_Over_A_Bench",
    "wrist_curl": "Palms-Up_Barbell_Wrist_Curl_Over_A_Bench",
    "rear_delt_machine": "Reverse_Flyes",
    "deadlift": "Barbell_Deadlift",
    "kettlebell_swing": "One-Arm_Kettlebell_Swings",
    "calf_raise": "Standing_Calf_Raises",
    "donkey_calf_raise": "Donkey_Calf_Raises",
    "foam_roll": "Hamstring-SMR",
    "shrug": "Barbell_Shrug",
    "bike": "Recumbent_Bike",
    "elliptical": "Elliptical_Trainer",
    "treadmill": "Jogging_Treadmill",
    "jump_rope": "Rope_Jumping",
    "row_machine": "Rowing_Stationary",
    "stair_climber": "Stairmaster",
    "incline_walk": "Walking_Treadmill",
    "side_plank": "Side_Bridge",
    "ab_wheel": "Barbell_Ab_Rollout_-_On_Knees",
    "crunch": "Cable_Crunch",
    "hanging_knee_raise": "Hanging_Leg_Raise",
    "mountain_climber": "Mountain_Climbers",
    "world_greatest_stretch": "Worlds_Greatest_Stretch",
    "cat_cow": "Cat_Stretch",
    "hip_flexor_stretch": "Kneeling_Hip_Flexor",
    "box_jump": "Box_Jump_Multiple_Response",
    "leg_extension": "Leg_Extensions",
    "machine_shoulder_press": "Machine_Shoulder_Military_Press",
    "ohp": "Standing_Military_Press",
    "arnold_press": "Arnold_Dumbbell_Press",
    "upright_row": "Upright_Barbell_Row",
    "cuba_press": "Cuban_Press",
    "skull_crusher": "Lying_Triceps_Press",
    "bench_dip": "Bench_Dips",
    "tricep_dip": "Dips_-_Triceps_Version",
    "tricep_pushdown": "Triceps_Pushdown",
    "rope_pushdown": "Triceps_Pushdown_-_Rope_Attachment",
    "overhead_tricep_ext": "Cable_Rope_Overhead_Triceps_Extension",
    "close_grip_bench": "Close-Grip_Barbell_Bench_Press",
    "incline_curl": "Dumbbell_Prone_Incline_Curl",
    "concentration_curl": "Concentration_Curls",
    "dumbbell_curl": "Dumbbell_Bicep_Curl",
    "cable_curl": "High_Cable_Curls",
    "hammer_curl": "Hammer_Curls",
    "t_bar_row": "T-Bar_Row_with_Handle",
    "seated_row": "Seated_Cable_Rows",
    "pull_up": "Pullups",
    "barbell_row": "Bent_Over_Barbell_Row",
    "pendlay_row": "Bent_Over_Barbell_Row",
    "close_grip_pulldown": "Wide-Grip_Lat_Pulldown",
    "cable_row": "Seated_Cable_Rows",
    "chest_supported_row": "Lying_T-Bar_Row",
    "assisted_pull_up": "Band_Assisted_Pull-Up",
    "lat_pulldown": "Wide-Grip_Lat_Pulldown",
    "rack_pull": "Rack_Pulls",
    "push_up": "Pushups",
    "machine_chest_press": "Butterfly",
    "bench_press": "Barbell_Bench_Press_-_Medium_Grip",
    "cable_fly": "Cable_Crossover",
    "pec_deck": "Butterfly",
    "chest_dip": "Dips_-_Chest_Version",
    "diamond_push_up": "Close-Grip_Push-Up_off_of_a_Dumbbell",
    "landmine_press": "Landmine_Linear_Jammer",
    "stiff_leg_deadlift": "Stiff-Legged_Barbell_Deadlift",
    "leg_curl": "Lying_Leg_Curls",
    "step_up": "Dumbbell_Step_Ups",
    "bulgarian_split_squat": "Split_Squat_with_Dumbbells",
    "front_squat": "Front_Barbell_Squat",
    "reverse_lunge": "Crossover_Reverse_Lunge",
    "walking_lunge": "Dumbbell_Lunges",
    "dumbbell_rdl": "Stiff-Legged_Dumbbell_Deadlift",
    "cable_kickback": "One-Legged_Cable_Kickback",
    "hip_thrust": "Barbell_Hip_Thrust",
    "glute_bridge": "Barbell_Glute_Bridge",
    "barbell_squat": "Barbell_Squat",
    "goblet_squat": "Goblet_Squat",
    "hack_squat": "Hack_Squat",
    "leg_press": "Leg_Press",
    "dumbbell_press": "Dumbbell_Bench_Press",
    "incline_dumbbell_press": "Incline_Dumbbell_Press",
    "seated_leg_curl": "Seated_Leg_Curl",
    "seated_calf_raise": "Seated_Calf_Raise",
    "good_morning": "Good_Morning",
    "romanian_deadlift": "Romanian_Deadlift",
    "battle_rope": "Battling_Ropes",
    "sauna_walk": "Walking_Treadmill",
}

# free-db 没有的少数动作：外链配图（Wikimedia 用原图，勿用已失效的 /thumb/640px-）
EXTERNAL_IMAGE_URLS: dict[str, str] = {
    "burpee": "https://upload.wikimedia.org/wikipedia/commons/9/95/Burpee_1_Neutral_Position.jpg",
    "bird_dog": "https://upload.wikimedia.org/wikipedia/commons/8/82/Bird_dog_exercise.jpg",
    # 与猫牛式相近的活动度动作，复用 free-db 猫式配图
    "thoracic_opener": (
        "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/"
        "exercises/Cat_Stretch/0.jpg"
    ),
}

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

    free_by_id = {str(e.get("id") or ""): e for e in source if e.get("id")}

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
        if zh_name in seen_zh:
            # Keep variation: disambiguate instead of silently dropping
            base = zh_name
            suffix = equip if equip and equip not in base else (en_name.split()[0] if en_name else eid)
            candidate = f"{base}（{suffix}）"
            n = 2
            while candidate in seen_zh:
                candidate = f"{base}（{suffix}{n}）"
                n += 1
            item["name"] = candidate
            zh_name = candidate
        seen_zh[zh_name] = len(out)
        out.append(item)

    out_by_id = {item["id"]: i for i, item in enumerate(out)}

    for ex in legacy:
        eid = str(ex.get("id") or slugify(str(ex.get("name") or "ex")))
        name = str(ex.get("name") or "").strip()
        if not name:
            continue

        free_id = LEGACY_ID_TO_FREE.get(eid) or LEGACY_ID_TO_FREE.get(slugify(eid))
        if free_id and free_id in out_by_id:
            idx = out_by_id[free_id]
            # 把中文习惯名/要点合并进已有配图条目，避免重复无图项
            if re.search(r"[\u4e00-\u9fff]", name):
                old = out[idx]["name"]
                out[idx]["name"] = name
                if old in seen_zh and seen_zh[old] == idx:
                    del seen_zh[old]
                seen_zh[name] = idx
            lt = str(ex.get("tips") or "")
            if lt and re.search(r"[\u4e00-\u9fff]", lt):
                out[idx]["tips"] = lt
            if ex.get("muscle"):
                out[idx]["muscle"] = str(ex["muscle"])
            continue

        if eid in seen_ids or slugify(eid) in {slugify(x) for x in seen_ids}:
            continue
        if name in seen_zh:
            idx = seen_zh[name]
            if ex.get("tips") and not re.search(
                r"[\u4e00-\u9fff]", str(out[idx].get("tips") or "")
            ):
                out[idx]["tips"] = str(ex["tips"])
            if not out[idx].get("image_url"):
                if free_id and free_id in free_by_id:
                    out[idx]["image_url"] = image_url(
                        free_by_id[free_id].get("images"), free_id
                    )
                elif eid in EXTERNAL_IMAGE_URLS:
                    out[idx]["image_url"] = EXTERNAL_IMAGE_URLS[eid]
            continue

        img = ""
        name_en = str(ex.get("name_en") or "")
        if free_id and free_id in free_by_id:
            img = image_url(free_by_id[free_id].get("images"), free_id)
            name_en = name_en or str(free_by_id[free_id].get("name") or "")
        elif eid in EXTERNAL_IMAGE_URLS:
            img = EXTERNAL_IMAGE_URLS[eid]
        elif name in EXTERNAL_IMAGE_URLS:
            img = EXTERNAL_IMAGE_URLS[name]

        seen_ids.add(eid)
        seen_zh[name] = len(out)
        out.append(
            {
                "id": eid,
                "name": name,
                "name_en": name_en,
                "muscle": str(ex.get("muscle") or "全身"),
                "equipment": str(ex.get("equipment") or "其他").split("/")[0],
                "tips": str(ex.get("tips") or ""),
                "image_url": img,
            }
        )

    apply_name_fixes(out)
    merge_extras(out)
    out.sort(key=lambda x: (x.get("muscle") or "", x.get("name") or ""))
    return out


def apply_name_fixes(out: list[dict]) -> None:
    """Normalize a few known bad Chinese names in place."""
    used = {str(e.get("name") or "") for e in out}
    for ex in out:
        eid = str(ex.get("id") or "")
        old = str(ex.get("name") or "")
        new = NAME_FIX_BY_ID.get(eid) or NAME_FIX_BY_NAME.get(old)
        if not new or new == old:
            continue
        if new in used and new != old:
            # keep unique
            candidate = f"{new}（{ex.get('equipment') or eid}）"
            n = 2
            while candidate in used:
                candidate = f"{new}（{n}）"
                n += 1
            new = candidate
        used.discard(old)
        used.add(new)
        ex["name"] = new


def merge_extras(out: list[dict]) -> None:
    """Append/override from data/exercises_extra.json (local curated bodyweight & variations)."""
    if not EXTRA_PATH.exists():
        return
    try:
        extras = json.loads(EXTRA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(extras, list):
        return

    by_id = {str(e.get("id") or ""): i for i, e in enumerate(out) if e.get("id")}
    used_names = {str(e.get("name") or "") for e in out}

    for raw in extras:
        if not isinstance(raw, dict):
            continue
        eid = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not eid or not name:
            continue
        item = {
            "id": eid,
            "name": name,
            "name_en": str(raw.get("name_en") or ""),
            "muscle": str(raw.get("muscle") or "全身"),
            "equipment": str(raw.get("equipment") or "自重"),
            "tips": str(raw.get("tips") or ""),
            "image_url": str(raw.get("image_url") or ""),
        }
        if eid in by_id:
            idx = by_id[eid]
            prev = out[idx]
            for key in ("name", "name_en", "muscle", "equipment", "tips"):
                if item.get(key):
                    prev[key] = item[key]
            if item.get("image_url"):
                prev["image_url"] = item["image_url"]
            continue

        # Already have this Chinese name (e.g. renamed from free-db) → skip
        if name in used_names:
            continue

        by_id[eid] = len(out)
        used_names.add(name)
        out.append(item)


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
