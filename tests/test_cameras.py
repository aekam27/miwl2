from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from miwl2.cameras import (
    MAX_FRAME_BYTES,
    CameraLimits,
    CameraManager,
    CameraSource,
    CameraWorker,
    MjpegDecoder,
    decode_image,
)
from miwl2.storage import Store


def jpeg(color: str = "#245dc9", label: str = "") -> bytes:
    image = QImage(640 if label else 160, 360 if label else 90, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    if label:
        painter = QPainter(image)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Helvetica Neue", 24))
        painter.drawText(42, 165, label)
        painter.setFont(QFont("Helvetica Neue", 16))
        painter.drawText(42, 210, "Generated JPEG · no camera device or real faces")
        painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "JPEG")
    return bytes(buffer.data())


def part(frame: bytes, length: bool = True) -> bytes:
    header = b"--fixture\r\nContent-Type: image/jpeg\r\n"
    if length:
        header += f"Content-Length: {len(frame)}\r\n".encode()
    return header + b"\r\n" + frame + b"\r\n"


@dataclass
class StreamFixture:
    color: str = "#245dc9"
    label: str = ""
    disconnect_first: bool = False
    stall_headers: bool = False
    continuous: bool = False
    content_type: str = 'multipart/x-mixed-replace; boundary="fixture"'
    connections: int = 0
    requested: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)


@contextmanager
def stream_fixture(fixture: StreamFixture) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            fixture.connections += 1
            fixture.requested.set()
            if fixture.stall_headers:
                fixture.release.wait(3)
            try:
                self.send_response(200)
                self.send_header("Content-Type", fixture.content_type)
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(part(jpeg(fixture.color, fixture.label)))
                self.wfile.flush()
                if fixture.disconnect_first and fixture.connections == 1:
                    return
                if fixture.continuous:
                    while not fixture.release.wait(0.25):
                        self.wfile.write(part(jpeg(fixture.color, fixture.label)))
                        self.wfile.flush()
                    return
                fixture.release.wait(3)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/synthetic.mjpeg"
    finally:
        fixture.release.set()
        server.shutdown()
        server.server_close()
        worker.join(1)


def eventually(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 2
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert condition()


@pytest.mark.parametrize("has_length", [True, False])
def test_fragmented_multipart_decodes_actual_synthetic_jpegs(has_length: bool) -> None:
    frames = [jpeg(), jpeg("#bd7632")]
    data = b"".join(part(frame, has_length) for frame in frames) + b"--fixture--\r\n"
    decoder = MjpegDecoder("fixture")
    output: list[bytes] = []
    for offset in range(0, len(data), 7):
        output.extend(decoder.feed(data[offset : offset + 7]))
    assert output == frames
    assert decode_image(output[0]).size().width() == 160
    assert decode_image(output[0]).pixelColor(0, 0) != decode_image(output[1]).pixelColor(0, 0)


def test_decoder_rejects_oversized_and_invalid_frames() -> None:
    with pytest.raises(ValueError, match="size"):
        MjpegDecoder("fixture").feed(
            (
                "--fixture\r\nContent-Type: image/jpeg\r\n"
                f"Content-Length: {MAX_FRAME_BYTES + 1}\r\n\r\n"
            ).encode()
        )
    with pytest.raises(ValueError, match="invalid JPEG"):
        MjpegDecoder("fixture").feed(part(b"bad"))
    with pytest.raises(ValueError, match="no larger"):
        decode_image(b"not an image")


@pytest.mark.parametrize(
    "url",
    [
        "rtsp://127.0.0.1/live",
        "file:///private/video",
        "0",
        "http://user:password@127.0.0.1/live",
        "https://camera.example/live",
        "http://127.0.0.1:bad/video",
    ],
)
def test_source_scope_is_explicit(url: str) -> None:
    with pytest.raises(ValueError):
        CameraSource("Source", url, True).validated()


def test_configuration_persists_without_auto_connect_and_requires_authorization(
    tmp_path: Path,
) -> None:
    manager = CameraManager(Store(tmp_path / "workspace.sqlite3"))
    try:
        manager.configure(0, CameraSource("Synthetic", "http://127.0.0.1:12345/video", False))
        with pytest.raises(ValueError, match="authorized"):
            manager.connect(0)
        reopened = CameraManager(Store(manager.store.path))
        assert reopened.sources[0].name == "Synthetic"
        assert reopened.states[0][0] == "idle" and reopened.workers == [None, None]
        reopened.shutdown()
    finally:
        manager.shutdown()


def test_two_sources_are_isolated_and_pause_stop_close_workers(tmp_path: Path) -> None:
    first, second = StreamFixture(), StreamFixture(color="#bd7632")
    with stream_fixture(first) as url1, stream_fixture(second) as url2:
        manager = CameraManager(Store(tmp_path / "workspace.sqlite3"))
        try:
            manager.configure(0, CameraSource("Blue fixture", url1, True))
            manager.configure(1, CameraSource("Amber fixture", url2, True))
            manager.connect(0)
            manager.connect(1)
            eventually(lambda: all(not image.isNull() for image in manager.frames))
            assert manager.image(0).pixelColor(0, 0) != manager.image(1).pixelColor(0, 0)
            first_worker, second_worker = manager.workers
            assert first_worker is not None and second_worker is not None
            start = time.monotonic()
            manager.stop(0, paused=True)
            manager.wait_stopped()
            assert time.monotonic() - start < 0.5
            assert not first_worker.thread.is_alive() and second_worker.thread.is_alive()
            assert manager.snapshot()[0]["state"] == "paused"
            manager.stop(1)
            manager.wait_stopped()
            assert not second_worker.thread.is_alive()
        finally:
            manager.shutdown()


def test_disconnect_retries_bounded_and_can_be_stopped() -> None:
    fixture = StreamFixture(disconnect_first=True)
    states: list[str] = []
    with stream_fixture(fixture) as url:
        worker = CameraWorker(
            CameraSource("Fixture", url, True),
            lambda state, detail: states.append(state),
            lambda image: None,
            CameraLimits(retry_seconds=0.01),
        )
        worker.start()
        eventually(lambda: fixture.connections == 2)
        assert "reconnecting" in states and "streaming" in states
        worker.stop()
        worker.thread.join(0.5)
        assert not worker.thread.is_alive()


def test_stop_interrupts_headers_and_invalidates_queued_reconnect(tmp_path: Path) -> None:
    fixture = StreamFixture(stall_headers=True)
    with stream_fixture(fixture) as url:
        manager = CameraManager(Store(tmp_path / "workspace.sqlite3"))
        try:
            manager.configure(0, CameraSource("Fixture", url, True))
            manager.connect(0)
            assert fixture.requested.wait(1)
            generation = manager.prepare_reconnect(0)
            manager.stop(0)
            manager.finish_reconnect(0, generation)
            assert manager.workers[0] is None
            assert manager.snapshot()[0]["state"] == "stopped"
            assert all(not worker.thread.is_alive() for worker in manager.retired)
        finally:
            manager.shutdown()


def test_incompatible_response_fails_without_retrying() -> None:
    fixture = StreamFixture(content_type="text/html")
    states: list[tuple[str, str]] = []
    with stream_fixture(fixture) as url:
        worker = CameraWorker(
            CameraSource("Fixture", url, True),
            lambda state, detail: states.append((state, detail)),
            lambda image: None,
        )
        worker.start()
        worker.thread.join(1)
        assert not worker.thread.is_alive()
        assert states[-1][0] == "failed" and "multipart MJPEG" in states[-1][1]
        assert fixture.connections == 1
