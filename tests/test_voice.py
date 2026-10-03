from __future__ import annotations

import struct
import sys
import threading
import time
import wave
from pathlib import Path

import pytest

from miwl2.voice import (
    VoiceCancelled,
    VoiceEngine,
    VoiceError,
    VoicePaths,
    VoiceRuntime,
    run_process,
    validate_wav,
)


def wav(path: Path, seconds: float = 0.2, silent: bool = False, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(struct.pack("<h", 0 if silent else 2000) * int(seconds * rate))


@pytest.mark.parametrize(
    "seconds,silent,rate", [(61, False, 16000), (1, True, 16000), (1, False, 8000)]
)
def test_wav_limits_and_silence_gate(
    tmp_path: Path, seconds: float, silent: bool, rate: int
) -> None:
    path = tmp_path / "record.wav"
    wav(path, seconds, silent, rate)
    with pytest.raises(VoiceError):
        validate_wav(path)


def test_precancel_never_starts_a_process() -> None:
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(VoiceCancelled):
        run_process(["/does/not/exist"], cancel, 1)


def test_stop_interrupts_owned_process_promptly() -> None:
    cancel = threading.Event()
    errors: list[Exception] = []

    def run() -> None:
        try:
            run_process([sys.executable, "-c", "import time; time.sleep(10)"], cancel, 12)
        except VoiceCancelled as error:
            errors.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.05)
    start = time.monotonic()
    cancel.set()
    worker.join(timeout=1)
    assert not worker.is_alive() and len(errors) == 1
    assert time.monotonic() - start < 0.8


class BlockingRuntime(VoiceRuntime):
    def __init__(self, directory: Path) -> None:
        super().__init__(VoicePaths(directory / "cli", directory / "model", directory / "helper"))
        self.entered, self.release = threading.Event(), threading.Event()
        self.spoken = ""

    def transcribe(self, source: Path, cancel: threading.Event) -> str:
        self.entered.set()
        self.release.wait(1)
        return "Late transcript from the previous session."

    def speak(self, text: str, cancel: threading.Event) -> None:
        self.spoken = text
        self.entered.set()
        self.release.wait(1)


def wait(engine: VoiceEngine) -> None:
    deadline = time.monotonic() + 2
    while engine.busy and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not engine.busy


def test_session_switch_discards_late_transcript_and_keeps_single_worker(tmp_path: Path) -> None:
    runtime = BlockingRuntime(tmp_path)
    engine = VoiceEngine(runtime)
    try:
        engine.edit("Existing unsent text")
        engine.import_wav(tmp_path / "source.wav")
        assert runtime.entered.wait(1)
        with pytest.raises(VoiceError, match="Stop"):
            engine.import_wav(tmp_path / "another.wav")
        engine.reset()
        runtime.release.set()
        wait(engine)
        assert engine.snapshot.transcript == "" and engine.snapshot.phase == "idle"
    finally:
        runtime.release.set()
        engine.shutdown()


def test_cancel_preserves_prior_transcript_and_playback_snapshot(tmp_path: Path) -> None:
    runtime = BlockingRuntime(tmp_path)
    engine = VoiceEngine(runtime)
    try:
        engine.edit("Reviewed text")
        engine.speak("Only this draft")
        assert runtime.entered.wait(1)
        engine.edit("Ignored during playback")
        engine.stop()
        runtime.release.set()
        wait(engine)
        assert engine.snapshot.transcript == "Reviewed text"
        assert runtime.spoken == "Only this draft"
    finally:
        runtime.release.set()
        engine.shutdown()


def test_transcription_temp_output_cleanup_and_real_command_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = VoicePaths(tmp_path / "cli", tmp_path / "model", tmp_path / "helper")
    paths.whisper.touch()
    paths.model.touch()
    source = tmp_path / "input.wav"
    wav(source)
    output_paths: list[Path] = []

    def fake(
        arguments: list[str], cancel: threading.Event, timeout: float, stdin: bytes | None = None
    ) -> str:
        assert arguments[0] == str(paths.whisper) and "auto" in arguments
        assert timeout == 120 and stdin is None
        output = Path(arguments[arguments.index("-of") + 1]).with_suffix(".txt")
        output_paths.append(output)
        output.write_text(" Synthetic transcript. ")
        return ""

    monkeypatch.setattr("miwl2.voice.run_process", fake)
    runtime = VoiceRuntime(paths)
    assert runtime.transcribe(source, threading.Event()) == "Synthetic transcript."
    assert output_paths and not output_paths[0].parent.exists()


def test_playback_limits_do_not_start_process(tmp_path: Path) -> None:
    runtime = VoiceRuntime(VoicePaths(tmp_path / "cli", tmp_path / "model", tmp_path / "helper"))
    for text in ("", "x" * 5001):
        with pytest.raises(VoiceError):
            runtime.speak(text, threading.Event())
