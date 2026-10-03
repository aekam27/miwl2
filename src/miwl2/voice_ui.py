from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from miwl2.bridge import WorkspaceBridge
from miwl2.voice import VoiceEngine, VoiceError


class VoiceBridge(QObject):
    changed = Signal()
    transcriptChanged = Signal()
    _changed = Signal()

    def __init__(self, engine: VoiceEngine, workspace: WorkspaceBridge) -> None:
        super().__init__()
        self.engine = engine
        self.workspace = workspace
        self._error = ""
        self._text = ""
        self._changed.connect(self.refresh)
        engine.on_change = self._changed.emit
        workspace.currentSessionChanged.connect(self._session_changed)
        workspace.voice_busy = lambda: engine.busy

    @Slot()
    def refresh(self) -> None:
        text = self.engine.snapshot.transcript
        if text != self._text:
            self._text = text
            self.transcriptChanged.emit()
        self.changed.emit()
        self.workspace.contextChanged.emit()

    @Slot()
    def _session_changed(self) -> None:
        self._error = ""
        self.engine.reset()
        self.refresh()

    @Property(bool, notify=changed)
    def available(self) -> bool:
        return self.engine.runtime.paths.available

    @Property(bool, notify=changed)
    def recordingAvailable(self) -> bool:
        return self.engine.runtime.paths.recording_available

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self.engine.busy

    @Property(str, notify=changed)
    def phase(self) -> str:
        return self.engine.snapshot.phase

    @Property(str, notify=changed)
    def statusText(self) -> str:
        phase = self.engine.snapshot.phase
        return {
            "idle": "Ready · local Whisper base · Samantha playback",
            "review": "Review and edit your transcript before sending",
            "awaiting_permission": "Waiting for the recording helper / microphone permission…",
            "recording": f"Recording · {self.engine.snapshot.elapsed:.0f} / 60 seconds",
            "transcribing": "Transcribing locally with Whisper base…",
            "speaking": "Speaking the saved draft with Samantha…",
            "stopping": "Stopping voice…",
            "finished": "Recording finished…",
        }.get(phase, phase)

    @Property(str, notify=transcriptChanged)
    def transcript(self) -> str:
        return self._text

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error or self.engine.snapshot.error

    def _ready(self) -> bool:
        if self.workspace.busy or self.busy or self.workspace.documents_busy():
            self._error = "Finish or stop the current response/voice task first."
            self.changed.emit()
            return False
        self._error = ""
        return True

    @Slot()
    def record(self) -> None:
        if self._ready():
            try:
                self.engine.record()
            except VoiceError as error:
                self._error = str(error)
                self.changed.emit()

    @Slot(QUrl)
    def transcribeFile(self, url: QUrl) -> None:
        if not self._ready():
            return
        if not url.isLocalFile():
            self._error = "Select a local WAV file. Remote audio is not fetched."
            self.changed.emit()
            return
        self.engine.import_wav(Path(url.toLocalFile()))

    @Slot(str)
    def editTranscript(self, text: str) -> None:
        self.engine.edit(text)

    @Slot()
    def finishRecording(self) -> None:
        self.engine.finish_recording()

    @Slot()
    def stop(self) -> None:
        self.engine.stop()

    @Slot()
    def sendTranscript(self) -> None:
        if not self._ready():
            return
        if self.workspace.service.store.provider_configuration().provider == "cloud":
            self._error = (
                "Voice transcripts stay local. Choose a local provider to send this transcript."
            )
            self.changed.emit()
            return
        text = self.engine.snapshot.transcript.strip()
        if not text:
            self._error = "Review or type a transcript first."
            self.changed.emit()
            return
        self.workspace.sendMessage(text)

    @Slot()
    def speakDraft(self) -> None:
        if self._ready():
            self.engine.speak(cast(str, self.workspace.resultText))

    def shutdown(self) -> None:
        self.engine.shutdown()
