"""Capture real styled QML controls in isolated synthetic workspaces; no sensors."""

from __future__ import annotations

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
from verify_documents import SOURCE

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
    from test_qt import click, item, settle_documents

    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with tempfile.TemporaryDirectory(prefix="miwl2-styled-controls-") as directory:
        data = Path(directory)
        service = WorkspaceService(Store(data / "workspace.sqlite3"), DeterministicProvider())
        bridge = WorkspaceBridge(service)
        bridge.renameSession("Cedar Library · fictional notes")
        bridge.updateSource(SOURCE)
        cameras = CameraBridge(CameraManager(service.store))
        voice = VoiceBridge(VoiceEngine(VoiceRuntime(VoicePaths.local(root))), bridge)
        vision = VisionBridge(
            Gallery(data / "gallery.sqlite3"), VisionRuntime(VisionPaths.local(root)), cameras
        )
        documents = DocumentsBridge(DocumentIndex(data / "documents.sqlite3"), bridge)
        engine = QQmlApplicationEngine()
        engine.addImageProvider("cameras", CameraImages(cameras.manager))
        for name, context in (
            ("bridge", bridge),
            ("cameraContext", cameras),
            ("voiceContext", voice),
            ("visionContext", vision),
            ("documentsContext", documents),
        ):
            engine.rootContext().setContextProperty(name, context)
        warnings: list[str] = []
        engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
        engine.load(QUrl.fromLocalFile(str(root / "src/miwl2/ui/Main.qml")))
        window = cast(QQuickWindow, engine.rootObjects()[0])
        previews: list[str] = []

        def capture(name: str) -> None:
            QTest.qWait(100)
            path = root / "evidence" / ("Miwl-2-controls-" + name + "-preview.png")
            assert window.grabWindow().save(str(path))
            previews.append(str(path.relative_to(root)))

        def close_popup(name: str) -> None:
            popup = window.findChild(QObject, name)
            assert popup is not None
            QMetaObject.invokeMethod(popup, "close")
            QTest.qWait(20)

        try:
            QTest.qWait(100)
            item(window, "promptEditor").setProperty(
                "text", "Help me explain the survey results without implying a causal improvement."
            )
            click(app, window, "operationPicker")
            capture("writing-menu")
            close_popup("operationPickerMenu")
            item(window, "promptEditor").forceActiveFocus()
            capture("writing-focus")
            click(app, window, "providerButton")
            click(app, window, "providerPicker")
            capture("provider-menu")
            click(app, window, "providerPickerOption1")
            item(window, "endpointField").forceActiveFocus()
            capture("provider-fields")
            item(window, "endpointField").setProperty("text", "http://example.invalid:11434")
            click(app, window, "saveProviderButton")
            assert bridge.providerError
            capture("provider-error")
            click(app, window, "providerPicker")
            click(app, window, "providerPickerOption2")
            capture("provider-readonly")
            close_popup("providerPopup")
            click(app, window, "voiceTab")
            item(window, "voiceTranscript").setProperty(
                "text",
                "These are fictional survey notes. 21 of 28 respondents reported saving time.",
            )
            item(window, "voiceTranscript").forceActiveFocus()
            capture("voice")
            click(app, window, "cameraTab")
            item(window, "cameraName0").setProperty(
                "text", "Study source · fictional configuration"
            )
            item(window, "cameraUrl0").setProperty("text", "http://127.0.0.1:12345/synthetic-video")
            item(window, "cameraUrl0").forceActiveFocus()
            capture("camera")
            click(app, window, "galleryTab")
            item(window, "galleryPassphrase").forceActiveFocus()
            capture("gallery-locked")
            vision.unlock("synthetic-disposable-qa-passphrase", True)
            while vision.busy:
                QTest.qWait(5)
            assert vision.unlocked
            click(app, window, "gallerySource")
            capture("gallery-menu")
            close_popup("gallerySourceMenu")
            vision.lock()
            source = data / "Cedar-pilot-synthetic.md"
            source.write_text(SOURCE)
            documents.importFile(QUrl.fromLocalFile(str(source)))
            settle_documents(app, documents)
            click(app, window, "documentsTab")
            item(window, "documentsQuestion").setProperty("text", "respondents saving time")
            click(app, window, "documentsSearch")
            settle_documents(app, documents)
            item(window, "documentsQuestion").forceActiveFocus()
            capture("documents")
            click(app, window, "conversationTab")
            window.resize(960, 720)
            click(app, window, "operationPicker")
            capture("compact-menu")
            close_popup("operationPickerMenu")
            assert not warnings, warnings
            (root / "evidence/controls-ui-verification.json").write_text(
                json.dumps(
                    {
                        "platform": app.platformName(),
                        "data": "isolated fictional fixtures",
                        "previews": previews,
                        "qml_warnings": warnings,
                        "real_sensors_opened": 0,
                        "provider_requests": 0,
                        "gallery": "disposable synthetic passphrase; no people/frames enrolled",
                        "states": [
                            "idle",
                            "focus",
                            "error",
                            "readOnly",
                            "disabled",
                            "selected-option",
                            "open-menu",
                            "compact",
                        ],
                    },
                    indent=2,
                )
                + "\n"
            )
            print(json.dumps({"previews": previews, "warnings": warnings}), flush=True)
        finally:
            window.setVisible(False)
            documents.shutdown()
            vision.shutdown()
            cameras.shutdown()
            voice.shutdown()
            service.shutdown()
            delete(engine)


if __name__ == "__main__":
    run()
