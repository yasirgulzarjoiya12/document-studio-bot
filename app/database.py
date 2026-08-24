from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from .models import JobStatus


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    username TEXT,
    first_name TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    language TEXT NOT NULL DEFAULT 'en',
    page_size INTEGER NOT NULL DEFAULT 6,
    auto_cleanup INTEGER NOT NULL DEFAULT 1,
    notify_progress INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL,
    operation TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    input_meta TEXT NOT NULL DEFAULT '{}',
    output_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS job_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    original_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_results_job ON job_results(job_id);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    job_id TEXT,
    event_type TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None

    def _db(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("Database is not connected")
        return self.conn

    async def register_user(self, user_id: int, chat_id: int, username: str | None, first_name: str | None) -> None:
        stamp = now()
        db = self._db()
        await db.execute(
            """INSERT INTO users(user_id,chat_id,username,first_name,created_at,last_seen_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
               chat_id=excluded.chat_id, username=excluded.username,
               first_name=excluded.first_name, last_seen_at=excluded.last_seen_at""",
            (user_id, chat_id, username, first_name, stamp, stamp),
        )
        await db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)", (user_id,))
        await db.commit()

    async def get_settings(self, user_id: int) -> dict[str, Any]:
        cur = await self._db().execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        if not row:
            return {"language": "en", "page_size": 6, "auto_cleanup": 1, "notify_progress": 1}
        return dict(row)

    async def update_setting(self, user_id: int, key: str, value: Any) -> None:
        allowed = {"language", "page_size", "auto_cleanup", "notify_progress"}
        if key not in allowed:
            raise ValueError("Unknown setting")
        await self._db().execute(f"UPDATE user_settings SET {key}=? WHERE user_id=?", (value, user_id))
        await self._db().commit()

    async def create_job(self, job_id: str, user_id: int, chat_id: int, operation: str, input_meta: dict[str, Any]) -> None:
        stamp = now()
        await self._db().execute(
            """INSERT INTO jobs(job_id,user_id,chat_id,operation,status,progress,input_meta,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (job_id, user_id, chat_id, operation, JobStatus.QUEUED.value, 0, json.dumps(input_meta), stamp, stamp),
        )
        await self._db().commit()

    async def set_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress: int | None = None,
        output_count: int | None = None,
        error: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        fields = []
        values: list[Any] = []
        if status is not None:
            fields.append("status=?")
            values.append(status.value)
            if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                fields.append("completed_at=?")
                values.append(now())
        if progress is not None:
            fields.append("progress=?")
            values.append(progress)
        if output_count is not None:
            fields.append("output_count=?")
            values.append(output_count)
        if error is not None:
            fields.append("error=?")
            values.append(error[:2000])
        if retry_count is not None:
            fields.append("retry_count=?")
            values.append(retry_count)
        if not fields:
            return
        fields.append("updated_at=?")
        values.append(now())
        values.append(job_id)
        await self._db().execute(f"UPDATE jobs SET {', '.join(fields)} WHERE job_id=?", values)
        await self._db().commit()

    async def add_result(
        self, job_id: str, path: Path, media_type: str, original_name: str, size_bytes: int
    ) -> None:
        await self._db().execute(
            """INSERT INTO job_results(job_id, path, media_type, original_name, size_bytes, created_at)
               VALUES(?,?,?,?,?,?)""",
            (job_id, str(path), media_type, original_name, size_bytes, now()),
        )
        await self._db().commit()

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        cur = await self._db().execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    async def get_results(self, job_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        cur = await self._db().execute(
            "SELECT * FROM job_results WHERE job_id=? ORDER BY id LIMIT ? OFFSET ?",
            (job_id, limit, offset),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def get_result(self, result_id: int) -> dict[str, Any] | None:
        cur = await self._db().execute("SELECT * FROM job_results WHERE id=?", (result_id,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    async def personal_stats(self, user_id: int) -> dict[str, int]:
        cur = await self._db().execute(
            "SELECT status, COUNT(*) AS c FROM jobs WHERE user_id=? GROUP BY status", (user_id,)
        )
        rows = await cur.fetchall()
        await cur.close()
        stats = {"total": 0, "completed": 0, "failed": 0, "cancelled": 0, "queued": 0, "processing": 0}
        for row in rows:
            stats[row["status"]] = row["c"]
            stats["total"] += row["c"]
        return stats

    async def recent_jobs(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        cur = await self._db().execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def active_jobs(self, user_id: int | None = None) -> list[dict[str, Any]]:
        if user_id is None:
            cur = await self._db().execute(
                "SELECT * FROM jobs WHERE status IN ('queued','processing') ORDER BY created_at DESC LIMIT 50"
            )
        else:
            cur = await self._db().execute(
                "SELECT * FROM jobs WHERE user_id=? AND status IN ('queued','processing') ORDER BY created_at DESC",
                (user_id,),
            )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def list_users(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = await self._db().execute(
            "SELECT * FROM users ORDER BY last_seen_at DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def list_jobs(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            cur = await self._db().execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)
            )
        else:
            cur = await self._db().execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def count_by_status(self) -> dict[str, int]:
        cur = await self._db().execute("SELECT status, COUNT(*) AS c FROM jobs GROUP BY status")
        rows = await cur.fetchall()
        await cur.close()
        return {row["status"]: row["c"] for row in rows}
