"""Capture the real Qt composer with disposable fictional data and no network."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import cast

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete

from miwl2.bridge import WorkspaceBridge
from miwl2.providers import DeterministicProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("before", "after"), required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests"))
    from test_qt import click, item, settle

    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with tempfile.TemporaryDirectory(prefix="miwl2-composer-") as directory:
        service = WorkspaceService(
            Store(Path(directory) / "workspace.sqlite3"),
            DeterministicProvider(chunk_delay=0.1, preparation_delay=8),
        )
        bridge = WorkspaceBridge(service)
        bridge.renameSession("Cedar Library · fictional composer check")
        source = (
            "Fictional evaluation: 21 of 28 survey respondents reported saving time. "
            "The survey was self-selected and had no randomized comparison group. "
            "These reports do not establish a causal improvement."
        )
        bridge.updateSource(source)
        bridge.updateResult("Fictional saved draft. Preserve this while stopping a response.")
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        warnings: list[str] = []
        engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
        engine.load(QUrl.fromLocalFile(str(root / "src/miwl2/ui/Main.qml")))
        assert engine.rootObjects()
        window = cast(QQuickWindow, engine.rootObjects()[0])
        window.setProperty("reduceMotion", True)
        QTest.qWait(200)
        captures: list[dict[str, object]] = []

        def capture(state: str, size: str) -> None:
            QTest.qWait(100)
            image = window.grabWindow()
            assert not image.isNull()
            path = root / "evidence" / f"Miwl-2-composer-{arguments.stage}-{size}-{state}.png"
            assert image.save(str(path))
            composer = item(window, "composer")
            position = composer.mapToScene(QPointF(0, 0))
            assert position.y() + composer.height() <= window.height()
            button = item(window, "sendButton")
            captures.append(
                {
                    "path": str(path.relative_to(root)),
                    "viewport": [window.width(), window.height()],
                    "pixels": [image.width(), image.height()],
                    "state": state,
                    "button_text": button.property("text"),
                    "button_enabled": button.isEnabled(),
                    "busy": bridge.busy,
                }
            )

        try:
            for label, size in (("normal", (1380, 844)), ("compact", (960, 720))):
                window.resize(*size)
                window.setProperty("sidebarVisible", label == "normal")
                window.setProperty("inspectorVisible", label == "normal")
                prompt = item(window, "promptEditor")
                prompt.setProperty("text", "")
                capture("disabled", label)
                assert not item(window, "sendButton").isEnabled()
                prompt.setProperty("text", "Explain the fictional survey results clearly.")
                prompt.forceActiveFocus()
                capture("ready", label)
                if arguments.stage == "after":
                    item(window, "sendButton").forceActiveFocus()
                    assert item(window, "sendButton").hasActiveFocus()
                    capture("send-focus", label)
                    picker = item(window, "operationPicker")
                    picker.setProperty("currentIndex", 1)
                    assert item(window, "sendButton").property("text") == "Write"
                    capture("write", label)
                    picker.setProperty("currentIndex", 0)
                prompt.setProperty(
                    "text",
                    "Explain these fictional survey results.\n"
                    "Keep the participant and respondent counts distinct.\n"
                    "Mention the self-selected survey and absent control group.\n"
                    "Avoid claiming a causal improvement.",
                )
                prompt.forceActiveFocus()
                capture("multiline", label)
                if arguments.stage == "after":
                    scroll = item(window, "promptScroll")
                    assert float(scroll.property("contentHeight")) <= float(
                        scroll.property("availableHeight")
                    ), "Four short lines should fit without a clipped last line"
                prompt.setProperty(
                    "text", "\n".join(f"Fictional requirement {i}" for i in range(40))
                )
                prompt.forceActiveFocus()
                prompt.setProperty("cursorPosition", len(str(prompt.property("text"))))
                QTest.keyClick(window, Qt.Key.Key_Down, Qt.KeyboardModifier.MetaModifier)
                capture("long", label)
                scroll = item(window, "promptScroll")
                assert float(scroll.property("contentHeight")) > float(
                    scroll.property("availableHeight")
                )
                prompt.setProperty("text", "Make the fictional draft shorter.")
                saved = bridge.resultText
                click(app, window, "sendButton")
                assert bridge.busy
                capture("busy", label)
                assert item(window, "sendButton").property("text") == "Stop"
                click(app, window, "sendButton")
                settle(app, bridge)
                assert bridge.resultText == saved
                assert service.store.last_job(bridge.currentSessionId)["state"] == "cancelled"
            assert bridge.sourceText == source
            assert not warnings, warnings
            (root / "evidence" / f"composer-{arguments.stage}-verification.json").write_text(
                json.dumps(
                    {
                        "method": "Real Qt window with QTest synthetic interactions",
                        "qt_platform": app.platformName(),
                        "captures": captures,
                        "source_preserved": True,
                        "saved_draft_preserved_on_stop": True,
                        "qml_warnings": warnings,
                        "sensors_opened": 0,
                        "network_calls": 0,
                        "user_workspaces_modified": False,
                    },
                    indent=2,
                )
                + "\n"
            )
            print(
                json.dumps(
                    {
                        "stage": arguments.stage,
                        "platform": app.platformName(),
                        "captures": len(captures),
                    }
                )
            )
        finally:
            window.setVisible(False)
            service.shutdown()
            delete(engine)


if __name__ == "__main__":
    run()
