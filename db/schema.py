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
    "age": None,
    "experience": "中级",
    "days_per_week": 4,
    "session_minutes": 60,
    "activity_level": "轻度活动",
    "preferred_split": "随教练",
    "equipment": "健身房",
    "injuries": "",
    "diet_prefs": "",
    "sleep_hours": None,
    "weight_kg": None,
    "target_weight_kg": None,
    "body_fat_pct": None,
    "target_body_fat_pct": None,
    "height_cm": None,
    "calorie_target": None,
    "protein_target_g": None,
    "carb_target_g": None,
    "fat_target_g": None,
    "calorie_target_rest": None,
    "protein_target_g_rest": None,
    "carb_target_g_rest": None,
    "fat_target_g_rest": None,
    "notes": "",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    goal TEXT NOT NULL DEFAULT '增肌',
    goal_detail TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    age INTEGER,
    experience TEXT NOT NULL DEFAULT '中级',
    days_per_week INTEGER NOT NULL DEFAULT 4,
    session_minutes INTEGER NOT NULL DEFAULT 60,
    activity_level TEXT NOT NULL DEFAULT '轻度活动',
    preferred_split TEXT NOT NULL DEFAULT '随教练',
    equipment TEXT NOT NULL DEFAULT '健身房',
    injuries TEXT NOT NULL DEFAULT '',
    diet_prefs TEXT NOT NULL DEFAULT '',
    sleep_hours REAL,
    weight_kg REAL,
    target_weight_kg REAL,
    body_fat_pct REAL,
    target_body_fat_pct REAL,
    height_cm REAL,
    calorie_target REAL,
    protein_target_g REAL,
    carb_target_g REAL,
    fat_target_g REAL,
    calorie_target_rest REAL,
    protein_target_g_rest REAL,
    carb_target_g_rest REAL,
    fat_target_g_rest REAL,
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

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '新对话',
    summary TEXT NOT NULL DEFAULT '',
    summary_upto_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS body_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    weight_kg REAL,
    body_fat_pct REAL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_sets_workout ON sets(workout_id);
CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_meals_date ON meals(date);
CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(date);
CREATE INDEX IF NOT EXISTS idx_body_metrics_date ON body_metrics(date);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # timeout: wait on lock when coach tools write in parallel
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL allows concurrent readers + one writer (LangChain tool threads)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    return conn


def _migrate_profile_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(profile)").fetchall()}
    migrations = {
        "goal_detail": "ALTER TABLE profile ADD COLUMN goal_detail TEXT NOT NULL DEFAULT ''",
        "gender": "ALTER TABLE profile ADD COLUMN gender TEXT NOT NULL DEFAULT ''",
        "age": "ALTER TABLE profile ADD COLUMN age INTEGER",
        "session_minutes": (
            "ALTER TABLE profile ADD COLUMN session_minutes INTEGER NOT NULL DEFAULT 60"
        ),
        "activity_level": (
            "ALTER TABLE profile ADD COLUMN activity_level TEXT NOT NULL DEFAULT '轻度活动'"
        ),
        "preferred_split": (
            "ALTER TABLE profile ADD COLUMN preferred_split TEXT NOT NULL DEFAULT '随教练'"
        ),
        "diet_prefs": "ALTER TABLE profile ADD COLUMN diet_prefs TEXT NOT NULL DEFAULT ''",
        "sleep_hours": "ALTER TABLE profile ADD COLUMN sleep_hours REAL",
        "target_weight_kg": "ALTER TABLE profile ADD COLUMN target_weight_kg REAL",
        "body_fat_pct": "ALTER TABLE profile ADD COLUMN body_fat_pct REAL",
        "target_body_fat_pct": "ALTER TABLE profile ADD COLUMN target_body_fat_pct REAL",
        "calorie_target": "ALTER TABLE profile ADD COLUMN calorie_target REAL",
        "protein_target_g": "ALTER TABLE profile ADD COLUMN protein_target_g REAL",
        "carb_target_g": "ALTER TABLE profile ADD COLUMN carb_target_g REAL",
        "fat_target_g": "ALTER TABLE profile ADD COLUMN fat_target_g REAL",
        "calorie_target_rest": "ALTER TABLE profile ADD COLUMN calorie_target_rest REAL",
        "protein_target_g_rest": "ALTER TABLE profile ADD COLUMN protein_target_g_rest REAL",
        "carb_target_g_rest": "ALTER TABLE profile ADD COLUMN carb_target_g_rest REAL",
        "fat_target_g_rest": "ALTER TABLE profile ADD COLUMN fat_target_g_rest REAL",
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


def _migrate_chat_sessions(conn: sqlite3.Connection) -> None:
    """Ensure chat_sessions exists and chat_messages.session_id is backfilled."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '新对话',
            summary TEXT NOT NULL DEFAULT '',
            summary_upto_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    msg_cols = {row[1] for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
    if "session_id" not in msg_cols:
        conn.execute("ALTER TABLE chat_messages ADD COLUMN session_id INTEGER")

    orphan = conn.execute(
        """
        SELECT COUNT(*) AS n FROM chat_messages
        WHERE session_id IS NULL
        """
    ).fetchone()["n"]
    session_count = conn.execute("SELECT COUNT(*) AS n FROM chat_sessions").fetchone()["n"]

    if orphan or session_count == 0:
        # Prefer attaching orphans to an existing default session; else create one.
        default = conn.execute(
            "SELECT id FROM chat_sessions ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if default is None:
            cur = conn.execute(
                "INSERT INTO chat_sessions (title) VALUES (?)",
                ("默认对话",),
            )
            session_id = int(cur.lastrowid)
        else:
            session_id = int(default["id"])
        if orphan:
            conn.execute(
                "UPDATE chat_messages SET session_id = ? WHERE session_id IS NULL",
                (session_id,),
            )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at)"
    )


def init_db(db_path: Path | None = None) -> None:
    """Create tables and ensure a default profile row exists."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        _migrate_profile_columns(conn)
        _migrate_workout_columns(conn)
        _migrate_chat_sessions(conn)
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
