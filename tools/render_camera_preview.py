"""Render actual camera controls decoding two explicitly synthetic loopback fixtures."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete

from miwl2.bridge import WorkspaceBridge
from miwl2.camera_ui import CameraBridge, CameraImages
from miwl2.cameras import CameraManager, CameraSource
from miwl2.providers import DeterministicProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store


def run() -> None:
    # The existing dev fixtures are the only network sources this tool opens.
    sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))
    from test_cameras import StreamFixture, stream_fixture

    application = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with tempfile.TemporaryDirectory(prefix="miwl2-cameras-") as directory:
        service = WorkspaceService(
            Store(Path(directory) / "workspace.sqlite3"), DeterministicProvider(0, 0)
        )
        bridge = WorkspaceBridge(service)
        manager = CameraManager(service.store)
        context = CameraBridge(manager)
        first = StreamFixture(label="LOCAL SYNTHETIC FIXTURE 1")
        second = StreamFixture(color="#795530", label="LOCAL SYNTHETIC FIXTURE 2")
        with stream_fixture(first) as url1, stream_fixture(second) as url2:
            manager.configure(0, CameraSource("Synthetic blue source", url1, True))
            manager.configure(1, CameraSource("Synthetic amber source", url2, True))
            engine = QQmlApplicationEngine()
            engine.addImageProvider("cameras", CameraImages(manager))
            engine.rootContext().setContextProperty("bridge", bridge)
            engine.rootContext().setContextProperty("cameraContext", context)
            warnings: list[str] = []
            engine.warnings.connect(
                lambda errors: warnings.extend(error.toString() for error in errors)
            )
            engine.load(
                QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/miwl2/ui/Main.qml"))
            )
            assert engine.rootObjects()
            window = engine.rootObjects()[0]
            window.resize(1380, 900)
            window.setProperty("activeView", 2)
            manager.connect(0)
            manager.connect(1)
            deadline = time.monotonic() + 2
            while any(image.isNull() for image in manager.frames) and time.monotonic() < deadline:
                QTest.qWait(5)
            assert all(not image.isNull() for image in manager.frames)
            QTest.qWait(250)
            assert window.grabWindow().save("evidence/Miwl-2-camera-fixture-preview.png")
            assert not warnings, warnings
            Path("evidence/camera-fixture-verification.json").write_text(
                json.dumps(
                    {
                        "sources": "two generated JPEG streams from localhost fixtures",
                        "platform": application.platformName(),
                        "qml_warnings": warnings,
                        "remote_stream_accessed": False,
                        "camera_device_accessed": False,
                        "biometric_collection": False,
                        "recognition_implemented": False,
                        "frames_decoded": manager.frame_revisions,
                        "preview": "Miwl-2-camera-fixture-preview.png",
                    },
                    indent=2,
                )
                + "\n"
            )
            context.shutdown()
            service.shutdown()
            window.setVisible(False)
            delete(engine)
    print("Synthetic camera preview saved; no device or remote feed used.")


if __name__ == "__main__":
    run()
