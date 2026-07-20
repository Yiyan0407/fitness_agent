"""CRUD helpers for the fitness SQLite database."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from db.schema import EXERCISES_PATH, get_connection, init_db


WEEKDAY_KEYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

WEEKDAY_CN = {
    "monday": "周一",
    "tuesday": "周二",
    "wednesday": "周三",
    "thursday": "周四",
    "friday": "周五",
    "saturday": "周六",
    "sunday": "周日",
}


class Repository:
    def __init__(self, db_path: Path | None = None) -> None:
        init_db(db_path)
        self.db_path = db_path
        self.conn = get_connection(db_path)

    def close(self) -> None:
        self.conn.close()

    # --- profile ---

    def get_profile(self) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        return dict(row) if row else {}

    def update_profile(self, **fields: Any) -> dict[str, Any]:
        allowed = {
            "goal",
            "goal_detail",
            "gender",
            "experience",
            "days_per_week",
            "equipment",
            "injuries",
            "weight_kg",
            "target_weight_kg",
            "body_fat_pct",
            "height_cm",
            "calorie_target",
            "protein_target_g",
            "carb_target_g",
            "fat_target_g",
            "notes",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_profile()
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        self.conn.execute(
            f"UPDATE profile SET {sets}, updated_at = datetime('now', 'localtime') WHERE id = 1",
            values,
        )
        self.conn.commit()
        return self.get_profile()

    # --- plans ---

    def get_current_plan(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM plans WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["content"] = json.loads(data.pop("content_json"))
        return data

    def save_plan(self, content: dict[str, Any] | str, name: str = "当前计划") -> dict[str, Any]:
        if isinstance(content, str):
            parsed = json.loads(content)
        else:
            parsed = content
        self.conn.execute("UPDATE plans SET is_active = 0 WHERE is_active = 1")
        cur = self.conn.execute(
            """
            INSERT INTO plans (name, content_json, is_active)
            VALUES (?, ?, 1)
            """,
            (name, json.dumps(parsed, ensure_ascii=False)),
        )
        self.conn.commit()
        plan_id = cur.lastrowid
        row = self.conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        data = dict(row)
        data["content"] = json.loads(data.pop("content_json"))
        return data

    def get_plan_for_date(self, target: date | None = None) -> dict[str, Any] | None:
        plan = self.get_current_plan()
        if not plan:
            return None
        target = target or date.today()
        key = WEEKDAY_KEYS[target.weekday()]
        day = plan["content"].get(key) or plan["content"].get(WEEKDAY_CN[key])
        if day is None:
            return {"date": target.isoformat(), "weekday": key, "rest": True, "exercises": []}
        if isinstance(day, dict):
            return {
                "date": target.isoformat(),
                "weekday": key,
                "rest": bool(day.get("rest", False)),
                "name": day.get("name", ""),
                "exercises": day.get("exercises", []),
            }
        return {"date": target.isoformat(), "weekday": key, "rest": True, "exercises": []}

    # --- workouts / sets ---

    def get_or_create_workout(self, target: date | None = None) -> dict[str, Any]:
        target = target or date.today()
        ds = target.isoformat()
        row = self.conn.execute("SELECT * FROM workouts WHERE date = ?", (ds,)).fetchone()
        if row:
            return dict(row)
        cur = self.conn.execute(
            "INSERT INTO workouts (date, status) VALUES (?, 'planned')",
            (ds,),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM workouts WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    def update_workout(
        self,
        workout_id: int,
        status: str | None = None,
        notes: str | None = None,
        calories_burned: float | None = None,
        calories_burned_note: str | None = None,
        clear_calories_burned: bool = False,
    ) -> dict[str, Any]:
        if status is not None:
            self.conn.execute(
                "UPDATE workouts SET status = ? WHERE id = ?", (status, workout_id)
            )
        if notes is not None:
            self.conn.execute(
                "UPDATE workouts SET notes = ? WHERE id = ?", (notes, workout_id)
            )
        if clear_calories_burned:
            self.conn.execute(
                """
                UPDATE workouts
                SET calories_burned = NULL, calories_burned_note = ''
                WHERE id = ?
                """,
                (workout_id,),
            )
        else:
            if calories_burned is not None:
                self.conn.execute(
                    "UPDATE workouts SET calories_burned = ? WHERE id = ?",
                    (float(calories_burned), workout_id),
                )
            if calories_burned_note is not None:
                self.conn.execute(
                    "UPDATE workouts SET calories_burned_note = ? WHERE id = ?",
                    (calories_burned_note, workout_id),
                )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM workouts WHERE id = ?", (workout_id,)
        ).fetchone()
        return dict(row)

    def get_sets(self, workout_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM sets WHERE workout_id = ? ORDER BY exercise_name, set_index, id",
            (workout_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_set(
        self,
        exercise_name: str,
        weight_kg: float | None = None,
        reps: int | None = None,
        rpe: float | None = None,
        set_index: int | None = None,
        completed: bool = True,
        notes: str = "",
        target_date: str | None = None,
    ) -> dict[str, Any]:
        target = date.fromisoformat(target_date) if target_date else date.today()
        workout = self.get_or_create_workout(target)
        if set_index is None:
            row = self.conn.execute(
                """
                SELECT COALESCE(MAX(set_index), 0) AS mx
                FROM sets WHERE workout_id = ? AND exercise_name = ?
                """,
                (workout["id"], exercise_name),
            ).fetchone()
            set_index = int(row["mx"]) + 1
        cur = self.conn.execute(
            """
            INSERT INTO sets (
                workout_id, exercise_name, set_index, weight_kg, reps, rpe, completed, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workout["id"],
                exercise_name,
                set_index,
                weight_kg,
                reps,
                rpe,
                1 if completed else 0,
                notes or "",
            ),
        )
        self.conn.execute(
            "UPDATE workouts SET status = 'in_progress' WHERE id = ? AND status = 'planned'",
            (workout["id"],),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM sets WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def update_set(self, set_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {
            "exercise_name",
            "set_index",
            "weight_kg",
            "reps",
            "rpe",
            "completed",
            "notes",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "completed" in updates:
            updates["completed"] = 1 if updates["completed"] else 0
        if not updates:
            row = self.conn.execute("SELECT * FROM sets WHERE id = ?", (set_id,)).fetchone()
            return dict(row) if row else {}
        sets_sql = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE sets SET {sets_sql} WHERE id = ?",
            [*updates.values(), set_id],
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM sets WHERE id = ?", (set_id,)).fetchone()
        return dict(row)

    def _seed_sets_from_day_plan(self, workout_id: int, day: dict[str, Any]) -> None:
        for ex in day.get("exercises") or []:
            name = ex.get("name") or ex.get("exercise") or ""
            if not name:
                continue
            sets_count = int(ex.get("sets", 3))
            reps = ex.get("reps")
            weight = ex.get("weight_kg") or ex.get("weight")
            reps_val = None
            if reps is not None:
                if isinstance(reps, int):
                    reps_val = reps
                else:
                    text = str(reps)
                    if text.isdigit():
                        reps_val = int(text)
                    elif "-" in text:
                        # "6-8" -> use lower bound as default target
                        left = text.split("-", 1)[0].strip()
                        if left.isdigit():
                            reps_val = int(left)
            for i in range(1, sets_count + 1):
                self.conn.execute(
                    """
                    INSERT INTO sets (
                        workout_id, exercise_name, set_index, weight_kg, reps, completed, notes
                    ) VALUES (?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        workout_id,
                        name,
                        i,
                        weight,
                        reps_val,
                        ex.get("notes", ""),
                    ),
                )

    @staticmethod
    def _plan_exercise_signature(day: dict[str, Any] | None) -> list[tuple[str, int]]:
        if not day or day.get("rest"):
            return []
        sig = []
        for ex in day.get("exercises") or []:
            name = ex.get("name") or ex.get("exercise") or ""
            if not name:
                continue
            sig.append((name, int(ex.get("sets", 3))))
        return sig

    @staticmethod
    def _sets_exercise_signature(sets: list[dict[str, Any]]) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        order: list[str] = []
        for s in sets:
            name = s["exercise_name"]
            if name not in counts:
                counts[name] = 0
                order.append(name)
            counts[name] += 1
        return [(name, counts[name]) for name in order]

    def ensure_today_sets_from_plan(
        self,
        target: date | None = None,
        *,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """Seed planned sets from the active plan.

        - No existing sets → seed from plan
        - force=True and no completed sets → rebuild from plan
        - Otherwise leave today's sets alone (preserve mid-workout edits)
        """
        target = target or date.today()
        workout = self.get_or_create_workout(target)
        existing = self.get_sets(workout["id"])
        day = self.get_plan_for_date(target)
        if not day or day.get("rest") or not day.get("exercises"):
            return existing

        completed_any = any(s.get("completed") for s in existing)

        if existing and not force:
            return existing

        if existing and force and completed_any:
            # Don't wipe a session that already has logged sets
            return existing

        if existing:
            self.conn.execute("DELETE FROM sets WHERE workout_id = ?", (workout["id"],))
            self.conn.execute(
                "UPDATE workouts SET status = 'planned' WHERE id = ?",
                (workout["id"],),
            )

        self._seed_sets_from_day_plan(workout["id"], day)
        self.conn.commit()
        return self.get_sets(workout["id"])

    def sync_today_from_plan_if_idle(self, target: date | None = None) -> list[dict[str, Any]]:
        """After plan template save: refresh today only if not started."""
        return self.ensure_today_sets_from_plan(target, force=True)

    def get_today_workout(self, target_date: str | None = None) -> dict[str, Any]:
        target = date.fromisoformat(target_date) if target_date else date.today()
        day_plan = self.get_plan_for_date(target)
        workout = self.get_or_create_workout(target)
        sets = self.ensure_today_sets_from_plan(target)
        # refresh workout row after possible status reset
        workout = self.get_or_create_workout(target)
        return {
            "date": target.isoformat(),
            "plan": day_plan,
            "workout": workout,
            "sets": sets,
        }

    def get_recent_history(self, days: int = 14) -> dict[str, Any]:
        since = (date.today() - timedelta(days=days)).isoformat()
        workouts = self.conn.execute(
            """
            SELECT w.*, COUNT(s.id) AS set_count,
                   SUM(CASE WHEN s.completed = 1 THEN 1 ELSE 0 END) AS completed_sets
            FROM workouts w
            LEFT JOIN sets s ON s.workout_id = w.id
            WHERE w.date >= ?
            GROUP BY w.id
            ORDER BY w.date DESC
            """,
            (since,),
        ).fetchall()
        sets = self.conn.execute(
            """
            SELECT s.*, w.date AS workout_date
            FROM sets s
            JOIN workouts w ON w.id = s.workout_id
            WHERE w.date >= ? AND s.completed = 1
            ORDER BY w.date DESC, s.id DESC
            """,
            (since,),
        ).fetchall()
        return {
            "days": days,
            "workouts": [dict(r) for r in workouts],
            "completed_sets": [dict(r) for r in sets],
        }

    def get_completion_last_n_days(self, n: int = 7) -> list[dict[str, Any]]:
        result = []
        for i in range(n - 1, -1, -1):
            d = date.today() - timedelta(days=i)
            row = self.conn.execute(
                """
                SELECT
                    COUNT(s.id) AS total,
                    SUM(CASE WHEN s.completed = 1 THEN 1 ELSE 0 END) AS done
                FROM workouts w
                LEFT JOIN sets s ON s.workout_id = w.id
                WHERE w.date = ?
                """,
                (d.isoformat(),),
            ).fetchone()
            total = int(row["total"] or 0)
            done = int(row["done"] or 0)
            result.append(
                {
                    "date": d.isoformat(),
                    "weekday": WEEKDAY_CN[WEEKDAY_KEYS[d.weekday()]],
                    "total_sets": total,
                    "completed_sets": done,
                    "done": total > 0 and done >= total,
                }
            )
        return result

    def get_exercise_progress(self, exercise_name: str | None = None, days: int = 60):
        since = (date.today() - timedelta(days=days)).isoformat()
        if exercise_name:
            rows = self.conn.execute(
                """
                SELECT w.date, s.exercise_name, MAX(s.weight_kg) AS max_weight,
                       MAX(s.reps) AS max_reps
                FROM sets s
                JOIN workouts w ON w.id = s.workout_id
                WHERE w.date >= ? AND s.completed = 1 AND s.exercise_name = ?
                      AND s.weight_kg IS NOT NULL
                GROUP BY w.date, s.exercise_name
                ORDER BY w.date
                """,
                (since, exercise_name),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT w.date, s.exercise_name, MAX(s.weight_kg) AS max_weight,
                       MAX(s.reps) AS max_reps
                FROM sets s
                JOIN workouts w ON w.id = s.workout_id
                WHERE w.date >= ? AND s.completed = 1 AND s.weight_kg IS NOT NULL
                GROUP BY w.date, s.exercise_name
                ORDER BY w.date
                """,
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all_logged_sets(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT s.*, w.date AS workout_date, w.status AS workout_status
            FROM sets s
            JOIN workouts w ON w.id = s.workout_id
            ORDER BY w.date DESC, s.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_calendar_days(
        self,
        start: date | None = None,
        end: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-day summaries for calendar rendering."""
        start = start or (date.today().replace(day=1) - timedelta(days=180))
        end = end or (date.today() + timedelta(days=60))
        rows = self.conn.execute(
            """
            SELECT
                w.date,
                w.status,
                w.notes,
                COUNT(s.id) AS total_sets,
                SUM(CASE WHEN s.completed = 1 THEN 1 ELSE 0 END) AS completed_sets,
                COUNT(DISTINCT s.exercise_name) AS exercise_count
            FROM workouts w
            LEFT JOIN sets s ON s.workout_id = w.id
            WHERE w.date >= ? AND w.date <= ?
            GROUP BY w.id
            ORDER BY w.date
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        by_date = {r["date"]: dict(r) for r in rows}

        result: list[dict[str, Any]] = []
        cur = start
        while cur <= end:
            ds = cur.isoformat()
            plan_day = self.get_plan_for_date(cur)
            row = by_date.get(ds)
            total = int((row or {}).get("total_sets") or 0)
            done = int((row or {}).get("completed_sets") or 0)
            status = (row or {}).get("status") or "none"
            rest = bool(plan_day and plan_day.get("rest"))
            plan_name = (plan_day or {}).get("name") or ""
            has_plan_work = bool(plan_day and not rest and plan_day.get("exercises"))

            if row or has_plan_work or rest:
                if status == "done" or (total > 0 and done >= total and total > 0):
                    kind = "done"
                elif done > 0 or status == "in_progress":
                    kind = "in_progress"
                elif rest:
                    kind = "rest"
                elif total > 0 or has_plan_work:
                    kind = "planned"
                else:
                    kind = "rest"
                result.append(
                    {
                        "date": ds,
                        "kind": kind,
                        "status": status,
                        "plan_name": plan_name,
                        "rest": rest,
                        "total_sets": total,
                        "completed_sets": done,
                        "exercise_count": int((row or {}).get("exercise_count") or 0),
                        "notes": (row or {}).get("notes") or "",
                    }
                )
            cur += timedelta(days=1)
        return result

    def get_last_completed_set(self, exercise_name: str, before_date: str | None = None) -> dict[str, Any] | None:
        """Last completed set for an exercise, optionally before a date."""
        before = before_date or date.today().isoformat()
        row = self.conn.execute(
            """
            SELECT s.*, w.date AS workout_date
            FROM sets s
            JOIN workouts w ON w.id = s.workout_id
            WHERE s.exercise_name = ?
              AND s.completed = 1
              AND w.date < ?
            ORDER BY w.date DESC, s.id DESC
            LIMIT 1
            """,
            (exercise_name, before),
        ).fetchone()
        return dict(row) if row else None

    def bump_set_field(self, set_id: int, field: str, delta: float) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM sets WHERE id = ?", (set_id,)).fetchone()
        if not row:
            return {}
        data = dict(row)
        if field == "weight_kg":
            current = float(data.get("weight_kg") or 0)
            new_val = max(0.0, current + delta)
            return self.update_set(set_id, weight_kg=new_val)
        if field == "reps":
            current = int(data.get("reps") or 0)
            new_val = max(0, current + int(delta))
            return self.update_set(set_id, reps=new_val)
        if field == "rpe":
            current = float(data.get("rpe") or 0)
            new_val = min(10.0, max(0.0, current + delta))
            return self.update_set(set_id, rpe=new_val)
        return data

    def complete_set(
        self,
        set_id: int,
        weight_kg: float | None = None,
        reps: int | None = None,
        rpe: float | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {"completed": True}
        if weight_kg is not None:
            fields["weight_kg"] = weight_kg
        if reps is not None:
            fields["reps"] = reps
        if rpe is not None:
            fields["rpe"] = rpe
        updated = self.update_set(set_id, **fields)
        row = self.conn.execute(
            "SELECT workout_id FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
        if row:
            self.update_workout(row["workout_id"], status="in_progress")
        return updated

    def delete_set(self, set_id: int) -> None:
        self.conn.execute("DELETE FROM sets WHERE id = ?", (set_id,))
        self.conn.commit()

    def skip_remaining_sets(
        self,
        workout_id: int,
        exercise_name: str | None = None,
    ) -> int:
        """Delete incomplete sets. If exercise_name given, only that exercise."""
        if exercise_name:
            cur = self.conn.execute(
                """
                DELETE FROM sets
                WHERE workout_id = ? AND exercise_name = ? AND completed = 0
                """,
                (workout_id, exercise_name),
            )
        else:
            cur = self.conn.execute(
                "DELETE FROM sets WHERE workout_id = ? AND completed = 0",
                (workout_id,),
            )
        self.conn.commit()
        return int(cur.rowcount or 0)

    def drop_last_incomplete_set(self, workout_id: int, exercise_name: str) -> bool:
        row = self.conn.execute(
            """
            SELECT id FROM sets
            WHERE workout_id = ? AND exercise_name = ? AND completed = 0
            ORDER BY set_index DESC, id DESC
            LIMIT 1
            """,
            (workout_id, exercise_name),
        ).fetchone()
        if not row:
            return False
        self.delete_set(row["id"])
        return True

    def apply_to_remaining_sets(
        self,
        workout_id: int,
        exercise_name: str,
        *,
        weight_kg: float | None = None,
        reps: int | None = None,
        weight_delta: float | None = None,
    ) -> int:
        """Update all incomplete sets of an exercise (mid-workout adjustment)."""
        rows = self.conn.execute(
            """
            SELECT id, weight_kg, reps FROM sets
            WHERE workout_id = ? AND exercise_name = ? AND completed = 0
            """,
            (workout_id, exercise_name),
        ).fetchall()
        for row in rows:
            fields: dict[str, Any] = {}
            if weight_kg is not None:
                fields["weight_kg"] = weight_kg
            elif weight_delta is not None:
                current = float(row["weight_kg"] or 0)
                fields["weight_kg"] = max(0.0, current + weight_delta)
            if reps is not None:
                fields["reps"] = reps
            if fields:
                self.update_set(row["id"], **fields)
        return len(rows)

    def add_planned_set(
        self,
        workout_id: int,
        exercise_name: str,
        weight_kg: float | None = None,
        reps: int | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT COALESCE(MAX(set_index), 0) AS mx,
                   (SELECT weight_kg FROM sets
                    WHERE workout_id = ? AND exercise_name = ?
                    ORDER BY set_index DESC, id DESC LIMIT 1) AS last_w,
                   (SELECT reps FROM sets
                    WHERE workout_id = ? AND exercise_name = ?
                    ORDER BY set_index DESC, id DESC LIMIT 1) AS last_r
            FROM sets WHERE workout_id = ? AND exercise_name = ?
            """,
            (
                workout_id,
                exercise_name,
                workout_id,
                exercise_name,
                workout_id,
                exercise_name,
            ),
        ).fetchone()
        set_index = int(row["mx"] or 0) + 1
        if weight_kg is None:
            weight_kg = row["last_w"]
        if reps is None:
            reps = row["last_r"]
        cur = self.conn.execute(
            """
            INSERT INTO sets (
                workout_id, exercise_name, set_index, weight_kg, reps, completed, notes
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (workout_id, exercise_name, set_index, weight_kg, reps, notes or ""),
        )
        self.conn.commit()
        out = self.conn.execute(
            "SELECT * FROM sets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(out)

    def get_day_detail(self, target_date: str | None = None) -> dict[str, Any]:
        """Read-only day view for calendar (does not seed planned sets)."""
        target = date.fromisoformat(target_date) if target_date else date.today()
        day_plan = self.get_plan_for_date(target)
        row = self.conn.execute(
            "SELECT * FROM workouts WHERE date = ?", (target.isoformat(),)
        ).fetchone()
        workout = dict(row) if row else None
        sets = self.get_sets(workout["id"]) if workout else []
        return {
            "date": target.isoformat(),
            "plan": day_plan,
            "workout": workout,
            "sets": sets,
        }

    # --- chat ---

    def add_chat_message(self, role: str, content: str) -> dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO chat_messages (role, content) VALUES (?, ?)",
            (role, content),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM chat_messages WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    def get_chat_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM chat_messages ORDER BY id DESC LIMIT ?
            ) sub ORDER BY id ASC
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_chat(self) -> None:
        self.conn.execute("DELETE FROM chat_messages")
        self.conn.commit()

    # --- exercises ---

    def list_exercises(self, query: str = "", muscle: str = "") -> list[dict[str, Any]]:
        path = EXERCISES_PATH
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        q = query.strip().lower()
        m = muscle.strip().lower()
        results = []
        for ex in data:
            if q and q not in ex["name"].lower() and q not in ex.get("muscle", "").lower():
                continue
            if m and m not in ex.get("muscle", "").lower():
                continue
            results.append(ex)
        return results

    # --- nutrition / meals ---

    def get_nutrition_targets(self) -> dict[str, Any]:
        profile = self.get_profile()
        return {
            "calorie_target": profile.get("calorie_target"),
            "protein_target_g": profile.get("protein_target_g"),
            "carb_target_g": profile.get("carb_target_g"),
            "fat_target_g": profile.get("fat_target_g"),
            "goal": profile.get("goal"),
            "weight_kg": profile.get("weight_kg"),
            "target_weight_kg": profile.get("target_weight_kg"),
            "body_fat_pct": profile.get("body_fat_pct"),
        }

    def log_meal(
        self,
        name: str,
        meal_type: str = "正餐",
        calories: float | None = None,
        protein_g: float | None = None,
        carb_g: float | None = None,
        fat_g: float | None = None,
        notes: str = "",
        target_date: str | None = None,
    ) -> dict[str, Any]:
        ds = target_date or date.today().isoformat()
        cur = self.conn.execute(
            """
            INSERT INTO meals (
                date, meal_type, name, calories, protein_g, carb_g, fat_g, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ds,
                meal_type or "正餐",
                name.strip(),
                calories,
                protein_g,
                carb_g,
                fat_g,
                notes or "",
            ),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM meals WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    def delete_meal(self, meal_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_meals(self, target_date: str | None = None) -> list[dict[str, Any]]:
        ds = target_date or date.today().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM meals WHERE date = ? ORDER BY id ASC",
            (ds,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_nutrition_day(self, target_date: str | None = None) -> dict[str, Any]:
        ds = target_date or date.today().isoformat()
        meals = self.get_meals(ds)
        totals = {
            "calories": sum(float(m["calories"] or 0) for m in meals),
            "protein_g": sum(float(m["protein_g"] or 0) for m in meals),
            "carb_g": sum(float(m["carb_g"] or 0) for m in meals),
            "fat_g": sum(float(m["fat_g"] or 0) for m in meals),
        }
        targets = self.get_nutrition_targets()
        return {
            "date": ds,
            "meals": meals,
            "totals": totals,
            "targets": targets,
            "remaining": {
                "calories": (targets["calorie_target"] or 0) - totals["calories"]
                if targets.get("calorie_target")
                else None,
                "protein_g": (targets["protein_target_g"] or 0) - totals["protein_g"]
                if targets.get("protein_target_g")
                else None,
            },
        }

    def get_recent_nutrition(self, days: int = 7) -> dict[str, Any]:
        days = max(1, min(int(days), 30))
        since = (date.today() - timedelta(days=days - 1)).isoformat()
        rows = self.conn.execute(
            """
            SELECT date,
                   COUNT(*) AS meal_count,
                   COALESCE(SUM(calories), 0) AS calories,
                   COALESCE(SUM(protein_g), 0) AS protein_g,
                   COALESCE(SUM(carb_g), 0) AS carb_g,
                   COALESCE(SUM(fat_g), 0) AS fat_g
            FROM meals
            WHERE date >= ?
            GROUP BY date
            ORDER BY date DESC
            """,
            (since,),
        ).fetchall()
        return {
            "days": days,
            "targets": self.get_nutrition_targets(),
            "daily": [dict(r) for r in rows],
        }

    # --- daily reports ---

    def get_day_snapshot(self, target_date: str | None = None) -> dict[str, Any]:
        """Assemble workout + nutrition + profile facts for a day (for report gen)."""
        ds = target_date or date.today().isoformat()
        workout_pack = self.get_today_workout(ds)
        nutri = self.get_nutrition_day(ds)
        profile = self.get_profile()
        sets = workout_pack.get("sets") or []
        done_sets = [s for s in sets if s.get("completed")]
        by_ex: dict[str, list] = {}
        for s in done_sets:
            by_ex.setdefault(s["exercise_name"], []).append(
                {
                    "set_index": s.get("set_index"),
                    "weight_kg": s.get("weight_kg"),
                    "reps": s.get("reps"),
                    "rpe": s.get("rpe"),
                }
            )
        return {
            "date": ds,
            "profile": {
                "goal": profile.get("goal"),
                "goal_detail": profile.get("goal_detail"),
                "weight_kg": profile.get("weight_kg"),
                "target_weight_kg": profile.get("target_weight_kg"),
                "body_fat_pct": profile.get("body_fat_pct"),
                "height_cm": profile.get("height_cm"),
                "gender": profile.get("gender"),
                "experience": profile.get("experience"),
            },
            "plan": workout_pack.get("plan") or {},
            "workout": {
                "status": (workout_pack.get("workout") or {}).get("status"),
                "notes": (workout_pack.get("workout") or {}).get("notes"),
                "calories_burned": (workout_pack.get("workout") or {}).get(
                    "calories_burned"
                ),
                "calories_burned_note": (workout_pack.get("workout") or {}).get(
                    "calories_burned_note"
                ),
                "total_sets": len(sets),
                "completed_sets": len(done_sets),
                "exercises": by_ex,
            },
            "nutrition": {
                "totals": nutri["totals"],
                "targets": {
                    "calorie_target": nutri["targets"].get("calorie_target"),
                    "protein_target_g": nutri["targets"].get("protein_target_g"),
                    "carb_target_g": nutri["targets"].get("carb_target_g"),
                    "fat_target_g": nutri["targets"].get("fat_target_g"),
                },
                "remaining": nutri.get("remaining"),
                "meals": [
                    {
                        "meal_type": m.get("meal_type"),
                        "name": m.get("name"),
                        "calories": m.get("calories"),
                        "protein_g": m.get("protein_g"),
                        "carb_g": m.get("carb_g"),
                        "fat_g": m.get("fat_g"),
                    }
                    for m in nutri.get("meals") or []
                ],
            },
        }

    def get_daily_report(self, target_date: str | None = None) -> dict[str, Any] | None:
        ds = target_date or date.today().isoformat()
        row = self.conn.execute(
            "SELECT * FROM daily_reports WHERE date = ?", (ds,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["stats"] = json.loads(data.get("stats_json") or "{}")
        except json.JSONDecodeError:
            data["stats"] = {}
        return data

    def list_daily_reports(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, date, title, user_note, created_at, updated_at,
                   substr(content, 1, 120) AS preview
            FROM daily_reports
            ORDER BY date DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_daily_report(
        self,
        *,
        target_date: str,
        title: str,
        content: str,
        stats: dict[str, Any] | None = None,
        user_note: str = "",
    ) -> dict[str, Any]:
        stats_json = json.dumps(stats or {}, ensure_ascii=False, default=str)
        existing = self.conn.execute(
            "SELECT id FROM daily_reports WHERE date = ?", (target_date,)
        ).fetchone()
        if existing:
            self.conn.execute(
                """
                UPDATE daily_reports
                SET title = ?, content = ?, stats_json = ?, user_note = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE date = ?
                """,
                (title, content, stats_json, user_note or "", target_date),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO daily_reports (date, title, content, stats_json, user_note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_date, title, content, stats_json, user_note or ""),
            )
        self.conn.commit()
        return self.get_daily_report(target_date) or {}

    def delete_daily_report(self, target_date: str) -> None:
        self.conn.execute("DELETE FROM daily_reports WHERE date = ?", (target_date,))
        self.conn.commit()
