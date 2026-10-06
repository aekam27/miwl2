from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from miwl2.configuration import ProviderConfiguration
from miwl2.domain import JobState, Operation, ProviderInfo, ProviderRequest

SCHEMA_VERSION = 2
BACKUP_LIMIT = 5


class StorageError(RuntimeError):
    """A workspace needs attention before it can be opened safely."""


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Store:
    """Short transactions with one application writer and per-operation connections."""

    def __init__(self, path: Path) -> None:
        self.path = path.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.configuration_warning = ""
        if self.path.is_symlink():
            raise StorageError("The writing database must be a regular file, not a symlink.")
        existed = self.path.exists()
        version = 0
        if existed:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as existing:
                version = int(existing.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise StorageError(
                    f"This workspace uses schema {version}; this app supports {SCHEMA_VERSION}. "
                    "Open it with a newer Miwl version. The database was not changed."
                )
        else:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        self.path.chmod(0o600)
        if existed and version < SCHEMA_VERSION:
            self.backup("before-migration")
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            schema = """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '',
                    source_revision INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    role TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    message_id TEXT NOT NULL REFERENCES messages(id),
                    state TEXT NOT NULL, request TEXT NOT NULL,
                    source_revision INTEGER NOT NULL, provider TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS jobs_session ON jobs(session_id, created_at);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
            for statement in schema.split(";"):
                if statement.strip():
                    connection.execute(statement)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "provider_label" not in columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN provider_label TEXT NOT NULL DEFAULT ''"
                )
            if "provider_is_test" not in columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN provider_is_test INTEGER NOT NULL DEFAULT 1"
                )
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.recover_interrupted_jobs()

    def backup(self, reason: str = "manual") -> Path:
        """A consistent WAL-aware writing snapshot; never copies gallery or documents."""
        if reason not in {"manual", "startup", "before-migration"}:
            raise ValueError("Unsupported backup reason.")
        directory = self.path.parent / "writing-backups"
        if directory.is_symlink():
            raise StorageError("The writing backup folder must not be a symlink.")
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
        name = f"writing-{reason}-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}-{uuid4().hex}.sqlite3"
        destination = directory / name
        temporary = directory / ("." + name + ".tmp")
        with self._lock:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            try:
                with self.connection() as source:
                    target = sqlite3.connect(temporary)
                    try:
                        source.backup(target)
                        if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                            raise StorageError("The writing backup failed its integrity check.")
                    finally:
                        target.close()
                with temporary.open("rb") as snapshot_file:
                    os.fsync(snapshot_file.fileno())
                os.replace(temporary, destination)
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                snapshots = [
                    item
                    for item in directory.glob("writing-*.sqlite3")
                    if re.fullmatch(
                        r"writing-(manual|startup|before-migration)-\d{8}T\d{12}Z-"
                        r"[0-9a-f]{32}\.sqlite3",
                        item.name,
                    )
                    and item.is_file()
                    and not item.is_symlink()
                ]
                # Sort by modification time because the reason precedes the date.
                snapshots.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
                for snapshot in snapshots[BACKUP_LIMIT:]:
                    if snapshot.is_file() and not snapshot.is_symlink():
                        snapshot.unlink()
            finally:
                temporary.unlink(missing_ok=True)
        return destination

    def backup_if_due(self) -> Path | None:
        """At most one automatic snapshot per UTC day; explicit backups remain available."""
        today = datetime.now(UTC).strftime("%Y%m%d")
        with self.connection() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key='backup_day'").fetchone()
        if row is not None and row["value"] == today:
            return None
        path = self.backup("startup")
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO settings VALUES('backup_day',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (today,),
            )
        return path

    def provider_configuration(self) -> ProviderConfiguration:
        with self.connection() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key='provider'").fetchone()
        if row is None:
            return ProviderConfiguration()
        try:
            values = json.loads(row["value"])
            if not isinstance(values, dict) or not all(isinstance(v, str) for v in values.values()):
                raise ValueError("Invalid provider values")
            return ProviderConfiguration(**values).validated()
        except (ValueError, TypeError):
            self.configuration_warning = (
                "Saved provider settings are invalid. Test mode is active; "
                "choose and save a writing provider to repair them."
            )
            return ProviderConfiguration()

    def save_provider_configuration(self, configuration: ProviderConfiguration) -> None:
        value = json.dumps(configuration.validated().to_dict())
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO settings(key,value) VALUES('provider',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (value,),
            )
        self.configuration_warning = ""

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

    def recover_interrupted_jobs(self) -> None:
        with self.connection() as connection:
            pending = connection.execute(
                "SELECT message_id FROM jobs WHERE state IN (?,?,?,?)",
                (JobState.QUEUED, JobState.LOADING, JobState.RUNNING, JobState.CANCELLING),
            ).fetchall()
            for row in pending:
                connection.execute(
                    "UPDATE messages SET status='failed' WHERE id=?", (row["message_id"],)
                )
            connection.execute(
                "UPDATE jobs SET state=?, error=?, updated_at=? WHERE state IN (?,?,?,?)",
                (
                    JobState.FAILED,
                    "The application closed before this response finished. You can retry it.",
                    timestamp(),
                    JobState.QUEUED,
                    JobState.LOADING,
                    JobState.RUNNING,
                    JobState.CANCELLING,
                ),
            )

    def create_session(self) -> str:
        session_id = uuid4().hex
        now = timestamp()
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO sessions(id,title,created_at,updated_at) VALUES(?,?,?,?)",
                (session_id, "Untitled session", now, now),
            )
        return session_id

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT id,title,updated_at FROM sessions ORDER BY updated_at DESC, rowid DESC"
                )
            ]

    def session(self, session_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise ValueError("That session could not be found.")
        return dict(row)

    def update_source(self, session_id: str, source: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE sessions SET source=?,source_revision=source_revision+1,updated_at=? "
                "WHERE id=? AND source<>?",
                (source, timestamp(), session_id, source),
            )

    def update_result(self, session_id: str, result: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE sessions SET result=?,updated_at=? WHERE id=? AND result<>?",
                (result, timestamp(), session_id, result),
            )

    def rename(self, session_id: str, title: str) -> None:
        title = title.strip()[:80]
        if not title:
            raise ValueError("Use a non-empty session name.")
        with self.connection() as connection:
            connection.execute(
                "UPDATE sessions SET title=?,updated_at=? WHERE id=?",
                (title, timestamp(), session_id),
            )

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT recent.*,jobs.provider,jobs.provider_label,jobs.provider_is_test "
                    "FROM (SELECT rowid AS sequence,* FROM messages WHERE session_id=? "
                    "ORDER BY rowid DESC LIMIT 200) AS recent "
                    "LEFT JOIN jobs ON jobs.message_id=recent.id ORDER BY sequence",
                    (session_id,),
                )
            ]

    def create_job(
        self, session_id: str, request: ProviderRequest, info: ProviderInfo
    ) -> tuple[str, str]:
        job_id, message_id, now = uuid4().hex, uuid4().hex, timestamp()
        with self.connection() as connection:
            session = connection.execute(
                "SELECT source_revision,title FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if session is None:
                raise ValueError("That session could not be found.")
            user_body = (
                request.prompt
                or {
                    Operation.SUMMARIZE: "Summarize the current source.",
                    Operation.PARAPHRASE: "Paraphrase the current source.",
                    Operation.ARTICLE: "Write an article.",
                    Operation.CHAT: "Send a message.",
                }[request.operation]
            )
            connection.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?,?)",
                (uuid4().hex, session_id, "user", user_body, "complete", now),
            )
            connection.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?,?)",
                (message_id, session_id, "assistant", "", "pending", now),
            )
            connection.execute(
                "INSERT INTO jobs(id,session_id,message_id,state,request,source_revision,provider,"
                "created_at,updated_at,provider_label,provider_is_test) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    session_id,
                    message_id,
                    JobState.QUEUED,
                    json.dumps(request.to_dict(), ensure_ascii=False),
                    session["source_revision"],
                    info.identifier,
                    now,
                    now,
                    info.label,
                    int(info.is_test),
                ),
            )
            title = session["title"]
            if title == "Untitled session":
                title = (
                    request.source
                    if request.operation in {Operation.SUMMARIZE, Operation.PARAPHRASE}
                    else user_body
                )
                title = " ".join(title.split())[:42] or "Untitled session"
            connection.execute(
                "UPDATE sessions SET title=?,updated_at=? WHERE id=?", (title, now, session_id)
            )
        return job_id, message_id

    def job(self, job_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("That response could not be found.")
        return dict(row)

    def last_job(self, session_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE session_id=? ORDER BY rowid DESC LIMIT 1", (session_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def last_completed_job(self, session_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE session_id=? AND state=? ORDER BY rowid DESC LIMIT 1",
                (session_id, JobState.COMPLETED),
            ).fetchone()
        return dict(row) if row is not None else None

    def set_job_state(self, job_id: str, state: JobState, error: str = "") -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE jobs SET state=?,error=?,updated_at=? WHERE id=?",
                (state, error, timestamp(), job_id),
            )

    def set_message(self, message_id: str, body: str, status: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE messages SET body=?,status=? WHERE id=?", (body, status, message_id)
            )

    def finish_job(self, job_id: str, state: JobState, body: str, error: str = "") -> bool:
        """Save a stopped/failed job and its partial message in one transaction."""
        if state not in {JobState.CANCELLED, JobState.FAILED}:
            raise ValueError("Use complete_job to save a completed draft.")
        with self.connection() as connection:
            changed = connection.execute(
                "UPDATE jobs SET state=?,error=?,updated_at=? WHERE id=? AND state IN (?,?,?,?)",
                (
                    state,
                    error,
                    timestamp(),
                    job_id,
                    JobState.QUEUED,
                    JobState.LOADING,
                    JobState.RUNNING,
                    JobState.CANCELLING,
                ),
            ).rowcount
            if not changed:
                return False
            connection.execute(
                "UPDATE messages SET body=?,status=? WHERE id="
                "(SELECT message_id FROM jobs WHERE id=?)",
                (body, state, job_id),
            )
        return True

    def complete_job(self, job_id: str, body: str) -> bool:
        """Commit the result only if the captured source revision is still current."""
        with self.connection() as connection:
            row = connection.execute(
                "SELECT jobs.*,sessions.source_revision AS current_revision FROM jobs "
                "JOIN sessions ON sessions.id=jobs.session_id WHERE jobs.id=?",
                (job_id,),
            ).fetchone()
            if row is None or row["state"] not in (
                JobState.QUEUED,
                JobState.LOADING,
                JobState.RUNNING,
            ):
                return False
            if row["source_revision"] != row["current_revision"]:
                connection.execute(
                    "UPDATE jobs SET state=?,updated_at=? WHERE id=?",
                    (JobState.CANCELLED, timestamp(), job_id),
                )
                connection.execute(
                    "UPDATE messages SET status='cancelled' WHERE id=?", (row["message_id"],)
                )
                return False
            now = timestamp()
            connection.execute(
                "UPDATE messages SET body=?,status='complete' WHERE id=?", (body, row["message_id"])
            )
            connection.execute(
                "UPDATE sessions SET result=?,updated_at=? WHERE id=?",
                (body, now, row["session_id"]),
            )
            connection.execute(
                "UPDATE jobs SET state=?,updated_at=? WHERE id=?", (JobState.COMPLETED, now, job_id)
            )
        return True
