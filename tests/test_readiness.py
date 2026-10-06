from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

from miwl2.cloud import CloudProvider
from miwl2.domain import JobState, Operation, ProviderInfo, ProviderRequest, Turn
from miwl2.ollama import HttpLimits, OllamaProvider
from miwl2.service import WorkspaceService
from miwl2.storage import BACKUP_LIMIT, StorageError, Store


def wait_idle(service: WorkspaceService) -> None:
    deadline = time.monotonic() + 3
    while service.active is not None and time.monotonic() < deadline:
        time.sleep(0.003)
    assert service.active is None


def test_future_schema_is_refused_without_changing_database(tmp_path: Path) -> None:
    path = tmp_path / "workspace.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE future_notes(body TEXT)")
        connection.execute("INSERT INTO future_notes VALUES('fictional saved note')")
        connection.execute("PRAGMA user_version=99")
    original = path.read_bytes()
    mode = path.stat().st_mode
    with pytest.raises(StorageError, match="newer Miwl"):
        Store(path)
    assert path.read_bytes() == original and path.stat().st_mode == mode
    assert not (tmp_path / "writing-backups").exists()


def test_legacy_migration_has_reopenable_private_snapshot(tmp_path: Path) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    session = store.create_session()
    store.update_result(session, "Fictional manually edited draft")
    with store.connection() as connection:
        connection.execute("ALTER TABLE jobs DROP COLUMN provider_label")
        connection.execute("ALTER TABLE jobs DROP COLUMN provider_is_test")
        connection.execute("PRAGMA user_version=1")
    migrated = Store(store.path)
    assert migrated.session(session)["result"] == "Fictional manually edited draft"
    backup = next((tmp_path / "writing-backups").glob("*.sqlite3"))
    assert backup.stat().st_mode & 0o777 == 0o600
    assert backup.parent.stat().st_mode & 0o777 == 0o700
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            connection.execute("SELECT result FROM sessions").fetchone()[0].startswith("Fictional")
        )
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_failed_migration_rolls_back_ddl_and_keeps_prior_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "workspace.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE jobs(id TEXT)")
        connection.execute("CREATE TABLE saved_notes(body TEXT)")
        connection.execute("INSERT INTO saved_notes VALUES('fictional original')")
        connection.execute("PRAGMA user_version=1")
    with pytest.raises(sqlite3.Error):
        Store(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            connection.execute("SELECT body FROM saved_notes").fetchone()[0] == "fictional original"
        )
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='sessions'"
        ).fetchall()
    assert len(list((tmp_path / "writing-backups").glob("*.sqlite3"))) == 1


def test_backup_includes_live_wal_and_failed_publish_keeps_previous_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    session = store.create_session()
    # Keep WAL open: a raw file copy would miss the following committed edit.
    reader = sqlite3.connect(store.path)
    reader.execute("SELECT * FROM sessions").fetchall()
    try:
        store.update_source(session, "Fictional committed WAL source")
        first = store.backup()
        with sqlite3.connect(first) as restored:
            assert (
                restored.execute("SELECT source FROM sessions").fetchone()[0].endswith("WAL source")
            )
        replace = Mock(side_effect=OSError("fixture publication failure"))
        monkeypatch.setattr(os, "replace", replace)
        with pytest.raises(OSError, match="fixture publication"):
            store.backup()
        assert first.exists()
        assert list(first.parent.glob("*.sqlite3")) == [first]
        assert not list(first.parent.glob("*.tmp"))
        assert store.session(session)["source"].endswith("WAL source")
    finally:
        reader.close()


def test_backups_are_bounded_and_automatic_copy_is_daily(tmp_path: Path) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    assert store.backup_if_due() is not None
    assert store.backup_if_due() is None
    for _ in range(BACKUP_LIMIT + 2):
        store.backup()
    copies = list((tmp_path / "writing-backups").glob("*.sqlite3"))
    assert len(copies) == BACKUP_LIMIT
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in copies)
    assert store.backup_if_due() is None


@pytest.mark.parametrize("value", ["not-json", '{"endpoint":12}', '{"unknown":"value"}'])
def test_invalid_configuration_uses_labelled_fixture_until_explicit_repair(
    tmp_path: Path, value: str
) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    with store.connection() as connection:
        connection.execute("INSERT INTO settings VALUES('provider',?)", (value,))
    configuration = store.provider_configuration()
    assert configuration.provider == "deterministic" and "invalid" in store.configuration_warning
    with store.connection() as connection:
        assert (
            connection.execute("SELECT value FROM settings WHERE key='provider'").fetchone()[0]
            == value
        )
    store.save_provider_configuration(configuration)
    assert store.configuration_warning == ""


@pytest.mark.parametrize("kind", ["local", "cloud"])
def test_long_unicode_history_retains_newest_pairs_and_current_text(kind: str) -> None:
    limits = HttpLimits(prompt_bytes=1000)
    provider = (
        OllamaProvider("http://127.0.0.1:11434", "fixture", limits)
        if kind == "local"
        else CloudProvider("fixture", limits)
    )
    history = tuple(
        turn
        for index in range(8)
        for turn in (
            Turn("user", f"Question {index} " + "界" * 35),
            Turn("assistant", f"Answer {index} " + "é" * 40),
        )
    )
    request = ProviderRequest(
        Operation.CHAT, "Fictional source", "Current question", history, "Edited draft"
    )
    prepared = provider.prepare_request(request)
    assert 0 < len(prepared.history) < len(history)
    assert prepared.history[-2:] == history[-2:]
    assert prepared.omitted_history_turns == len(history) - len(prepared.history)
    assert prepared.source == request.source and prepared.previous_result == request.previous_result
    payload = provider.payload(prepared)
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert sum(len(message["content"].encode("utf-8")) for message in messages) <= 1000
    assert (
        "Current question" in messages[-1]["content"] and "Edited draft" in messages[-1]["content"]
    )
    assert provider.prepare_request(prepared) == prepared


def test_oversized_current_text_is_rejected_before_creating_job_or_loading_cloud_key(
    tmp_path: Path,
) -> None:
    key_loader = Mock(side_effect=AssertionError("No key lookup allowed"))
    service = WorkspaceService(
        Store(tmp_path / "workspace.sqlite3"), CloudProvider("fixture", key_loader=key_loader)
    )
    try:
        session = service.store.create_session()
        service.update_source(session, "界" * 5000)
        with pytest.raises(ValueError, match="limit"):
            service.start(session, Operation.CHAT, "Small question", cloud_authorized=True)
        assert service.store.messages(session) == []
        key_loader.assert_not_called()
    finally:
        service.shutdown()


class BurstProvider:
    info = ProviderInfo("burst-fixture", "Burst fixture", True, "local")

    def __init__(self, oversized: bool = False) -> None:
        self.oversized = oversized

    def stream(self, request: ProviderRequest, cancel: Event) -> Iterator[str]:
        yield "First "
        if self.oversized:
            yield "x" * (64 * 1024)
        else:
            yield from ("x" for _ in range(1000))
            yield " final"


def test_burst_chunks_coalesce_writes_without_losing_terminal_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    service = WorkspaceService(store, BurstProvider())
    message_writes = Mock(wraps=store.set_message)
    monkeypatch.setattr(store, "set_message", message_writes)
    monkeypatch.setattr("miwl2.service.time.monotonic", lambda: 100.0)
    try:
        session = store.create_session()
        job = service.start(session, Operation.CHAT, "Fictional burst")
        # Event wait avoids relying on the patched shared time module.
        for _ in range(1000):
            if service.active is None:
                break
            Event().wait(0.003)
        assert service.active is None
        assert store.job(job)["state"] == JobState.COMPLETED
        assert store.session(session)["result"] == "First " + "x" * 1000 + " final"
        assert message_writes.call_count == 1
    finally:
        service.shutdown()


def test_generic_provider_output_limit_preserves_draft_and_partial(tmp_path: Path) -> None:
    service = WorkspaceService(Store(tmp_path / "workspace.sqlite3"), BurstProvider(True))
    try:
        session = service.store.create_session()
        service.update_result(session, "Fictional saved draft")
        job = service.start(session, Operation.CHAT, "Fictional overflow")
        wait_idle(service)
        assert service.store.job(job)["state"] == JobState.FAILED
        assert service.store.messages(session)[-1]["body"] == "First "
        assert service.store.session(session)["result"] == "Fictional saved draft"
    finally:
        service.shutdown()
    with pytest.raises(ValueError, match="closing"):
        service.start(session, Operation.CHAT, "After close")
    assert len(service.store.messages(session)) == 2


def test_terminal_save_failure_releases_job_and_blocks_more_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    service = WorkspaceService(store, BurstProvider())
    try:
        session = store.create_session()
        store.update_result(session, "Fictional prior draft")
        monkeypatch.setattr(
            store, "complete_job", Mock(side_effect=sqlite3.OperationalError("fixture full disk"))
        )
        service.start(session, Operation.CHAT, "Fictional save failure")
        wait_idle(service)
        assert "could not be saved" in service.persistence_error
        assert store.session(session)["result"] == "Fictional prior draft"
        with pytest.raises(ValueError, match="reopen"):
            service.start(session, Operation.CHAT, "Blocked while storage needs attention")
        assert len(store.messages(session)) == 2
    finally:
        service.shutdown()


def test_retention_does_not_remove_unmanaged_files(tmp_path: Path) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    first = store.backup()
    unrelated = first.parent / "writing-owner-copy.sqlite3"
    unrelated.write_text("Fictional separately managed copy")
    for _ in range(BACKUP_LIMIT + 1):
        store.backup()
    assert unrelated.read_text() == "Fictional separately managed copy"


def test_failed_terminal_message_write_rolls_back_job_state_and_preserves_draft(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    session = store.create_session()
    store.update_result(session, "Fictional existing draft")
    job, message = store.create_job(
        session, ProviderRequest(Operation.CHAT, "", "Fictional request"), BurstProvider.info
    )
    with store.connection() as connection:
        connection.execute(
            "CREATE TRIGGER reject_message BEFORE UPDATE ON messages "
            "BEGIN SELECT RAISE(ABORT, 'fixture message failure'); END"
        )
    with pytest.raises(sqlite3.Error, match="fixture message failure"):
        store.finish_job(job, JobState.FAILED, "Partial response", "Fixture error")
    assert store.job(job)["state"] == JobState.QUEUED
    assert store.messages(session)[-1]["status"] == "pending"
    with store.connection() as connection:
        connection.execute("DROP TRIGGER reject_message")
    assert store.finish_job(job, JobState.FAILED, "Partial response", "Fixture error")
    assert store.messages(session)[-1]["status"] == "failed"
    assert not store.finish_job(job, JobState.CANCELLED, "Late replacement")
    assert store.messages(session)[-1]["body"] == "Partial response"
    assert store.session(session)["result"] == "Fictional existing draft"
