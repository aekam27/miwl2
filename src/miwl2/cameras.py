from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from threading import Event, RLock, Thread
from urllib.parse import urlsplit

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage, QImageReader

from miwl2.storage import Store

MAX_FRAME_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class CameraSource:
    name: str
    url: str = ""
    authorized: bool = False

    def validated(self) -> CameraSource:
        name, url = self.name.strip()[:60], self.url.strip()
        if not name:
            raise ValueError("Give this source a name.")
        if url:
            parsed = urlsplit(url)
            try:
                port = parsed.port
            except ValueError as exception:
                raise ValueError("Use a valid HTTP(S) MJPEG URL.") from exception
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.fragment:
                raise ValueError(
                    "This milestone supports HTTP(S) MJPEG URLs only; RTSP is not connected."
                )
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("URLs containing credentials are not supported.")
            if port is not None and port < 1:
                raise ValueError("Use a valid HTTP(S) MJPEG port.")
            if parsed.hostname != "localhost":
                try:
                    ipaddress.ip_address(parsed.hostname)
                except ValueError as exception:
                    raise ValueError(
                        "Use a numeric IP address or localhost for this MJPEG milestone."
                    ) from exception
        return CameraSource(name, url, self.authorized)


class MjpegDecoder:
    """Bounded multipart JPEG parser, supporting Content-Length or boundary framing."""

    def __init__(self, boundary: str) -> None:
        if not boundary or len(boundary) > 70 or not boundary.isascii():
            raise ValueError("The stream did not provide a valid MJPEG boundary.")
        self.boundary = b"--" + boundary.encode("ascii")
        self.buffer = bytearray()
        self.in_body = False
        self.length: int | None = None

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames: list[bytes] = []
        while True:
            if not self.in_body:
                start = self.buffer.find(self.boundary)
                if start < 0:
                    if len(self.buffer) > 8192:
                        raise ValueError("MJPEG headers exceeded the supported limit.")
                    break
                del self.buffer[:start]
                if self.buffer.startswith(self.boundary + b"--"):
                    self.buffer.clear()
                    break
                end = self.buffer.find(b"\r\n\r\n")
                if end < 0:
                    if len(self.buffer) > 8192:
                        raise ValueError("MJPEG headers exceeded the supported limit.")
                    break
                if end > 8192:
                    raise ValueError("MJPEG headers exceeded the supported limit.")
                headers: dict[bytes, bytes] = {}
                for line in bytes(self.buffer[:end]).split(b"\r\n")[1:]:
                    key, separator, value = line.partition(b":")
                    if separator:
                        headers[key.strip().lower()] = value.strip()
                if headers.get(b"content-type", b"").lower() != b"image/jpeg":
                    raise ValueError("The MJPEG stream returned a non-JPEG part.")
                raw_length = headers.get(b"content-length")
                try:
                    self.length = int(raw_length) if raw_length is not None else None
                except ValueError as exception:
                    raise ValueError(
                        "The MJPEG stream returned an invalid frame length."
                    ) from exception
                if self.length is not None and not 0 < self.length <= MAX_FRAME_BYTES:
                    raise ValueError("The MJPEG frame exceeded the supported size.")
                del self.buffer[: end + 4]
                self.in_body = True
            if self.length is None:
                end = self.buffer.find(b"\r\n" + self.boundary)
                if end < 0:
                    if len(self.buffer) > MAX_FRAME_BYTES:
                        raise ValueError("The MJPEG frame exceeded the supported size.")
                    break
                length = end
            else:
                length = self.length
                if len(self.buffer) < length:
                    break
            frame = bytes(self.buffer[:length])
            if length > MAX_FRAME_BYTES:
                raise ValueError("The MJPEG frame exceeded the supported size.")
            if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
                raise ValueError("The stream returned an invalid JPEG frame.")
            frames.append(frame)
            del self.buffer[:length]
            self.in_body = False
        return frames


def decode_image(frame: bytes) -> QImage:
    buffer = QBuffer()
    buffer.setData(frame)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer, b"JPEG")
    size = reader.size()
    if not size.isValid() or size.width() > 1920 or size.height() > 1080:
        raise ValueError("Use MJPEG frames no larger than 1920×1080.")
    image = reader.read()
    if image.isNull():
        raise ValueError("The stream's JPEG frame could not be decoded.")
    return image


@dataclass(frozen=True)
class CameraLimits:
    connect_seconds: float = 3
    read_seconds: float = 5
    retries: int = 3
    retry_seconds: float = 0.5
    frame_interval: float = 0.1

    def __post_init__(self) -> None:
        if (
            min(self.connect_seconds, self.read_seconds, self.retry_seconds, self.frame_interval)
            <= 0
            or not 0 <= self.retries <= 3
        ):
            raise ValueError("Use positive camera time limits and at most three retries.")


class CameraWorker:
    def __init__(
        self,
        source: CameraSource,
        on_state: Callable[[str, str], None],
        on_frame: Callable[[QImage], None],
        limits: CameraLimits | None = None,
    ) -> None:
        self.source = source.validated()
        self.on_state, self.on_frame = on_state, on_frame
        self.limits = limits or CameraLimits()
        self.cancel = Event()
        self.thread = Thread(target=self._run, name="miwl2-mjpeg", daemon=True)

    def start(self) -> None:
        if not self.source.url or not self.source.authorized:
            raise ValueError("Save an authorized MJPEG source URL before connecting.")
        self.thread.start()

    def stop(self) -> None:
        self.cancel.set()

    def _connection(self) -> None:
        parsed = urlsplit(self.source.url)
        factory = (
            http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        )
        host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname or ""
        connection = factory(host, parsed.port, timeout=self.limits.connect_seconds)
        finished = Event()
        transport_socket: socket.socket | None = None

        def interrupt() -> None:
            while not finished.wait(0.025):
                if self.cancel.is_set():
                    active_socket = connection.sock or transport_socket
                    if active_socket is not None:
                        try:
                            active_socket.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                    connection.close()

        watcher = Thread(target=interrupt, daemon=True, name="miwl2-camera-cancel")
        watcher.start()
        response: http.client.HTTPResponse | None = None
        try:
            connection.connect()
            if self.cancel.is_set():
                return
            assert connection.sock is not None
            transport_socket = connection.sock
            connection.auto_open = 0
            connection.sock.settimeout(self.limits.read_seconds)
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request("GET", target, headers={"Accept": "multipart/x-mixed-replace"})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError(
                    f"Source returned HTTP {response.status}. Redirects are not followed."
                )
            content_type = response.getheader("Content-Type", "")
            boundary = ""
            for parameter in content_type.split(";")[1:]:
                key, separator, value = parameter.strip().partition("=")
                if key.lower() == "boundary" and separator:
                    boundary = value.strip('"')
            if not content_type.lower().startswith("multipart/x-mixed-replace"):
                raise ValueError("This URL did not return a multipart MJPEG stream.")
            decoder, last_frame = MjpegDecoder(boundary), 0.0
            while not self.cancel.is_set():
                chunk = response.read1(16 * 1024)
                if self.cancel.is_set():
                    return
                if not chunk:
                    raise OSError("stream closed")
                for frame in decoder.feed(chunk):
                    if self.cancel.is_set():
                        return
                    now = time.monotonic()
                    if now - last_frame >= self.limits.frame_interval:
                        image = decode_image(frame)
                        self.on_state("streaming", "MJPEG connected · preview available")
                        self.on_frame(image)
                        last_frame = now
        finally:
            finished.set()
            if response is not None:
                response.close()
            connection.close()
            watcher.join(0.1)

    def _run(self) -> None:
        for attempt in range(self.limits.retries + 1):
            if self.cancel.is_set():
                return
            self.on_state("connecting" if attempt == 0 else "reconnecting", "Opening MJPEG source…")
            try:
                self._connection()
                return
            except ValueError as exception:
                if not self.cancel.is_set():
                    self.on_state("failed", str(exception))
                return
            except (OSError, http.client.HTTPException):
                if self.cancel.is_set():
                    return
                if attempt == self.limits.retries:
                    self.on_state(
                        "failed", "Source disconnected or timed out. Check the URL and reconnect."
                    )
                else:
                    self.on_state(
                        "reconnecting",
                        f"Connection lost · retry {attempt + 1}/{self.limits.retries}",
                    )
                    if self.cancel.wait(self.limits.retry_seconds * (2**attempt)):
                        return


class CameraManager:
    """Two isolated workers and latest-frame slots; configuration never auto-connects."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self._lock = RLock()
        with store.connection() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key='cameras'").fetchone()
        configurations = (
            json.loads(row["value"]) if row else [{"name": "Source 1"}, {"name": "Source 2"}]
        )
        self.sources = [CameraSource(**item).validated() for item in configurations]
        self.states = [("idle", "Not connected") for _ in self.sources]
        self.frames = [QImage(), QImage()]
        self.frame_revisions = [0, 0]
        self.frame_times = [0.0, 0.0]
        self.workers: list[CameraWorker | None] = [None, None]
        self.retired: list[CameraWorker] = []
        self.generations = [0, 0]
        self.on_change: Callable[[], None] = lambda: None

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    **asdict(source),
                    "state": self.states[index][0],
                    "detail": self.states[index][1],
                    "frameRevision": self.frame_revisions[index],
                    "hasFrame": not self.frames[index].isNull(),
                    "generation": self.generations[index],
                }
                for index, source in enumerate(self.sources)
            ]

    def configure(self, index: int, source: CameraSource) -> None:
        self._check_index(index)
        source = source.validated()
        self.stop(index)
        with self._lock:
            self.sources[index] = source
            self.frames[index] = QImage()
            self.frame_times[index] = 0.0
            self.frame_revisions[index] += 1
            with self.store.connection() as connection:
                connection.execute(
                    "INSERT INTO settings(key,value) VALUES('cameras',?) ON CONFLICT(key) "
                    "DO UPDATE SET value=excluded.value",
                    (json.dumps([asdict(item) for item in self.sources]),),
                )
        self.on_change()

    @staticmethod
    def _check_index(index: int) -> None:
        if index not in {0, 1}:
            raise ValueError("Choose source 1 or source 2.")

    def connect(self, index: int, limits: CameraLimits | None = None) -> None:
        self._check_index(index)
        with self._lock:
            source = self.sources[index]
            if not source.url or not source.authorized:
                raise ValueError("Save an authorized MJPEG source URL before connecting.")
            self.retired = [worker for worker in self.retired if worker.thread.is_alive()]
            # Prevent rapid stop/reconnect from accumulating unbounded socket threads.
            if self.workers[index] is not None or self.retired:
                raise ValueError("Wait for stopped workers to exit before reconnecting.")
            generation = self.generations[index]

            def state_changed(state: str, detail: str) -> None:
                with self._lock:
                    if self.generations[index] != generation:
                        return
                    self.states[index] = (state, detail)
                self.on_change()

            def frame_changed(image: QImage) -> None:
                with self._lock:
                    if self.generations[index] != generation:
                        return
                    self.frames[index] = image
                    self.frame_times[index] = time.monotonic()
                    self.frame_revisions[index] += 1
                self.on_change()

            worker = CameraWorker(source, state_changed, frame_changed, limits)
            self.workers[index] = worker
            worker.start()

    def stop(self, index: int, paused: bool = False) -> None:
        self._check_index(index)
        with self._lock:
            self.generations[index] += 1
            worker, self.workers[index] = self.workers[index], None
            if worker is not None:
                worker.stop()
                self.retired.append(worker)
            self.states[index] = (
                ("paused", "Paused · connection closed")
                if paused
                else ("stopped", "Stopped · connection closed")
            )
        self.on_change()

    def prepare_reconnect(self, index: int) -> int:
        self.stop(index)
        return self.generations[index]

    def finish_reconnect(self, index: int, generation: int) -> None:
        self.wait_stopped()
        with self._lock:
            if self.generations[index] == generation:
                self.connect(index)

    def wait_stopped(self) -> None:
        deadline = time.monotonic() + 3.2
        for worker in list(self.retired):
            worker.thread.join(max(0, deadline - time.monotonic()))

    def image(self, index: int) -> QImage:
        self._check_index(index)
        with self._lock:
            return self.frames[index].copy()

    def vision_frame(self, index: int) -> tuple[QImage, int, int, str, float]:
        """Atomically copy the latest frame and its source lifecycle metadata."""
        self._check_index(index)
        with self._lock:
            return (
                self.frames[index].copy(),
                self.generations[index],
                self.frame_revisions[index],
                self.states[index][0],
                self.frame_times[index],
            )

    def shutdown(self) -> None:
        self.stop(0)
        self.stop(1)
        self.wait_stopped()
