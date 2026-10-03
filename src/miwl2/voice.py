from __future__ import annotations

import json
import math
import os
import signal
import struct
import subprocess
import tempfile
import threading
import time
import wave
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path


class VoiceError(ValueError):
    pass


class VoiceCancelled(Exception):
    pass


@dataclass(frozen=True)
class VoicePaths:
    whisper: Path
    model: Path
    recorder: Path
    say: Path = Path("/usr/bin/say")

    @classmethod
    def local(cls, root: Path) -> VoicePaths:
        return cls(
            root / ".runtime/whisper.cpp/build/bin/whisper-cli",
            root / ".runtime/whisper.cpp/models/ggml-base.bin",
            root / ".runtime/MiwlVoice.app",
        )

    @property
    def available(self) -> bool:
        return self.whisper.is_file() and self.model.is_file()

    @property
    def recording_available(self) -> bool:
        return self.available and (self.recorder / "Contents/MacOS/MiwlVoice").is_file()


@dataclass(frozen=True)
class VoiceSnapshot:
    phase: str = "idle"
    transcript: str = ""
    error: str = ""
    elapsed: float = 0


def validate_wav(path: Path) -> float:
    if path.stat().st_size > 2_000_000:
        raise VoiceError("Choose a recording no longer than 60 seconds (16 kHz mono WAV).")
    try:
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != 16000
                or audio.getcomptype() != "NONE"
            ):
                raise VoiceError("Voice accepts 16 kHz mono 16-bit PCM WAV audio.")
            duration = audio.getnframes() / 16000
            if not 0.1 <= duration <= 60.1:
                raise VoiceError("Record between 0.1 and 60 seconds.")
            data = audio.readframes(audio.getnframes())
            if len(data) != audio.getnframes() * 2:
                raise VoiceError("The WAV recording is incomplete.")
    except (wave.Error, EOFError) as error:
        raise VoiceError("The file is not a supported PCM WAV recording.") from error
    samples = struct.iter_unpack("<h", data)
    rms = math.sqrt(sum(sample[0] ** 2 for sample in samples) / (len(data) / 2))
    if rms < 30:
        raise VoiceError("No audible speech was detected. Record again closer to the microphone.")
    return duration


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=1)


def run_process(
    arguments: list[str],
    cancel: threading.Event,
    timeout: float,
    stdin: bytes | None = None,
) -> str:
    """Bound output memory and cancel the owned process group, never the UI thread."""
    if cancel.is_set():
        raise VoiceCancelled
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + timeout
            pending_input = stdin
            while True:
                if cancel.is_set():
                    raise VoiceCancelled
                if time.monotonic() >= deadline:
                    raise VoiceError("The local voice task timed out. Try a shorter recording.")
                try:
                    process.communicate(input=pending_input, timeout=0.025)
                    break
                except subprocess.TimeoutExpired:
                    # communicate resumes any buffered input; do not block on a pipe write.
                    pending_input = None
            output.seek(0)
            log = output.read(16_384).decode("utf-8", errors="replace")
            if process.returncode:
                raise VoiceError("The local voice tool failed. Check the installed runtime.")
            return log
        finally:
            _terminate(process)


class VoiceRuntime:
    def __init__(self, paths: VoicePaths) -> None:
        self.paths = paths
        self.last_duration = 0.0
        self.last_transcription_seconds = 0.0

    def transcribe(self, source: Path, cancel: threading.Event) -> str:
        if not self.paths.available:
            raise VoiceError("Local Whisper runtime/model is missing. Voice does not download it.")
        self.last_duration = validate_wav(source)
        with tempfile.TemporaryDirectory(prefix="miwl2-asr-") as directory:
            output = Path(directory) / "transcript"
            started = time.monotonic()
            run_process(
                [
                    str(self.paths.whisper),
                    "-m",
                    str(self.paths.model),
                    "-f",
                    str(source),
                    "-l",
                    "auto",
                    "-t",
                    "4",
                    "-otxt",
                    "-of",
                    str(output),
                    "-nt",
                    "-np",
                    "-ng",
                ],
                cancel,
                120,
            )
            self.last_transcription_seconds = time.monotonic() - started
            transcript_file = output.with_suffix(".txt")
            if not transcript_file.is_file() or transcript_file.stat().st_size > 80_000:
                raise VoiceError("Whisper did not return a bounded transcript.")
            text = transcript_file.read_text(encoding="utf-8").strip()
            if not text:
                raise VoiceError("No transcript was returned. Try a clearer recording.")
            return text

    def record(
        self,
        destination: Path,
        cancel: threading.Event,
        finish: threading.Event,
        update: Callable[[str, float], None],
    ) -> None:
        if not self.paths.recording_available:
            raise VoiceError(
                "The local recording helper is missing; typing and WAV import still work."
            )
        status = destination.parent / "recording-status.json"
        control = destination.parent / "recording-control.txt"
        process = subprocess.Popen(
            [
                "/usr/bin/open",
                "-n",
                "-W",
                str(self.paths.recorder),
                "--args",
                "record",
                str(destination),
                str(control),
                str(status),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        helper_pid: int | None = None
        final_phase = ""
        deadline = time.monotonic() + 180
        last_state: tuple[str, float] = ("", 0)
        try:
            while True:
                if cancel.is_set() or finish.is_set():
                    control.write_text("cancel" if cancel.is_set() else "finish")
                try:
                    result = json.loads(status.read_text())
                    helper_pid = int(result["pid"])
                    final_phase = result["phase"]
                    state = (final_phase, float(result.get("elapsed", 0)))
                    if state != last_state:
                        update(*state)
                        last_state = state
                    if final_phase in {"finished", "cancelled", "error"}:
                        if final_phase == "error":
                            raise VoiceError(str(result.get("error", "Recording failed.")))
                        break
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                if process.poll() is not None:
                    raise VoiceError("The recording helper exited before producing audio.")
                if time.monotonic() > deadline:
                    raise VoiceError("Recording or microphone permission timed out.")
                time.sleep(0.05)
            if cancel.is_set() or final_phase == "cancelled":
                raise VoiceCancelled
            process.wait(timeout=2)
        finally:
            control.write_text("cancel")
            # The helper is a separate LaunchServices app, outside open's process group.
            # Its own status file in this private directory identifies only this launch.
            if process.poll() is None:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    if helper_pid is not None and helper_pid > 1:
                        try:
                            os.kill(helper_pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
            _terminate(process)

    def speak(self, text: str, cancel: threading.Event) -> None:
        if not text.strip():
            raise VoiceError("Create a draft before speaking it.")
        if len(text) > 5000:
            raise VoiceError("Playback is limited to 5,000 characters. Shorten the draft first.")
        if not self.paths.say.is_file():
            raise VoiceError("The Mac's speech tool is unavailable.")
        run_process(
            [str(self.paths.say), "-v", "Samantha", "-r", "175"],
            cancel,
            180,
            stdin=text.encode("utf-8"),
        )


class VoiceEngine:
    """One local task, with generation gates for cancellation and session switches."""

    def __init__(self, runtime: VoiceRuntime) -> None:
        self.runtime = runtime
        self.on_change: Callable[[], None] = lambda: None
        self._snapshot = VoiceSnapshot()
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miwl2-voice")
        self._active: threading.Event | None = None
        self._finish_recording = threading.Event()
        self._generation = 0

    @property
    def snapshot(self) -> VoiceSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._active is not None

    def edit(self, text: str) -> None:
        with self._lock:
            if self._active is not None:
                return
            self._snapshot = replace(self._snapshot, transcript=text[:20_000])
        self.on_change()

    def reset(self) -> None:
        with self._lock:
            if self._active is not None:
                self._active.set()
            self._generation += 1
            self._snapshot = VoiceSnapshot(phase="stopping" if self.busy else "idle")
        self.on_change()

    def stop(self) -> None:
        with self._lock:
            if self._active is not None:
                self._active.set()
                self._snapshot = replace(self._snapshot, phase="stopping")
        self.on_change()

    def finish_recording(self) -> None:
        if self.snapshot.phase == "recording":
            self._finish_recording.set()

    def _start(self, phase: str, task: Callable[[threading.Event, int], str | None]) -> None:
        with self._lock:
            if self._active is not None:
                raise VoiceError("Stop the current voice task first.")
            cancel = threading.Event()
            self._active = cancel
            self._finish_recording.clear()
            generation = self._generation
            self._snapshot = replace(self._snapshot, phase=phase, error="", elapsed=0)
        self.on_change()

        def work() -> None:
            transcript: str | None = None
            error = ""
            try:
                transcript = task(cancel, generation)
            except VoiceCancelled:
                pass
            except (VoiceError, OSError, subprocess.SubprocessError) as exception:
                error = str(exception)
            finally:
                with self._lock:
                    self._active = None
                    if generation == self._generation:
                        text = (
                            transcript
                            if transcript is not None and not cancel.is_set()
                            else self._snapshot.transcript
                        )
                        self._snapshot = VoiceSnapshot("review" if text else "idle", text, error)
                    else:
                        self._snapshot = VoiceSnapshot()
                self.on_change()

        self._executor.submit(work)

    def _update(self, generation: int, phase: str, elapsed: float = 0) -> None:
        with self._lock:
            if generation != self._generation or self._active is None or self._active.is_set():
                return
            self._snapshot = replace(self._snapshot, phase=phase, elapsed=elapsed)
        self.on_change()

    def import_wav(self, source: Path) -> None:
        def task(cancel: threading.Event, generation: int) -> str:
            return self.runtime.transcribe(source, cancel)

        self._start("transcribing", task)

    def record(self) -> None:
        def task(cancel: threading.Event, generation: int) -> str:
            with tempfile.TemporaryDirectory(prefix="miwl2-record-") as directory:
                audio = Path(directory) / "recording.wav"
                self.runtime.record(
                    audio,
                    cancel,
                    self._finish_recording,
                    lambda phase, elapsed: self._update(generation, phase, elapsed),
                )
                if cancel.is_set():
                    raise VoiceCancelled
                self._update(generation, "transcribing")
                return self.runtime.transcribe(audio, cancel)

        self._start("awaiting_permission", task)

    def speak(self, text: str) -> None:
        def task(cancel: threading.Event, generation: int) -> None:
            self.runtime.speak(text, cancel)

        self._start("speaking", task)

    def shutdown(self) -> None:
        self.stop()
        self._executor.shutdown(wait=True, cancel_futures=True)
