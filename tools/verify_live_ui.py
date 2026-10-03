"""Opt-in Qt control verification against the approved installed local model."""

from __future__ import annotations

import json
import tempfile
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
from miwl2.domain import JobState
from miwl2.ollama import OllamaProvider
from miwl2.providers import TEST_LABEL
from miwl2.service import WorkspaceService
from miwl2.storage import Store


def run() -> None:
    application = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with tempfile.TemporaryDirectory(prefix="miwl2-live-ui-") as directory:
        store = Store(Path(directory) / "workspace.sqlite3")
        configuration = ProviderConfiguration("ollama")
        store.save_provider_configuration(configuration)
        provider = OllamaProvider(configuration.endpoint, configuration.model)
        service = WorkspaceService(store, provider)
        bridge = WorkspaceBridge(service)
        bridge.updateSource(SOURCE)
        bridge.renameSession("Cedar Library · local AI check")
        engine = QQmlApplicationEngine()
        warnings: list[str] = []
        engine.warnings.connect(
            lambda errors: warnings.extend(error.toString() for error in errors)
        )
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/miwl2/ui/Main.qml")))
        window = cast(QQuickWindow, engine.rootObjects()[0])
        window.resize(1380, 820)
        QTest.qWait(30)

        def item(name: str) -> QQuickItem:
            result = window.findChild(QQuickItem, name)
            assert result is not None, name
            return result

        def click(name: str) -> None:
            target = item(name)
            assert target.isVisible() and target.isEnabled()
            point = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
            QTest.mouseClick(
                window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint()
            )
            application.processEvents()

        results: list[dict[str, object]] = []

        def finish(operation: str, started: float) -> None:
            while bridge.busy and time.monotonic() - started < 40:
                QTest.qWait(5)
            application.processEvents()
            assert not bridge.busy, "Live model response did not finish"
            job = store.last_job(bridge.currentSessionId)
            assert job is not None and job["state"] == JobState.COMPLETED, bridge.errorMessage
            assert json.loads(job["request"])["operation"] == operation
            assert job["provider_is_test"] == 0 and bridge.resultText.strip()
            assert not bridge.resultText.startswith(TEST_LABEL)
            assert item("resultEditor").property("text") == bridge.resultText
            results.append(
                {
                    "operation": operation,
                    "elapsed_seconds": time.monotonic() - started,
                    "job_state": job["state"],
                    "provider": job["provider"],
                    "output": bridge.resultText,
                }
            )
            print(
                json.dumps(
                    {k: results[-1][k] for k in ("operation", "elapsed_seconds", "job_state")}
                ),
                flush=True,
            )

        try:
            started = time.monotonic()
            click("summarizeButton")
            finish("summarize", started)
            started = time.monotonic()
            click("paraphraseButton")
            finish("paraphrase", started)
            picker = item("operationPicker")
            picker.forceActiveFocus()
            QTest.keyClick(window, Qt.Key.Key_Down)
            application.processEvents()
            assert picker.property("currentIndex") == 1
            item("promptEditor").setProperty(
                "text",
                "Write a 150-word report for library staff, "
                "using the fictional source and its limitations.",
            )
            started = time.monotonic()
            click("sendButton")
            finish("article", started)
            picker.forceActiveFocus()
            QTest.keyClick(window, Qt.Key.Key_Up)
            application.processEvents()
            assert picker.property("currentIndex") == 0
            item("promptEditor").setProperty(
                "text", "Make the draft shorter, preserving the numbers and uncertainty."
            )
            started = time.monotonic()
            click("sendButton")
            finish("chat", started)
            click("draftTab")
            click("copyResultButton")
            assert QGuiApplication.clipboard().text() == bridge.resultText
            assert Store(store.path).session(bridge.currentSessionId)["result"] == bridge.resultText
            QTest.qWait(250)
            preview = Path("evidence/Miwl-2-local-AI-preview.png")
            assert window.grabWindow().save(str(preview))
            assert warnings == [], warnings
            Path("evidence/local-ui-inference.json").write_text(
                json.dumps(
                    {
                        "platform": application.platformName(),
                        "data": "isolated synthetic fixture",
                        "results": results,
                        "qml_warnings": warnings,
                        "draft_copy_correct": True,
                        "restart_persistence_correct": True,
                        "preview": str(preview),
                        "limitation": (
                            "Qt controls exercised in offscreen mode; "
                            "the Mac was locked, blocking native CUA checks."
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
        finally:
            service.shutdown()
            window.setVisible(False)
            delete(engine)


if __name__ == "__main__":
    run()
