from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock

import pytest

from miwl2.domain import JobState, Operation, ProviderInfo, ProviderRequest
from miwl2.service import WorkspaceService
from miwl2.storage import Store


class RecordingProvider:
    info = ProviderInfo("dispatch-fixture", "Dispatch fixture", True, "local")

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def stream(self, request: ProviderRequest, cancel: Event) -> Iterator[str]:
        self.prompts.append(request.prompt)
        yield "Fictional completed response"


def wait_idle(service: WorkspaceService) -> None:
    deadline = time.monotonic() + 3
    while service.active is not None and time.monotonic() < deadline:
        time.sleep(0.003)
    assert service.active is None, "Provider worker did not finish"


def test_worker_start_failure_preserves_writing_and_retry_skips_abandoned_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    provider = RecordingProvider()
    service = WorkspaceService(store, provider)
    try:
        session = store.create_session()
        store.update_source(session, "Fictional original notes")
        store.update_result(session, "Fictional saved draft")
        # ThreadPoolExecutor queues work before attempting to start its first worker.
        # Raising here reproduces both the startup failure and the abandoned queue item.
        with monkeypatch.context() as patch:
            patch.setattr(
                Thread, "start", Mock(side_effect=RuntimeError("fictional worker capacity"))
            )
            failed = service.start(session, Operation.CHAT, "Fictional failed dispatch")

        assert service.active is None
        assert store.job(failed)["state"] == JobState.FAILED
        assert "worker could not start" in store.job(failed)["error"]
        assert "retry" in store.job(failed)["error"].lower()
        assert store.messages(session)[-1]["status"] == "failed"
        assert store.messages(session)[-1]["body"] == ""
        assert store.session(session)["source"] == "Fictional original notes"
        assert store.session(session)["result"] == "Fictional saved draft"
        assert provider.prompts == []
        assert not service.persistence_error

        # The new worker sees the abandoned queue item before the retried request.
        # Only the retry may call the provider or complete a response.
        retried = service.retry(session)
        wait_idle(service)
        assert provider.prompts == ["Fictional failed dispatch"]
        assert store.job(failed)["state"] == JobState.FAILED
        assert store.job(retried)["state"] == JobState.COMPLETED
        assert store.session(session)["result"] == "Fictional completed response"
        assert store.session(session)["source"] == "Fictional original notes"
        reopened = Store(store.path)
        assert reopened.job(failed)["state"] == JobState.FAILED
        assert reopened.session(session)["result"] == "Fictional completed response"
    finally:
        service.shutdown()


def test_worker_start_failure_with_unwritable_status_blocks_until_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "workspace.sqlite3")
    provider = RecordingProvider()
    service = WorkspaceService(store, provider)
    try:
        session = store.create_session()
        store.update_result(session, "Fictional saved draft")
        with monkeypatch.context() as patch:
            patch.setattr(
                Thread, "start", Mock(side_effect=RuntimeError("fictional worker capacity"))
            )
            patch.setattr(
                store,
                "finish_job",
                Mock(side_effect=sqlite3.OperationalError("fictional disk full")),
            )
            failed = service.start(session, Operation.CHAT, "Fictional failed dispatch")

        assert service.active is None
        assert "could not be saved" in service.persistence_error
        assert store.session(session)["result"] == "Fictional saved draft"
        assert provider.prompts == []
        with pytest.raises(ValueError, match="reopen"):
            service.start(session, Operation.CHAT, "Fictional blocked request")
        assert len(store.messages(session)) == 2
        service.shutdown()
        reopened = Store(store.path)
        assert reopened.job(failed)["state"] == JobState.FAILED
        assert reopened.messages(session)[-1]["status"] == "failed"
        assert reopened.session(session)["result"] == "Fictional saved draft"
    finally:
        service.shutdown()
