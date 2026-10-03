"""Native Cocoa Qt daily-use checks with fictional temporary data; no sensors/cloud."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import cast

from PySide6.QtCore import QMetaObject, QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete

from miwl2.bridge import WorkspaceBridge
from miwl2.camera_ui import CameraBridge, CameraImages
from miwl2.cameras import CameraManager
from miwl2.documents import DocumentIndex
from miwl2.documents_ui import DocumentsBridge
from miwl2.gallery import Gallery
from miwl2.providers import DeterministicProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store
from miwl2.vision import VisionPaths, VisionRuntime
from miwl2.vision_ui import VisionBridge
from miwl2.voice import VoiceEngine, VoicePaths, VoiceRuntime
from miwl2.voice_ui import VoiceBridge


def run() -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests"))
    from test_qt import click, item, settle, settle_documents

    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with tempfile.TemporaryDirectory(prefix="miwl2-daily-use-") as directory:
        data = Path(directory)
        service = WorkspaceService(Store(data / "workspace.sqlite3"), DeterministicProvider(0, 5))
        bridge = WorkspaceBridge(service)
        bridge.renameSession("Cedar Library · fictional daily-use check")
        bridge.updateSource(
            "Fictional survey: 21 of 28 respondents reported saving time. No control group."
        )
        bridge.updateResult("Fictional edited draft. Preserve this while stopping.")
        cameras = CameraBridge(CameraManager(service.store))
        voice = VoiceBridge(VoiceEngine(VoiceRuntime(VoicePaths.local(root))), bridge)
        vision = VisionBridge(
            Gallery(data / "gallery.sqlite3"), VisionRuntime(VisionPaths.local(root)), cameras
        )
        documents = DocumentsBridge(DocumentIndex(data / "documents.sqlite3"), bridge)
        engine = QQmlApplicationEngine()
        engine.addImageProvider("cameras", CameraImages(cameras.manager))
        for name, value in [
            ("bridge", bridge),
            ("cameraContext", cameras),
            ("voiceContext", voice),
            ("visionContext", vision),
            ("documentsContext", documents),
        ]:
            engine.rootContext().setContextProperty(name, value)
        warnings: list[str] = []
        engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
        engine.load(QUrl.fromLocalFile(str(root / "src/miwl2/ui/Main.qml")))
        window = cast(QQuickWindow, engine.rootObjects()[0])
        window.setProperty("reduceMotion", True)
        captures = []

        def capture(name: str) -> None:
            QTest.qWait(100)
            path = root / "evidence" / ("Miwl-2-daily-use-" + name + ".png")
            assert window.grabWindow().save(str(path))
            captures.append(str(path.relative_to(root)))

        try:
            for name, size in [("normal", (1380, 844)), ("compact", (960, 720))]:
                window.resize(*size)
                window.setProperty("sidebarVisible", name == "normal")
                window.setProperty("inspectorVisible", name == "normal")
                QTest.qWait(100)
                for _ in range(2):
                    click(app, window, "summarizeButton")
                    assert bridge.busy
                    click(app, window, "sendButton")
                    settle(app, bridge)
                    assert bridge.resultText.startswith("Fictional edited draft")
                    assert service.store.last_job(bridge.currentSessionId)["state"] == "cancelled"
                click(app, window, "providerButton")
                click(app, window, "backupWorkspaceButton")
                assert "Writing backed up" in bridge.noticeMessage
                assert list((data / "writing-backups").glob("*.sqlite3"))
                capture(name + "-backup")
                popup = window.findChild(QObject, "providerPopup")
                assert popup is not None
                QMetaObject.invokeMethod(popup, "close")
                capture(name + "-writing")
            service.provider = DeterministicProvider(0, 0.1)
            bridge.setSimulateFailure(True)
            bridge.summarize()
            settle(app, bridge)
            assert bridge.retryAvailable
            bridge.retry()
            settle(app, bridge)
            assert not bridge.errorMessage
            document = data / "Cedar-fictional.md"
            document.write_text(
                "# Fictional survey\n21 of 28 respondents reported saving time.\n"
                "No control group.\n"
            )
            digest = hashlib.sha256(document.read_bytes()).hexdigest()
            for _ in range(2):
                documents.importFile(QUrl.fromLocalFile(str(document)))
                settle_documents(app, documents)
                click(app, window, "documentsTab")
                item(window, "documentsQuestion").setProperty("text", "respondents saving time")
                click(app, window, "documentsSearch")
                settle_documents(app, documents)
                result = documents.results[0]
                click(app, window, "documentCitation" + str(result["id"]))
                QTest.qWait(180)
                assert item(window, "documentCitationText").property("text") == document.read_text()
                capture("compact-citation")
                reader = window.findChild(QObject, "documentCitationDialog")
                assert reader is not None
                QMetaObject.invokeMethod(reader, "close")
                QTest.qWait(180)
                identifier = documents.documents[0]["id"]
                click(app, window, "documentDelete" + identifier)
                QTest.qWait(180)
                dialog = window.findChild(QObject, "documentRemoveDialog")
                capture("compact-remove-request")
                print(
                    json.dumps(
                        {
                            "remove_visible": dialog.property("visible") if dialog else None,
                            "remove_opened": dialog.property("opened") if dialog else None,
                            "reader_visible": reader.property("visible"),
                            "window_active": window.isActive(),
                        }
                    ),
                    flush=True,
                )
                assert dialog is not None and dialog.property("opened")
                assert documents.documents
                QMetaObject.invokeMethod(dialog, "accept")
                settle_documents(app, documents)
                QTest.qWait(180)
                assert not documents.documents and not documents.index.search("respondents")
            assert hashlib.sha256(document.read_bytes()).hexdigest() == digest
            assert not warnings, warnings
            report = {
                "platform": app.platformName(),
                "viewports": [[1380, 844], [960, 720]],
                "stop_runs": 4,
                "saved_draft_preserved": True,
                "failure_retry": True,
                "backup_control": True,
                "document_import_search_citation_confirmed_removal_runs": 2,
                "original_document_unchanged": True,
                "qml_warnings": warnings,
                "captures": captures,
                "real_sensors": 0,
                "cloud_calls": 0,
                "limits": (
                    "Import invoked with a local QUrl; Qt interactions do not verify "
                    "the OS file picker or Mac accessibility/Dock behavior."
                ),
            }
            (root / "evidence/daily-use-verification.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            print(json.dumps(report), flush=True)
        finally:
            documents.shutdown()
            vision.shutdown()
            service.shutdown()
            cameras.shutdown()
            voice.shutdown()
            window.setVisible(False)
            delete(engine)


if __name__ == "__main__":
    run()
