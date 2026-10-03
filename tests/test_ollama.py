from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any

import pytest

from miwl2.configuration import ProviderConfiguration
from miwl2.domain import JobState, Operation, ProviderRequest, Turn
from miwl2.ollama import HttpLimits, OllamaProvider
from miwl2.providers import TEST_LABEL, DeterministicProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store


@dataclass
class Scenario:
    records: list[object] = field(
        default_factory=lambda: [
            {"message": {"content": "Hello "}, "done": False},
            {"message": {"content": "世界"}, "done": True},
        ]
    )
    status: int = 200
    raw: bytes | None = None
    stall: str = ""
    received: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)
    payloads: list[dict[str, Any]] = field(default_factory=list)


@contextmanager
def mock_runtime(scenario: Scenario) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:
            assert self.path == "/api/chat"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            scenario.payloads.append(json.loads(body))
            scenario.received.set()
            if scenario.stall == "headers":
                scenario.release.wait(3)
            try:
                self.send_response(scenario.status)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Connection", "close")
                self.end_headers()
                if scenario.stall == "body":
                    self.wfile.flush()
                    scenario.release.wait(3)
                if scenario.raw is not None:
                    self.wfile.write(scenario.raw)
                else:
                    for record in scenario.records:
                        self.wfile.write((json.dumps(record, ensure_ascii=False) + "\n").encode())
                        self.wfile.flush()
                if scenario.stall == "after_chunk":
                    scenario.release.wait(3)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        scenario.release.set()
        server.shutdown()
        server.server_close()
        worker.join(1)


def request(operation: Operation = Operation.CHAT) -> ProviderRequest:
    return ProviderRequest(
        operation, "The trial lasted 12 weeks. Results remain uncertain.", "Explain this"
    )


def wait_idle(service: WorkspaceService) -> None:
    deadline = time.monotonic() + 2
    while service.active is not None and time.monotonic() < deadline:
        time.sleep(0.003)
    assert service.active is None


def test_real_adapter_streams_mock_unicode_and_posts_bounded_local_payload() -> None:
    scenario = Scenario()
    with mock_runtime(scenario) as endpoint:
        provider = OllamaProvider(endpoint, "gemma3:4b")
        assert "".join(provider.stream(request(), Event())) == "Hello 世界"
    payload = scenario.payloads[0]
    assert payload["model"] == "gemma3:4b" and payload["stream"] is True
    assert payload["options"]["num_ctx"] == 4096
    assert payload["options"]["num_predict"] == 1024
    assert not provider.info.is_test
    assert "uncertain" in payload["messages"][-1]["content"]


@pytest.mark.parametrize("operation", list(Operation))
def test_operations_have_distinct_prompts_and_source_semantics(operation: Operation) -> None:
    provider = OllamaProvider("http://127.0.0.1:11434", "gemma3:4b")
    task = ProviderRequest(
        operation,
        "Evidence with caveats.",
        "A useful topic",
        (Turn("user", "Earlier private question"), Turn("assistant", "Earlier answer")),
        "An edited draft",
    )
    messages = provider.payload(task)["messages"]
    assert isinstance(messages, list)
    assert f"Task: {operation}" in messages[-1]["content"]
    assert "Evidence with caveats." in messages[-1]["content"]
    assert ("An edited draft" in messages[-1]["content"]) == (operation == Operation.CHAT)
    assert (len(messages) == 4) == (operation == Operation.CHAT)
    if operation == Operation.PARAPHRASE:
        assert "Preserve its meaning" in messages[0]["content"]
    if operation == Operation.SUMMARIZE:
        assert "Do not add unsupported" in messages[0]["content"]


@pytest.mark.parametrize(
    ("scenario", "error"),
    [
        (Scenario(status=404), "could not find"),
        (Scenario(status=500), "HTTP 500"),
        (Scenario(raw=b"not json\n"), "invalid JSON"),
        (Scenario(records=[{"error": "model crashed"}]), "generation error"),
        (
            Scenario(records=[{"message": {"content": "partial"}, "done": False}]),
            "before completion",
        ),
        (Scenario(records=[{"message": {"content": 4}, "done": True}]), "invalid message"),
        (Scenario(records=[[]]), "invalid stream"),
    ],
)
def test_errors_are_recoverable_without_silent_fixture_fallback(
    scenario: Scenario, error: str
) -> None:
    with mock_runtime(scenario) as endpoint, pytest.raises(RuntimeError, match=error):
        list(OllamaProvider(endpoint, "gemma3:4b").stream(request(), Event()))


@pytest.mark.parametrize(
    ("limits", "scenario", "error"),
    [
        (HttpLimits(line_bytes=20), Scenario(raw=b"x" * 21), "oversized"),
        (HttpLimits(output_characters=3), Scenario(), "output limit"),
        (HttpLimits(read_seconds=0.08), Scenario(stall="body"), "timed out"),
        (HttpLimits(read_seconds=2, total_seconds=0.08), Scenario(stall="headers"), "timed out"),
    ],
)
def test_transport_and_output_limits(limits: HttpLimits, scenario: Scenario, error: str) -> None:
    with mock_runtime(scenario) as endpoint:
        started = time.monotonic()
        with pytest.raises(RuntimeError, match=error):
            list(OllamaProvider(endpoint, "gemma3:4b", limits).stream(request(), Event()))
        assert time.monotonic() - started < 1


@pytest.mark.parametrize("stall", ["headers", "body", "after_chunk"])
def test_stop_interrupts_blocked_http_and_preserves_saved_draft(tmp_path: Path, stall: str) -> None:
    scenario = Scenario(stall=stall, records=[{"message": {"content": "Partial"}, "done": False}])
    with mock_runtime(scenario) as endpoint:
        service = WorkspaceService(
            Store(tmp_path / "workspace.sqlite3"), OllamaProvider(endpoint, "gemma3:4b")
        )
        try:
            session = service.store.create_session()
            service.update_result(session, "User's saved draft")
            job = service.start(session, Operation.CHAT, "hello")
            assert scenario.received.wait(1)
            started = time.monotonic()
            service.cancel()
            wait_idle(service)
            assert time.monotonic() - started < 0.6
            assert service.store.job(job)["state"] == JobState.CANCELLED
            assert service.store.session(session)["result"] == "User's saved draft"
        finally:
            service.shutdown()


def test_precancel_and_prompt_limit_make_no_http_requests() -> None:
    scenario = Scenario()
    with mock_runtime(scenario) as endpoint:
        provider = OllamaProvider(endpoint, "gemma3:4b")
        cancel = Event()
        cancel.set()
        assert list(provider.stream(request(), cancel)) == []
        with pytest.raises(ValueError, match="No text was sent"):
            list(provider.stream(ProviderRequest(Operation.CHAT, "x" * 13_000, "hi"), Event()))
    assert scenario.payloads == []


def test_truncated_response_does_not_replace_complete_saved_draft(tmp_path: Path) -> None:
    scenario = Scenario(
        records=[
            {
                "message": {"content": "unfinished text"},
                "done": True,
                "done_reason": "length",
            }
        ]
    )
    with mock_runtime(scenario) as endpoint:
        service = WorkspaceService(
            Store(tmp_path / "workspace.sqlite3"), OllamaProvider(endpoint, "gemma3:4b")
        )
        try:
            session = service.store.create_session()
            service.update_result(session, "Previous complete draft")
            job = service.start(session, Operation.ARTICLE, "A topic")
            wait_idle(service)
            assert service.store.job(job)["state"] == JobState.FAILED
            assert "token limit" in service.store.job(job)["error"]
            assert service.store.session(session)["result"] == "Previous complete draft"
        finally:
            service.shutdown()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://127.0.0.1:11434/api",
        "http://user:password@127.0.0.1:11434",
        "http://127.0.0.1:bad",
        "http://127.0.0.1:11434?x=1",
    ],
)
def test_configuration_rejects_nonlocal_or_ambiguous_endpoints(endpoint: str) -> None:
    with pytest.raises(ValueError):
        ProviderConfiguration("ollama", endpoint, "gemma3:4b").validated()


def test_saved_provider_configuration_and_job_attribution_survive_restart(tmp_path: Path) -> None:
    scenario = Scenario()
    with mock_runtime(scenario) as endpoint:
        store = Store(tmp_path / "workspace.sqlite3")
        service = WorkspaceService(store, DeterministicProvider(0, 0))
        try:
            session = store.create_session()
            service.start(session, Operation.CHAT, "fixture request")
            wait_idle(service)
            configuration = ProviderConfiguration("ollama", endpoint, "gemma3:4b")
            service.configure_provider(configuration)
            service.start(session, Operation.ARTICLE, "A useful topic")
            wait_idle(service)
            assert store.session(session)["result"] == "Hello 世界"
            rows = store.messages(session)
            assert rows[1]["provider_is_test"] == 1
            assert rows[3]["provider_is_test"] == 0
            assert rows[3]["provider_label"] == "Ollama · gemma3:4b"
            assert Store(store.path).provider_configuration() == configuration
        finally:
            service.shutdown()


def test_new_fixture_operations_are_explicitly_not_ai() -> None:
    provider = DeterministicProvider(0, 0)
    for operation in (Operation.ARTICLE, Operation.PARAPHRASE):
        output = "".join(provider.stream(request(operation), Event()))
        assert output.startswith(TEST_LABEL)
        assert "fixed test outline" in output or "does not paraphrase" in output
