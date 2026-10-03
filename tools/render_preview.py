"""Capture the actual Miwl 2 viewport with isolated data, natively or offscreen."""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from shiboken6 import delete

from miwl2.bridge import WorkspaceBridge
from miwl2.providers import DeterministicProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=1380)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--populate-history", action="store_true")
    parser.add_argument(
        "--capture-delay-ms",
        type=int,
        default=400,
        help="Delay capture for native visual inspection; no input automation.",
    )
    parser.add_argument(
        "--view", choices=("conversation", "draft", "empty"), default="conversation"
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = arguments.output or root / "evidence/Miwl-2-workspace-preview.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    app.setApplicationName("Miwl 2")
    QQuickStyle.setStyle("Basic")
    with tempfile.TemporaryDirectory(prefix="miwl2-preview-") as directory:
        service = WorkspaceService(
            Store(Path(directory) / "preview.sqlite3"), DeterministicProvider(0, 0)
        )
        bridge = WorkspaceBridge(service)
        bridge.renameSession("Project notes")
        if arguments.view != "empty":
            bridge.loadSample()
            bridge.renameSession("Project notes")
            for action in (bridge.summarize, lambda: bridge.sendMessage("make it shorter")):
                action()
                deadline = time.monotonic() + 5
                while bridge.busy and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(0.005)
                assert not bridge.busy, "Test provider did not finish"
            if arguments.populate_history:
                first = bridge.currentSessionId
                for title in ("Reading notes", "Design details and decisions for the next version"):
                    bridge.newSession()
                    bridge.renameSession(title)
                bridge.selectSession(first)
        app.processEvents()
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.load(QUrl.fromLocalFile(str(root / "src/miwl2/ui/Main.qml")))
        assert engine.rootObjects(), "Actual app QML failed to load"
        window = engine.rootObjects()[0]
        window.setProperty("width", arguments.width)
        window.setProperty("height", arguments.height)
        window.setProperty("activeView", 1 if arguments.view == "draft" else 0)
        # Cocoa can deliver its initial native geometry after QML has loaded.
        # Apply the requested test dimensions once that first event has settled.
        QTimer.singleShot(200, lambda: window.resize(arguments.width, arguments.height))

        def capture() -> None:
            picture = window.grabWindow()
            assert not picture.isNull(), "Qt returned an empty render"
            assert picture.save(str(output)), "Preview image save failed"
            print(
                f"{output} ({picture.width()}x{picture.height()} pixels; "
                f"{window.width()}x{window.height()} viewport; {app.platformName()})"
            )
            app.quit()

        QTimer.singleShot(arguments.capture_delay_ms, capture)
        app.exec()
        service.shutdown()
        delete(engine)


if __name__ == "__main__":
    main()
