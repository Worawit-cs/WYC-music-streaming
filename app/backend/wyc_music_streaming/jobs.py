"""SQLite job store (WAL mode). The only database the app has."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id          INTEGER PRIMARY KEY,
  user        TEXT NOT NULL,
  video_id    TEXT NOT NULL,
  title       TEXT NOT NULL,
  artist      TEXT NOT NULL,
  album       TEXT NOT NULL,
  track_no    INTEGER,
  year        TEXT,
  cover_url   TEXT,
  box_id      TEXT,
  status      TEXT NOT NULL CHECK (status IN ('queued','downloading','done','failed','cancelled')),
  progress    REAL NOT NULL DEFAULT 0,
  error       TEXT,
  final_path  TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_user_status ON jobs(user, status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class NewJob:
    video_id: str
    title: str
    artist: str
    album: str
    track_no: int | None = None
    year: str | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class Job:
    id: int
    user: str
    video_id: str
    title: str
    artist: str
    album: str
    track_no: int | None
    year: str | None
    cover_url: str | None
    box_id: str | None
    status: str
    progress: float
    error: str | None
    final_path: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def add(self, user: str, items: list[NewJob], box_id: str | None = None) -> list[Job]:
        now = _now()
        ids: list[int] = []
        with self._lock:
            self._db.execute("BEGIN")
            try:
                for it in items:
                    cur = self._db.execute(
                        "INSERT INTO jobs (user, video_id, title, artist, album, track_no, year, cover_url,"
                        " box_id, status, progress, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?)",
                        (user, it.video_id, it.title, it.artist, it.album, it.track_no, it.year,
                         it.cover_url, box_id, now, now),
                    )
                    ids.append(cur.lastrowid)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return [job for i in ids if (job := self.get(i)) is not None]

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job(**dict(row)) if row else None

    def has_active(self, user: str, video_id: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM jobs WHERE user = ? AND video_id = ? AND status IN ('queued','downloading') LIMIT 1",
                (user, video_id),
            ).fetchone()
        return row is not None

    def claim_next(self) -> Job | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job_id = row["id"]
            self._db.execute(
                "UPDATE jobs SET status = 'downloading', progress = 0, error = NULL, updated_at = ? WHERE id = ?",
                (_now(), job_id),
            )
        return self.get(job_id)

    def _update(self, job_id: int, assignments: str, params: tuple[Any, ...]) -> None:
        with self._lock:
            self._db.execute(
                f"UPDATE jobs SET {assignments}, updated_at = ? WHERE id = ?",
                (*params, _now(), job_id),
            )

    def set_progress(self, job_id: int, fraction: float) -> None:
        self._update(job_id, "progress = ?", (max(0.0, min(1.0, fraction)),))

    def finish(self, job_id: int, final_path: str) -> None:
        self._update(job_id, "status = 'done', progress = 1, final_path = ?, error = NULL", (final_path,))

    def fail(self, job_id: int, error: str) -> None:
        self._update(job_id, "status = 'failed', error = ?", (error,))

    def cancel(self, user: str, job_id: int) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE jobs SET status = 'cancelled', updated_at = ?"
                " WHERE id = ? AND user = ? AND status = 'queued'",
                (_now(), job_id, user),
            )
        return cur.rowcount == 1

    def retry(self, user: str, job_id: int) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE jobs SET status = 'queued', progress = 0, error = NULL, updated_at = ?"
                " WHERE id = ? AND user = ? AND status = 'failed'",
                (_now(), job_id, user),
            )
        return cur.rowcount == 1

    def recover(self) -> int:
        with self._lock:
            cur = self._db.execute(
                "UPDATE jobs SET status = 'queued', progress = 0, updated_at = ? WHERE status = 'downloading'",
                (_now(),),
            )
        return cur.rowcount

    def list_for_user(self, user: str, history: int = 50) -> list[Job]:
        with self._lock:
            active = self._db.execute(
                "SELECT * FROM jobs WHERE user = ? AND status IN ('queued','downloading') ORDER BY id",
                (user,),
            ).fetchall()
            finished = self._db.execute(
                "SELECT * FROM jobs WHERE user = ? AND status NOT IN ('queued','downloading')"
                " ORDER BY updated_at DESC, id DESC LIMIT ?",
                (user, history),
            ).fetchall()
        return [Job(**dict(r)) for r in (*active, *finished)]
