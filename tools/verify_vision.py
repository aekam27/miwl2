"""Synthetic-only current-QML vision preview and real-network model smoke verification."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import cast

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete

from miwl2.bridge import WorkspaceBridge
from miwl2.camera_ui import CameraBridge, CameraImages
from miwl2.cameras import CameraManager, CameraSource
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
    from test_cameras import StreamFixture, stream_fixture
    from test_qt import click, item, wait_vision

    application = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    runtime = VisionRuntime(VisionPaths.local(root))
    started = time.perf_counter()
    smoke = runtime.synthetic_smoke()
    smoke["seconds"] = round(time.perf_counter() - started, 4)
    with tempfile.TemporaryDirectory(prefix="miwl2-vision-synthetic-") as directory:
        folder = Path(directory)
        service = WorkspaceService(Store(folder / "workspace.sqlite3"), DeterministicProvider(0, 0))
        workspace = WorkspaceBridge(service)
        workspace.renameSession("Synthetic vision check · no people")
        manager = CameraManager(service.store)
        cameras = CameraBridge(manager)
        voice = VoiceBridge(
            VoiceEngine(VoiceRuntime(VoicePaths.local(Path("/nonexistent-test-voice")))), workspace
        )
        vision = VisionBridge(Gallery(folder / "gallery.sqlite3"), runtime, cameras)
        engine = QQmlApplicationEngine()
        engine.addImageProvider("cameras", CameraImages(manager))
        for name, bridge in [
            ("bridge", workspace),
            ("cameraContext", cameras),
            ("voiceContext", voice),
            ("visionContext", vision),
        ]:
            engine.rootContext().setContextProperty(name, bridge)
        warnings: list[str] = []
        engine.warnings.connect(
            lambda errors: warnings.extend(error.toString() for error in errors)
        )
        engine.load(QUrl.fromLocalFile(str(root / "src/miwl2/ui/Main.qml")))
        assert engine.rootObjects()
        window = cast(QQuickWindow, engine.rootObjects()[0])
        first = StreamFixture(label="GENERATED FIXTURE · NO PEOPLE", continuous=True)
        second = StreamFixture(
            color="#795530", label="GENERATED FIXTURE · NO PEOPLE", continuous=True
        )
        try:
            click(application, window, "galleryTab")
            QTest.qWait(40)
            assert window.grabWindow().save(str(root / "evidence/Miwl-2-gallery-preview.png"))
            window.resize(960, 720)
            QTest.qWait(40)
            assert window.grabWindow().save(
                str(root / "evidence/Miwl-2-gallery-compact-preview.png")
            )
            window.resize(1380, 900)
            item(window, "galleryPassphrase").setProperty("text", "synthetic preview passphrase")
            click(application, window, "galleryUnlock")
            wait_vision(application, lambda: vision.unlocked and not vision.busy)
            assert vision.profiles == []
            QTest.qWait(40)
            assert window.grabWindow().save(
                str(root / "evidence/Miwl-2-enrollment-empty-preview.png")
            )
            with stream_fixture(first) as url1, stream_fixture(second) as url2:
                for index, url in enumerate((url1, url2)):
                    manager.configure(
                        index, CameraSource(f"Generated fixture {index + 1}", url, True)
                    )
                    cameras.connectSource(index)
                wait_vision(
                    application, lambda: all(row["state"] == "streaming" for row in cameras.sources)
                )
                click(application, window, "cameraTab")
                click(application, window, "cameraRecognitionConsent0")
                click(application, window, "cameraRecognitionConsent1")
                wait_vision(
                    application,
                    lambda: all(
                        row["result"] == "No usable face detected" for row in vision.sources
                    ),
                )
                assert window.grabWindow().save(
                    str(root / "evidence/Miwl-2-vision-synthetic-preview.png")
                )
                window.resize(960, 720)
                QTest.qWait(40)
                assert window.grabWindow().save(
                    str(root / "evidence/Miwl-2-vision-compact-preview.png")
                )
                results = [row["result"] for row in vision.sources]
                assert vision.profiles == []
                vision.lock()
                application.processEvents()
                assert not any(row["enabled"] for row in vision.sources)
                assert vision.profiles == []
            assert not warnings, warnings
        finally:
            vision.shutdown()
            cameras.shutdown()
            voice.shutdown()
            service.shutdown()
            window.setVisible(False)
            delete(engine)
    result = {
        "platform": application.platformName(),
        "qml_warnings": warnings,
        "real_model_smoke": smoke,
        "two_source_results": results,
        "gallery_empty_after_checks": True,
        "generated_jpeg_streams_only": True,
        "passphrase": "public synthetic test input in removed temporary directory",
        "no_real_people_or_face_images": True,
        "no_camera_device_or_remote_feed": True,
        "real_face_accuracy_tested": False,
        "preview_kind": "current Qt UI on offscreen backend; real YuNet sees no faces",
        "previews": [
            "Miwl-2-gallery-preview.png",
            "Miwl-2-gallery-compact-preview.png",
            "Miwl-2-enrollment-empty-preview.png",
            "Miwl-2-vision-synthetic-preview.png",
            "Miwl-2-vision-compact-preview.png",
        ],
    }
    (root / "evidence/vision-ui-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    run()
