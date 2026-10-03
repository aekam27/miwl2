from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import cast

from PySide6.QtCore import QLockFile, QStandardPaths, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle

from miwl2.bridge import WorkspaceBridge
from miwl2.camera_ui import CameraBridge, CameraImages
from miwl2.cameras import CameraManager
from miwl2.documents import DocumentIndex
from miwl2.documents_ui import DocumentsBridge
from miwl2.gallery import Gallery
from miwl2.service import WorkspaceService
from miwl2.storage import StorageError, Store
from miwl2.vision import VisionPaths, VisionRuntime
from miwl2.vision_ui import VisionBridge
from miwl2.voice import VoiceEngine, VoicePaths, VoiceRuntime
from miwl2.voice_ui import VoiceBridge


def main(on_ready: Callable[[QQuickWindow], None] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Miwl 2 desktop writing workspace")
    parser.add_argument(
        "--data-dir", type=Path, help="Override the local session storage directory"
    )
    arguments = parser.parse_args()
    application = QGuiApplication(sys.argv[:1])
    application.setOrganizationName("Aekam")
    application.setApplicationName("Miwl 2")
    application.setApplicationDisplayName("Miwl 2")
    application.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "Miwl-2-app-icon.png")))
    QQuickStyle.setStyle("Basic")
    data_dir = arguments.data_dir or Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    instance_lock = QLockFile(str(data_dir / "workspace.lock"))
    if not instance_lock.tryLock(0):
        print(
            f"Miwl 2 is already open for {data_dir.resolve()}. Use the existing window.",
            file=sys.stderr,
        )
        return 2
    try:
        return open_workspace(application, data_dir, on_ready)
    except (OSError, sqlite3.Error, StorageError, ValueError) as exception:
        print(f"Miwl 2 could not open this workspace: {exception}", file=sys.stderr)
        return 1
    finally:
        instance_lock.unlock()


def open_workspace(
    application: QGuiApplication,
    data_dir: Path,
    on_ready: Callable[[QQuickWindow], None] | None,
) -> int:
    with ExitStack() as cleanup:
        store = Store(data_dir / "workspace.sqlite3")
        service = WorkspaceService(store, store.provider_configuration().build())
        cleanup.callback(service.shutdown)
        bridge = WorkspaceBridge(service)
        try:
            store.backup_if_due()
        except (OSError, sqlite3.Error, StorageError) as exception:
            bridge._notice = f"Automatic writing backup failed: {exception}"
        cameras = CameraManager(store)
        camera_bridge = CameraBridge(cameras)
        cleanup.callback(camera_bridge.shutdown)
        voice_bridge = VoiceBridge(
            VoiceEngine(VoiceRuntime(VoicePaths.local(Path(__file__).resolve().parents[2]))), bridge
        )
        cleanup.callback(voice_bridge.shutdown)
        vision_bridge = VisionBridge(
            Gallery(data_dir / "gallery.sqlite3"),
            VisionRuntime(VisionPaths.local(Path(__file__).resolve().parents[2])),
            camera_bridge,
        )
        cleanup.callback(vision_bridge.shutdown)
        documents_bridge = DocumentsBridge(DocumentIndex(data_dir / "documents.sqlite3"), bridge)
        cleanup.callback(documents_bridge.shutdown)
        engine = QQmlApplicationEngine()
        engine.addImageProvider("cameras", CameraImages(cameras))
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.rootContext().setContextProperty("cameraContext", camera_bridge)
        engine.rootContext().setContextProperty("voiceContext", voice_bridge)
        engine.rootContext().setContextProperty("visionContext", vision_bridge)
        engine.rootContext().setContextProperty("documentsContext", documents_bridge)
        engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "ui" / "Main.qml")))
        if not engine.rootObjects():
            return 1
        window = cast(QQuickWindow, engine.rootObjects()[0])
        window.setIcon(application.windowIcon())
        if on_ready is not None:
            on_ready(window)
        application.aboutToQuit.connect(service.cancel)
        exit_code = application.exec()
        del engine
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
