"""SQLite schema and connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "fitness.db"
EXERCISES_PATH = DATA_DIR / "exercises.json"

DEFAULT_PROFILE = {
    "goal": "增肌",
    "goal_detail": "",
    "gender": "",
    "experience": "中级",
    "days_per_week": 4,
    "equipment": "健身房",
    "injuries": "",
    "weight_kg": None,
    "target_weight_kg": None,
    "body_fat_pct": None,
    "height_cm": None,
    "calorie_target": None,
    "protein_target_g": None,
    "carb_target_g": None,
    "fat_target_g": None,
    "notes": "",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    goal TEXT NOT NULL DEFAULT '增肌',
    goal_detail TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    experience TEXT NOT NULL DEFAULT '中级',
    days_per_week INTEGER NOT NULL DEFAULT 4,
    equipment TEXT NOT NULL DEFAULT '健身房',
    injuries TEXT NOT NULL DEFAULT '',
    weight_kg REAL,
    target_weight_kg REAL,
    body_fat_pct REAL,
    height_cm REAL,
    calorie_target REAL,
    protein_target_g REAL,
    carb_target_g REAL,
    fat_target_g REAL,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '当前计划',
    content_json TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'planned',
    notes TEXT NOT NULL DEFAULT '',
    calories_burned REAL,
    calories_burned_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL,
    exercise_name TEXT NOT NULL,
    set_index INTEGER NOT NULL DEFAULT 1,
    weight_kg REAL,
    reps INTEGER,
    rpe REAL,
    completed INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (workout_id) REFERENCES workouts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    meal_type TEXT NOT NULL DEFAULT '正餐',
    name TEXT NOT NULL,
    calories REAL,
    protein_g REAL,
    carb_g REAL,
    fat_g REAL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    stats_json TEXT NOT NULL DEFAULT '{}',
    user_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_sets_workout ON sets(workout_id);
CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_meals_date ON meals(date);
CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(date);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_profile_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(profile)").fetchall()}
    migrations = {
        "goal_detail": "ALTER TABLE profile ADD COLUMN goal_detail TEXT NOT NULL DEFAULT ''",
        "gender": "ALTER TABLE profile ADD COLUMN gender TEXT NOT NULL DEFAULT ''",
        "target_weight_kg": "ALTER TABLE profile ADD COLUMN target_weight_kg REAL",
        "body_fat_pct": "ALTER TABLE profile ADD COLUMN body_fat_pct REAL",
        "calorie_target": "ALTER TABLE profile ADD COLUMN calorie_target REAL",
        "protein_target_g": "ALTER TABLE profile ADD COLUMN protein_target_g REAL",
        "carb_target_g": "ALTER TABLE profile ADD COLUMN carb_target_g REAL",
        "fat_target_g": "ALTER TABLE profile ADD COLUMN fat_target_g REAL",
    }
    for col, sql in migrations.items():
        if col not in cols:
            conn.execute(sql)


def _migrate_workout_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(workouts)").fetchall()}
    migrations = {
        "calories_burned": "ALTER TABLE workouts ADD COLUMN calories_burned REAL",
        "calories_burned_note": (
            "ALTER TABLE workouts ADD COLUMN calories_burned_note TEXT NOT NULL DEFAULT ''"
        ),
    }
    for col, sql in migrations.items():
        if col not in cols:
            conn.execute(sql)


def init_db(db_path: Path | None = None) -> None:
    """Create tables and ensure a default profile row exists."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        _migrate_profile_columns(conn)
        _migrate_workout_columns(conn)
        row = conn.execute("SELECT id FROM profile WHERE id = 1").fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO profile (
                    id, goal, goal_detail, gender, experience, days_per_week, equipment,
                    injuries, weight_kg, target_weight_kg, height_cm, notes
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_PROFILE["goal"],
                    DEFAULT_PROFILE["goal_detail"],
                    DEFAULT_PROFILE["gender"],
                    DEFAULT_PROFILE["experience"],
                    DEFAULT_PROFILE["days_per_week"],
                    DEFAULT_PROFILE["equipment"],
                    DEFAULT_PROFILE["injuries"],
                    DEFAULT_PROFILE["weight_kg"],
                    DEFAULT_PROFILE["target_weight_kg"],
                    DEFAULT_PROFILE["height_cm"],
                    DEFAULT_PROFILE["notes"],
                ),
            )
        conn.commit()
    finally:
        conn.close()
