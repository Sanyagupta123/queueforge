import sqlite3
from pathlib import Path


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    queue_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    result TEXT,
    status TEXT NOT NULL CHECK (status IN ('queued', 'leased', 'succeeded', 'dead')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    created_at REAL NOT NULL,
    available_at REAL NOT NULL,
    lease_until REAL,
    worker_id TEXT,
    lease_token INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    completed_at REAL,
    first_claimed_at REAL,
    last_claimed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(queue_name, status, available_at, created_at, id);
CREATE INDEX IF NOT EXISTS idx_jobs_lease ON jobs(status, lease_until);
CREATE INDEX IF NOT EXISTS idx_jobs_completed ON jobs(status, completed_at);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    event_type TEXT NOT NULL,
    worker_id TEXT,
    created_at REAL NOT NULL,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id, id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path), timeout=5, isolation_level=None, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(path: str | Path) -> None:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)
