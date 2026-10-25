"""Хранилище на SQLite: пользователи, тренировки, отметки о выполнении."""
import sqlite3
from contextlib import closing

_path = "workout_bot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    tz TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    days TEXT NOT NULL,          -- '0,2,4' (0 = понедельник)
    hour INTEGER NOT NULL,
    minute INTEGER NOT NULL,
    exercises TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    status TEXT NOT NULL,        -- 'done' | 'skipped'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _connect():
    conn = sqlite3.connect(_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str = "workout_bot.db") -> None:
    global _path
    _path = path
    with closing(_connect()) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def _workout(row) -> dict:
    data = dict(row)
    data["days"] = [int(d) for d in data["days"].split(",")]
    return data


def get_tz(chat_id: int, default: str) -> str:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT tz FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    return row["tz"] if row else default


def set_tz(chat_id: int, tz: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO users (chat_id, tz) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET tz = excluded.tz",
            (chat_id, tz),
        )
        conn.commit()


def add_workout(chat_id, title, days, hour, minute, exercises) -> dict:
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO workouts (chat_id, title, days, hour, minute, exercises) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, title, ",".join(map(str, days)), hour, minute, exercises),
        )
        conn.commit()
        return get_workout(cur.lastrowid)


def get_workout(workout_id: int) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM workouts WHERE id = ?", (workout_id,)).fetchone()
    return _workout(row) if row else None


def list_workouts(chat_id: int) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM workouts WHERE chat_id = ? ORDER BY hour, minute", (chat_id,)
        ).fetchall()
    return [_workout(r) for r in rows]


def all_workouts() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM workouts").fetchall()
    return [_workout(r) for r in rows]


def delete_workout(workout_id: int, chat_id: int) -> bool:
    with closing(_connect()) as conn:
        cur = conn.execute(
            "DELETE FROM workouts WHERE id = ? AND chat_id = ?", (workout_id, chat_id)
        )
        conn.commit()
        return cur.rowcount > 0


def add_log(workout_id: int, chat_id: int, status: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO logs (workout_id, chat_id, status) VALUES (?, ?, ?)",
            (workout_id, chat_id, status),
        )
        conn.commit()


def stats(chat_id: int, days: int = 30) -> dict:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM logs "
            "WHERE chat_id = ? AND created_at >= datetime('now', ?) GROUP BY status",
            (chat_id, f"-{days} days"),
        ).fetchall()
    result = {"done": 0, "skipped": 0}
    result.update({r["status"]: r["n"] for r in rows})
    return result
