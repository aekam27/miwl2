"""Opt-in real local ASR/LLM and file-only Samantha synthesis using synthetic audio."""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
from pathlib import Path
from typing import cast

from benchmark_local import SOURCE
from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete

from miwl2.bridge import WorkspaceBridge
from miwl2.configuration import ProviderConfiguration
from miwl2.service import WorkspaceService
from miwl2.storage import Store
from miwl2.voice import VoiceEngine, VoicePaths, VoiceRuntime, run_process
from miwl2.voice_ui import VoiceBridge


def run() -> None:
    root = Path(__file__).resolve().parents[1]
    _application = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with tempfile.TemporaryDirectory(prefix="miwl2-voice-qa-") as directory:
        folder = Path(directory)
        source = folder / "synthetic.wav"
        run_process(
            ["/usr/bin/say", "-v", "Samantha", "-r", "160", "-o", str(folder / "synthetic.aiff")],
            threading.Event(),
            20,
            b"Summarize the Cedar Library pilot. "
            b"Twenty one of twenty eight respondents reported saving time.",
        )
        run_process(
            [
                "/usr/bin/afconvert",
                "-f",
                "WAVE",
                "-d",
                "LEI16@16000",
                "-c",
                "1",
                str(folder / "synthetic.aiff"),
                str(source),
            ],
            threading.Event(),
            20,
        )

        class FilePlayback(VoiceRuntime):
            def speak(self, text: str, cancel: threading.Event) -> None:
                run_process(
                    [
                        str(self.paths.say),
                        "-v",
                        "Samantha",
                        "-r",
                        "175",
                        "-o",
                        str(folder / "reply.aiff"),
                    ],
                    cancel,
                    30,
                    text.encode(),
                )

        runtime = FilePlayback(VoicePaths.local(root))
        voice = VoiceEngine(runtime)
        store = Store(folder / "workspace.sqlite3")
        config = ProviderConfiguration("ollama")
        store.save_provider_configuration(config)
        service = WorkspaceService(store, config.build())
        bridge = WorkspaceBridge(service)
        bridge.updateSource(SOURCE)
        bridge.renameSession("Cedar Library · voice check")
        voice_bridge = VoiceBridge(voice, bridge)
        engine = QQmlApplicationEngine()
        warnings: list[str] = []
        engine.warnings.connect(
            lambda errors: warnings.extend(error.toString() for error in errors)
        )
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.rootContext().setContextProperty("voiceContext", voice_bridge)
        engine.load(QUrl.fromLocalFile(str(root / "src/miwl2/ui/Main.qml")))
        window = cast(QQuickWindow, engine.rootObjects()[0])
        window.resize(1380, 900)
        QTest.qWait(40)

        def item(name: str) -> QQuickItem:
            result = window.findChild(QQuickItem, name)
            assert result is not None, name
            return result

        def click(name: str) -> None:
            target = item(name)
            assert target.isVisible() and target.isEnabled(), name
            point = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
            QTest.mouseClick(
                window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint()
            )
            QTest.qWait(5)

        def settle() -> None:
            deadline = time.monotonic() + 60
            while (voice.busy or service.active is not None) and time.monotonic() < deadline:
                QTest.qWait(10)
            assert not voice.busy and service.active is None
            QTest.qWait(20)

        try:
            click("voiceTab")
            voice_bridge.transcribeFile(QUrl.fromLocalFile(str(source)))
            QTest.qWait(100)
            started = time.monotonic()
            click("voiceCancelButton")
            settle()
            cancel_seconds = time.monotonic() - started
            assert not voice.snapshot.transcript
            voice_bridge.transcribeFile(QUrl.fromLocalFile(str(source)))
            settle()
            assert not voice.snapshot.error and "28" in voice.snapshot.transcript
            recognized = voice.snapshot.transcript
            assert item("voiceTranscript").property("text") == recognized
            assert not store.messages(cast(str, bridge.currentSessionId))
            edited = (
                "Summarize the fictional Cedar Library pilot in one paragraph. "
                "Preserve the survey numbers and uncertainty."
            )
            item("voiceTranscript").setProperty("text", edited)
            click("voiceSendButton")
            settle()
            job = store.last_job(cast(str, bridge.currentSessionId))
            assert job and job["state"] == "completed" and not job["provider_is_test"]
            click("voiceSpeakButton")
            settle()
            assert (folder / "reply.aiff").stat().st_size > 1000
            assert window.grabWindow().save(str(root / "evidence/Miwl-2-voice-preview.png"))
            window.resize(960, 720)
            QTest.qWait(40)
            assert window.grabWindow().save(str(root / "evidence/Miwl-2-voice-compact-preview.png"))
            report = {
                "input": "Samantha-generated synthetic speech; no microphone input",
                "audio_seconds": runtime.last_duration,
                "asr_seconds": runtime.last_transcription_seconds,
                "recognized": recognized,
                "reviewed_transcript": edited,
                "cancel_seconds": cancel_seconds,
                "saved_response": cast(str, bridge.resultText),
                "tts": "Real Samantha synthesis to a temporary AIFF file; no audible playback",
                "microphone_tested": False,
                "recording_helper": "Built/signature-verified; live permission/capture untested",
                "model_sha256": hashlib.sha256(runtime.paths.model.read_bytes()).hexdigest(),
                "temporary_audio_retention": "QA directory removed; recording/ASR audio discarded",
                "qml_warnings": warnings,
                "ui_sizes": [[1380, 900], [960, 720]],
            }
            assert not warnings, warnings
            (root / "evidence/voice-verification.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            print(
                json.dumps(
                    {
                        k: report[k]
                        for k in ("audio_seconds", "asr_seconds", "cancel_seconds", "recognized")
                    }
                ),
                flush=True,
            )
        finally:
            window.setVisible(False)
            voice_bridge.shutdown()
            service.shutdown()
            delete(engine)


if __name__ == "__main__":
    run()
