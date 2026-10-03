from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from threading import Event

import pytest

from miwl2.domain import JobState, Operation, Provider, ProviderInfo, ProviderRequest
from miwl2.providers import TEST_LABEL, DeterministicProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store


def wait_idle(service: WorkspaceService) -> None:
    deadline = time.monotonic() + 3
    while service.active is not None and time.monotonic() < deadline:
        time.sleep(0.003)
    assert service.active is None, "Provider worker did not finish"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "workspace.sqlite3")


@pytest.fixture
def service(store: Store) -> Iterator[WorkspaceService]:
    service = WorkspaceService(store, DeterministicProvider(0, 0))
    yield service
    service.shutdown()


class ControlledProvider:
    """Intentionally emits late data despite cancellation to test the service gate."""

    def __init__(self) -> None:
        self.started, self.release = Event(), Event()
        self.requests: list[ProviderRequest] = []

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo("controlled-test", "Controlled test", True, "local")

    def stream(self, request: ProviderRequest, cancel: Event) -> Iterator[str]:
        self.requests.append(request)
        self.started.set()
        yield "First chunk. "
        self.release.wait(2)
        yield "Late chunk."


def test_provider_contract_is_deterministic_and_labelled() -> None:
    provider = DeterministicProvider(0, 0)
    assert isinstance(provider, Provider)
    request = ProviderRequest(Operation.SUMMARIZE, "One. Two. Three. Four.", "")
    first = "".join(provider.stream(request, Event()))
    assert first == "".join(provider.stream(request, Event()))
    assert first.startswith(TEST_LABEL)
    assert "• One.\n• Two.\n• Three." in first
    assert "Four." not in first


def test_pre_cancelled_provider_returns_nothing() -> None:
    cancellation = Event()
    cancellation.set()
    provider = DeterministicProvider(0, 0)
    assert list(provider.stream(ProviderRequest(Operation.CHAT, "", "hello"), cancellation)) == []


def test_persistence_and_edited_result_survive_restart(service: WorkspaceService) -> None:
    session = service.store.create_session()
    service.update_source(session, "A first sentence. A second sentence.")
    job = service.start(session, Operation.SUMMARIZE)
    wait_idle(service)
    assert service.store.job(job)["state"] == JobState.COMPLETED
    service.update_result(session, "My edited result")
    service.store.rename(session, "Saved session")
    reopened = Store(service.store.path)
    assert reopened.session(session)["source"] == "A first sentence. A second sentence."
    assert reopened.session(session)["result"] == "My edited result"
    assert reopened.session(session)["title"] == "Saved session"
    assert len(reopened.messages(session)) == 2


def test_session_sources_history_and_outputs_are_isolated(service: WorkspaceService) -> None:
    first, second = service.store.create_session(), service.store.create_session()
    service.update_source(first, "Private alpha content.")
    service.update_source(second, "Separate beta content.")
    service.start(first, Operation.SUMMARIZE)
    wait_idle(service)
    second_job = service.start(second, Operation.CHAT, "summarize this")
    wait_idle(service)
    output = service.store.session(second)["result"]
    assert "beta" in output and "alpha" not in output
    assert "alpha" not in service.store.job(second_job)["request"]
    assert len(service.store.messages(first)) == 2
    assert len(service.store.messages(second)) == 2


def test_followup_uses_previous_result(service: WorkspaceService) -> None:
    session = service.store.create_session()
    service.update_source(session, "One. Two. Three.")
    service.start(session, Operation.SUMMARIZE)
    wait_idle(service)
    job = service.start(session, Operation.CHAT, "make it shorter")
    wait_idle(service)
    assert "• One." in service.store.session(session)["result"]
    assert "• Two." not in service.store.session(session)["result"]
    assert "previous_result" in service.store.job(job)["request"]


def test_cancellation_and_late_chunks_preserve_saved_output(store: Store) -> None:
    provider = ControlledProvider()
    service = WorkspaceService(store, provider)
    try:
        session = store.create_session()
        service.update_source(session, "Source content.")
        service.update_result(session, "Saved output")
        job_id = service.start(session, Operation.SUMMARIZE)
        assert provider.started.wait(1)
        old_job = service.active
        assert old_job is not None
        service.cancel(session)
        provider.release.set()
        wait_idle(service)
        assert store.job(job_id)["state"] == JobState.CANCELLED
        assert store.session(session)["result"] == "Saved output"
        assert "Late chunk" not in store.messages(session)[-1]["body"]
        before = store.messages(session)[-1]["body"]
        service._delta(old_job, "Result arriving after terminal state")
        assert store.messages(session)[-1]["body"] == before
    finally:
        provider.release.set()
        service.shutdown()


def test_source_change_cancels_captured_request(store: Store) -> None:
    provider = ControlledProvider()
    service = WorkspaceService(store, provider)
    try:
        session = store.create_session()
        service.update_source(session, "Old source.")
        service.update_result(session, "Previous output")
        job = service.start(session, Operation.SUMMARIZE)
        assert provider.started.wait(1)
        service.update_source(session, "New source.")
        provider.release.set()
        wait_idle(service)
        assert provider.requests[0].source == "Old source."
        assert store.session(session)["source"] == "New source."
        assert store.session(session)["result"] == "Previous output"
        assert store.job(job)["state"] == JobState.CANCELLED
    finally:
        provider.release.set()
        service.shutdown()


def test_storage_rejects_a_stale_source_revision(store: Store) -> None:
    session = store.create_session()
    store.update_source(session, "Original source.")
    store.update_result(session, "Keep this output")
    provider = DeterministicProvider(0, 0)
    job, _ = store.create_job(
        session, ProviderRequest(Operation.SUMMARIZE, "Original source.", ""), provider.info
    )
    store.update_source(session, "Changed source.")
    assert not store.complete_job(job, "Stale output")
    assert store.session(session)["result"] == "Keep this output"
    assert store.job(job)["state"] == JobState.CANCELLED


def test_completed_job_cannot_accept_a_second_late_result(store: Store) -> None:
    session = store.create_session()
    job, _ = store.create_job(
        session, ProviderRequest(Operation.CHAT, "", "hello"), DeterministicProvider().info
    )
    assert store.complete_job(job, "First complete response")
    assert not store.complete_job(job, "A late duplicate response")
    assert store.session(session)["result"] == "First complete response"


def test_failure_is_recoverable_and_preserves_output(service: WorkspaceService) -> None:
    session = service.store.create_session()
    service.update_source(session, "One. Two. Three.")
    service.update_result(session, "Previous saved output")
    failed = service.start(session, Operation.SUMMARIZE, simulate_error=True)
    wait_idle(service)
    assert service.store.job(failed)["state"] == JobState.FAILED
    assert service.store.session(session)["result"] == "Previous saved output"
    retried = service.retry(session)
    wait_idle(service)
    assert service.store.job(retried)["state"] == JobState.COMPLETED
    assert "• One." in service.store.session(session)["result"]


def test_restart_recovers_interrupted_job_without_overwriting_result(store: Store) -> None:
    session = store.create_session()
    store.update_result(session, "Saved before interruption")
    job, _ = store.create_job(
        session, ProviderRequest(Operation.CHAT, "", "hello"), DeterministicProvider().info
    )
    store.set_job_state(job, JobState.RUNNING)
    reopened = Store(store.path)
    assert reopened.job(job)["state"] == JobState.FAILED
    assert "closed" in reopened.job(job)["error"]
    assert reopened.messages(session)[-1]["status"] == "failed"
    assert reopened.session(session)["result"] == "Saved before interruption"


def test_empty_provider_response_is_a_recoverable_failure(store: Store) -> None:
    class EmptyProvider(ControlledProvider):
        def stream(self, request: ProviderRequest, cancel: Event) -> Iterator[str]:
            return iter(())

    service = WorkspaceService(store, EmptyProvider())
    try:
        session = store.create_session()
        job = service.start(session, Operation.CHAT, "hello")
        wait_idle(service)
        assert store.job(job)["state"] == JobState.FAILED
        assert "no text" in store.job(job)["error"]
    finally:
        service.shutdown()


def test_concurrent_start_is_rejected_and_idle_cancel_is_harmless(store: Store) -> None:
    provider = ControlledProvider()
    service = WorkspaceService(store, provider)
    try:
        session = store.create_session()
        job = service.start(session, Operation.CHAT, "hello")
        assert provider.started.wait(1)
        with pytest.raises(ValueError, match="current response"):
            service.start(session, Operation.CHAT, "another")
        provider.release.set()
        wait_idle(service)
        service.cancel()
        assert store.job(job)["state"] == JobState.COMPLETED
    finally:
        provider.release.set()
        service.shutdown()


def test_invalid_requests_do_not_create_messages(service: WorkspaceService) -> None:
    session = service.store.create_session()
    with pytest.raises(ValueError, match="source"):
        service.start(session, Operation.SUMMARIZE)
    with pytest.raises(ValueError, match="message"):
        service.start(session, Operation.CHAT, "   ")
    assert service.store.messages(session) == []
