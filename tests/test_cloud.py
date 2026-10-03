from __future__ import annotations

import http.client
import json
import ssl
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from miwl2.cloud import OPENAI_ENDPOINT, CloudProvider
from miwl2.configuration import ProviderConfiguration
from miwl2.domain import Operation, ProviderRequest
from miwl2.service import WorkspaceService
from miwl2.storage import Store


def event(value: object) -> bytes:
    return b"data: " + json.dumps(value, ensure_ascii=False).encode() + b"\n\n"


def successful() -> bytes:
    return (
        b": heartbeat\n\n"
        + event({"choices": [{"delta": {"role": "assistant"}}]})
        + event({"choices": [{"delta": {"content": "Synthetic café "}}]})
        + event({"choices": [{"delta": {"content": "response."}, "finish_reason": "stop"}]})
        + event(
            {
                "choices": [],
                "usage": {"prompt_tokens": 19, "completion_tokens": 4, "total_tokens": 23},
            }
        )
        + b"data: [DONE]\n\n"
    )


@dataclass
class CloudFixture:
    body: bytes = field(default_factory=successful)
    status: int = 200
    stall_headers: bool = False
    requests: list[dict[str, object]] = field(default_factory=list)
    arrived: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)


@contextmanager
def fixture_http(fixture: CloudFixture, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            fixture.requests.append(
                {
                    "path": self.path,
                    "payload": payload,
                    "authorization": self.headers.get("Authorization"),
                }
            )
            fixture.arrived.set()
            if fixture.stall_headers:
                fixture.release.wait(3)
            try:
                self.send_response(fixture.status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(fixture.body)))
                self.end_headers()
                for position in range(0, len(fixture.body), 13):
                    self.wfile.write(fixture.body[position : position + 13])
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    worker.start()

    def local_connection(
        host: str, *, timeout: float, context: ssl.SSLContext
    ) -> http.client.HTTPConnection:
        assert host == "api.openai.com" and context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname
        return http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=timeout)

    monkeypatch.setattr("miwl2.cloud.http.client.HTTPSConnection", local_connection)
    try:
        yield
    finally:
        fixture.release.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)


def provider() -> CloudProvider:
    return CloudProvider("synthetic-model", key_loader=lambda cancel: "synthetic-test-key")


def test_streams_fragmented_sse_and_uses_only_reported_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = CloudFixture()
    cloud = provider()
    with fixture_http(fixture, monkeypatch):
        output = "".join(
            cloud.stream(ProviderRequest(Operation.CHAT, "Safe source", "Hello"), threading.Event())
        )
    assert output == "Synthetic café response."
    assert cloud.last_usage == {"prompt_tokens": 19, "completion_tokens": 4, "total_tokens": 23}
    assert fixture.requests[0]["path"] == "/v1/chat/completions"
    assert fixture.requests[0]["authorization"] == "Bearer synthetic-test-key"
    payload = fixture.requests[0]["payload"]
    assert isinstance(payload, dict) and payload["stream_options"] == {"include_usage": True}
    assert payload["max_completion_tokens"] == 1024
    assert all(isinstance(m["content"], str) for m in payload["messages"])


@pytest.mark.parametrize(
    "body,status",
    [
        (b"", 401),
        (b"", 429),
        (b"", 302),
        (b"data: nonsense\n\n", 200),
        (event({"choices": [{"delta": {"content": "Partial"}}]}), 200),
        (event({"choices": [{"delta": {}, "finish_reason": "length"}]}), 200),
        (b"data: [DONE]\n\n", 200),
    ],
)
def test_cloud_failures_never_fallback_or_complete_partial(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    status: int,
) -> None:
    fixture = CloudFixture(body=body, status=status)
    with fixture_http(fixture, monkeypatch), pytest.raises(RuntimeError):
        list(
            provider().stream(ProviderRequest(Operation.CHAT, "", "Safe input"), threading.Event())
        )
    assert len(fixture.requests) == 1


def test_stop_interrupts_cloud_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = CloudFixture(stall_headers=True)
    cancel = threading.Event()
    errors: list[Exception] = []
    with fixture_http(fixture, monkeypatch):

        def run() -> None:
            try:
                list(provider().stream(ProviderRequest(Operation.CHAT, "", "Safe input"), cancel))
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        assert fixture.arrived.wait(1)
        start = time.monotonic()
        cancel.set()
        worker.join(timeout=1)
        assert not worker.is_alive() and not errors
        assert time.monotonic() - start < 0.8


def test_precancel_and_oversize_make_no_key_lookup() -> None:
    lookups: list[bool] = []
    cloud = CloudProvider(
        "synthetic-model", key_loader=lambda cancel: lookups.append(True) or "fake"
    )
    cancel = threading.Event()
    cancel.set()
    assert list(cloud.stream(ProviderRequest(Operation.CHAT, "", "Safe input"), cancel)) == []
    with pytest.raises(ValueError):
        list(cloud.stream(ProviderRequest(Operation.CHAT, "x" * 13000, "Hi"), threading.Event()))
    assert lookups == []


def test_cloud_requires_new_consent_per_request_and_never_stores_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(tmp_path / "cloud.sqlite3")
    config = ProviderConfiguration("cloud", OPENAI_ENDPOINT, "synthetic-model")
    store.save_provider_configuration(config)
    assert "key" not in json.dumps(config.to_dict()).lower()
    service = WorkspaceService(store, provider())
    session = store.create_session()
    try:
        with pytest.raises(ValueError, match="Confirm"):
            service.start(session, Operation.CHAT, "Safe input")
        assert store.messages(session) == []
        fixture = CloudFixture()
        with fixture_http(fixture, monkeypatch):
            service.start(session, Operation.CHAT, "Safe input", cloud_authorized=True)
            deadline = time.monotonic() + 2
            while service.active is not None and time.monotonic() < deadline:
                time.sleep(0.005)
        assert store.session(session)["result"] == "Synthetic café response."
        with pytest.raises(ValueError, match="Confirm"):
            service.start(session, Operation.CHAT, "Another input")
        assert b"synthetic-test-key" not in store.path.read_bytes()
    finally:
        service.shutdown()
