import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.config import (
    DEFAULT_MAX_ATTEMPTS,
    ERROR_TEXT_LIMIT,
    MAX_ATTEMPTS,
    MAX_PAYLOAD_BYTES,
    MAX_RESULT_BYTES,
)
from app.database import connect
from app.queue.retry import retry_delay

SUPPORTED_TASKS = frozenset({"uppercase_text", "calculate_sum", "simulate_failure"})


class QueueError(Exception):
    status_code = 409


class JobNotFound(QueueError):
    status_code = 404


class InvalidTransition(QueueError):
    status_code = 409


class QueueEngine:
    def __init__(self, database_path: str | Path, clock: Callable[[], float] = time.time):
        self.database_path = Path(database_path)
        self.clock = clock

    def _event(self, connection: sqlite3.Connection, job_id: str, event_type: str, worker_id: str | None = None, details: str | None = None) -> None:
        connection.execute(
            "INSERT INTO events(job_id, event_type, worker_id, created_at, details) VALUES (?, ?, ?, ?, ?)",
            (job_id, event_type, worker_id, self.clock(), details),
        )

    @staticmethod
    def _job(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] is not None else None
        return result

    def publish(
        self,
        queue_name: str,
        task_type: str,
        payload: dict[str, Any],
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> dict[str, Any]:
        if not queue_name or len(queue_name) > 64:
            raise ValueError("queue_name must contain 1-64 characters")
        if task_type not in SUPPORTED_TASKS:
            raise ValueError("unsupported task_type")
        if not isinstance(payload, dict):
            raise TypeError("payload must be a JSON object")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= MAX_ATTEMPTS:
            raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS}")
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"payload must not exceed {MAX_PAYLOAD_BYTES} bytes")
        now = self.clock()
        job_id = uuid.uuid4().hex
        with connect(self.database_path) as connection:
            connection.execute(
                """INSERT INTO jobs(id, queue_name, task_type, payload, status, attempts, max_attempts, created_at, available_at)
                   VALUES (?, ?, ?, ?, 'queued', 0, ?, ?, ?)""",
                (job_id, queue_name, task_type, encoded, max_attempts, now, now),
            )
            self._event(connection, job_id, "published")
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job(row)  # type: ignore[return-value]

    def get(self, job_id: str) -> dict[str, Any]:
        with connect(self.database_path) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        job = self._job(row)
        if job is None:
            raise JobNotFound("job not found")
        return job

    def list_jobs(
        self,
        queue_name: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        values: list[Any] = []
        if queue_name:
            clauses.append("queue_name = ?")
            values.append(queue_name)
        if status:
            clauses.append("status = ?")
            values.append(status)
        if search:
            clauses.append("id LIKE ?")
            values.append(f"%{search}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with connect(self.database_path) as connection:
            total = connection.execute(f"SELECT COUNT(*) FROM jobs {where}", values).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM jobs {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
        return [self._job(row) for row in rows if row is not None], total

    def recover_expired(self, queue_name: str | None = None) -> int:
        now = self.clock()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            clauses = ["status = 'leased'", "lease_until <= ?"]
            values: list[Any] = [now]
            if queue_name:
                clauses.append("queue_name = ?")
                values.append(queue_name)
            rows = connection.execute(
                f"SELECT id, attempts, max_attempts FROM jobs WHERE {' AND '.join(clauses)}",
                values,
            ).fetchall()
            for row in rows:
                if row["attempts"] >= row["max_attempts"]:
                    status, available = "dead", now
                    event = "dead"
                else:
                    status = "queued"
                    available = now + retry_delay(row["attempts"])
                    event = "lease_expired"
                connection.execute(
                    """UPDATE jobs SET status = ?, available_at = ?, lease_until = NULL, worker_id = NULL,
                       completed_at = CASE WHEN ? = 'dead' THEN ? ELSE completed_at END
                       WHERE id = ? AND status = 'leased' AND lease_until <= ?""",
                    (status, available, status, now, row["id"], now),
                )
                self._event(connection, row["id"], event)
            connection.commit()
        return len(rows)

    def claim(self, queue_name: str, worker_id: str, lease_seconds: int = 30) -> dict[str, Any] | None:
        if not queue_name or len(queue_name) > 64:
            raise ValueError("queue_name must contain 1-64 characters")
        if not worker_id or len(worker_id) > 128:
            raise ValueError("worker_id must contain 1-128 characters")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 1 and 300")
        now = self.clock()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            expired = connection.execute(
                "SELECT id, attempts, max_attempts FROM jobs WHERE queue_name = ? AND status = 'leased' AND lease_until <= ?",
                (queue_name, now),
            ).fetchall()
            for row in expired:
                status = "dead" if row["attempts"] >= row["max_attempts"] else "queued"
                available = now if status == "dead" else now + retry_delay(row["attempts"])
                connection.execute(
                    """UPDATE jobs SET status = ?, available_at = ?, worker_id = NULL, lease_until = NULL,
                       completed_at = CASE WHEN ? = 'dead' THEN ? ELSE completed_at END
                       WHERE id = ? AND status = 'leased' AND lease_until <= ?""",
                    (status, available, status, now, row["id"], now),
                )
                self._event(connection, row["id"], "dead" if status == "dead" else "lease_expired")
            row = connection.execute(
                """SELECT id FROM jobs WHERE queue_name = ? AND status = 'queued' AND available_at <= ?
                   ORDER BY created_at, id LIMIT 1""",
                (queue_name, now),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            updated = connection.execute(
                """UPDATE jobs SET status = 'leased', attempts = attempts + 1, worker_id = ?,
                   lease_until = ?, lease_token = lease_token + 1,
                   first_claimed_at = COALESCE(first_claimed_at, ?), last_claimed_at = ?
                   WHERE id = ? AND status = 'queued' AND available_at <= ?""",
                (worker_id, now + lease_seconds, now, now, row["id"], now),
            )
            if updated.rowcount != 1:
                connection.rollback()
                return None
            self._event(connection, row["id"], "claimed", worker_id)
            claimed = connection.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()
            connection.commit()
        return self._job(claimed)

    def _owned_lease(self, connection: sqlite3.Connection, job_id: str, worker_id: str, lease_token: int) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFound("job not found")
        if row["status"] != "leased" or row["worker_id"] != worker_id or row["lease_token"] != lease_token:
            raise InvalidTransition("job lease is not owned by this worker")
        if row["lease_until"] is None or row["lease_until"] <= self.clock():
            raise InvalidTransition("job lease has expired")
        return row

    def ack(self, job_id: str, worker_id: str, lease_token: int, result: Any = None) -> dict[str, Any]:
        encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
            raise ValueError(f"result must not exceed {MAX_RESULT_BYTES} bytes")
        now = self.clock()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._owned_lease(connection, job_id, worker_id, lease_token)
            connection.execute(
                """UPDATE jobs SET status = 'succeeded', result = ?, completed_at = ?, lease_until = NULL, worker_id = NULL
                   WHERE id = ? AND status = 'leased' AND worker_id = ? AND lease_token = ?""",
                (encoded, now, job_id, worker_id, lease_token),
            )
            self._event(connection, job_id, "succeeded", worker_id)
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            connection.commit()
        return self._job(row)  # type: ignore[return-value]

    def fail(self, job_id: str, worker_id: str, lease_token: int, error: str) -> dict[str, Any]:
        if not isinstance(error, str) or not error:
            raise ValueError("error must be a nonempty string")
        safe_error = error.replace("\x00", "")[:ERROR_TEXT_LIMIT]
        now = self.clock()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._owned_lease(connection, job_id, worker_id, lease_token)
            dead = row["attempts"] >= row["max_attempts"]
            status = "dead" if dead else "queued"
            available = now if dead else now + retry_delay(row["attempts"])
            connection.execute(
                """UPDATE jobs SET status = ?, available_at = ?, lease_until = NULL, worker_id = NULL,
                   last_error = ?, completed_at = CASE WHEN ? = 'dead' THEN ? ELSE NULL END
                   WHERE id = ? AND status = 'leased' AND worker_id = ? AND lease_token = ?""",
                (status, available, safe_error, status, now, job_id, worker_id, lease_token),
            )
            self._event(connection, job_id, "dead" if dead else "retry_scheduled", worker_id, safe_error)
            updated = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            connection.commit()
        return self._job(updated)  # type: ignore[return-value]

    def stats(self) -> dict[str, Any]:
        now = self.clock()
        hour_ago = now - 3600
        with connect(self.database_path) as connection:
            counts = {row["status"]: row["count"] for row in connection.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status")}
            for status in ("queued", "leased", "succeeded", "dead"):
                counts.setdefault(status, 0)
            depths = [dict(row) for row in connection.execute("SELECT queue_name, status, COUNT(*) AS count FROM jobs GROUP BY queue_name, status ORDER BY queue_name, status")]
            completed = connection.execute("SELECT COUNT(*) FROM jobs WHERE status = 'succeeded' AND completed_at >= ?", (hour_ago,)).fetchone()[0]
            durations = connection.execute(
                "SELECT AVG(completed_at - last_claimed_at) FROM jobs WHERE status = 'succeeded' AND completed_at >= ? AND last_claimed_at IS NOT NULL",
                (hour_ago,),
            ).fetchone()[0]
            waits = connection.execute(
                "SELECT AVG(first_claimed_at - created_at) FROM jobs WHERE first_claimed_at IS NOT NULL AND first_claimed_at >= ?",
                (hour_ago,),
            ).fetchone()[0]
            attempts = connection.execute("SELECT COUNT(*) FROM events WHERE event_type = 'claimed' AND created_at >= ?", (hour_ago,)).fetchone()[0]
            retries = connection.execute("SELECT COUNT(*) FROM events WHERE event_type = 'retry_scheduled' AND created_at >= ?", (hour_ago,)).fetchone()[0]
        return {
            "counts": counts,
            "queue_depth": depths,
            "completed_last_hour": completed,
            "throughput_per_minute": completed / 60 if completed else None,
            "average_processing_seconds": durations,
            "average_queue_wait_seconds": waits,
            "retry_rate": retries / attempts if attempts else None,
        }

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id, job_id, event_type, worker_id, created_at, details FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
