from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QMetaObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete

from miwl2.bridge import WorkspaceBridge
from miwl2.providers import DeterministicProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store


@pytest.fixture(scope="module")
def writing_app() -> Iterator[QGuiApplication]:
    existing = QGuiApplication.instance()
    app = existing or QGuiApplication([])
    assert isinstance(app, QGuiApplication)
    app.setQuitOnLastWindowClosed(False)
    QQuickStyle.setStyle("Basic")
    yield app
    if existing is None:
        delete(app)


@pytest.fixture
def writing_ui(
    tmp_path: Path, writing_app: QGuiApplication
) -> Iterator[tuple[WorkspaceBridge, QQuickWindow]]:
    service = WorkspaceService(Store(tmp_path / "writing.sqlite3"), DeterministicProvider(0, 0))
    bridge = WorkspaceBridge(service)
    bridge.updateSource("Fictional saved source")
    bridge.updateResult("Fictional saved draft")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)
    warnings: list[str] = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/miwl2/ui/Main.qml")))
    assert engine.rootObjects()
    window = cast(QQuickWindow, engine.rootObjects()[0])
    window.setProperty("reduceMotion", True)
    QTest.qWait(20)
    try:
        yield bridge, window
    finally:
        window.setVisible(False)
        service.shutdown()
        delete(engine)
        writing_app.processEvents()
        assert not warnings, warnings


def editor(window: QQuickWindow, field: str) -> QQuickItem:
    result = window.findChild(QQuickItem, "sourceEditor" if field == "source" else "resultEditor")
    assert result is not None
    return result


def evaluate(window: QQuickWindow, expression: str) -> None:
    script = QQmlExpression(QQmlEngine.contextForObject(window), window, expression)
    script.evaluate()
    assert not script.hasError(), script.error().toString()


@pytest.mark.parametrize("field", ["source", "draft"])
@pytest.mark.parametrize("action", ["new", "switch", "close"])
def test_failed_editor_save_preserves_text_and_blocks_navigation_or_close_until_retry(
    writing_ui: tuple[WorkspaceBridge, QQuickWindow],
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    action: str,
) -> None:
    bridge, window = writing_ui
    first = bridge.currentSessionId
    other = bridge.service.store.create_session()
    bridge.refresh()
    pending = "Fictional unsaved " + field
    window.setProperty("activeView", 1 if field == "draft" else 0)
    editor(window, field).setProperty("text", pending)
    if action == "close":
        window.setProperty("activeView", 5)
    method = "update_source" if field == "source" else "update_result"

    def attempt() -> bool:
        if action == "new":
            evaluate(window, "newSession()")
        elif action == "switch":
            evaluate(window, "chooseSession(" + json.dumps(other) + ")")
        else:
            return window.close()
        return False

    with monkeypatch.context() as failure:
        failure.setattr(
            bridge.service.store,
            method,
            Mock(side_effect=sqlite3.OperationalError("fixture write denied")),
        )
        accepted = attempt()
        assert bridge.currentSessionId == first
        assert window.isVisible() and not accepted
        assert editor(window, field).property("text") == pending
        assert "fixture write denied" in bridge.errorMessage
        banner = window.findChild(QQuickItem, "errorBanner")
        assert banner is not None and banner.isVisible()
        assert len(bridge.service.store.list_sessions()) == 2
        stored = bridge.service.store.session(first)
        assert stored["source" if field == "source" else "result"] == "Fictional saved " + field

    accepted = attempt()
    stored = bridge.service.store.session(first)
    assert stored["source" if field == "source" else "result"] == pending
    assert not bridge.errorMessage
    if action == "close":
        assert accepted and not window.isVisible()
    else:
        assert bridge.currentSessionId != first
        if action == "switch":
            assert bridge.currentSessionId == other
        else:
            assert len(bridge.service.store.list_sessions()) == 3


@pytest.mark.parametrize("field", ["source", "draft"])
def test_successful_other_editor_save_does_not_hide_unsaved_text_error(
    writing_ui: tuple[WorkspaceBridge, QQuickWindow], monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    bridge, window = writing_ui
    failed = bridge.updateSource if field == "source" else bridge.updateResult
    succeeded = bridge.updateResult if field == "source" else bridge.updateSource
    method = "update_source" if field == "source" else "update_result"
    with monkeypatch.context() as failure:
        failure.setattr(
            bridge.service.store,
            method,
            Mock(side_effect=sqlite3.OperationalError("fixture write denied")),
        )
        failed_result = failed("Fictional pending edit")
        succeeded_result = succeeded("Fictional independently saved edit")
        bridge.dismissError()
        assert "fixture write denied" in bridge.errorMessage
        assert failed_result is False and succeeded_result is True
    assert failed("Fictional pending edit") is True
    assert not bridge.errorMessage


def test_failed_flush_does_not_send_stale_text_or_clear_the_prompt(
    writing_ui: tuple[WorkspaceBridge, QQuickWindow], monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, window = writing_ui
    editor(window, "source").setProperty("text", "Fictional unsaved source for this request")
    prompt = window.findChild(QQuickItem, "promptEditor")
    assert prompt is not None
    prompt.setProperty("text", "Fictional follow-up question")
    with monkeypatch.context() as failure:
        failure.setattr(
            bridge.service.store,
            "update_source",
            Mock(side_effect=sqlite3.OperationalError("fixture write denied")),
        )
        evaluate(window, "sendPrompt()")
        assert bridge.service.store.messages(bridge.currentSessionId) == []
        assert prompt.property("text") == "Fictional follow-up question"
        assert editor(window, "source").property("text").startswith("Fictional unsaved")
    evaluate(window, "sendPrompt()")
    deadline = time.monotonic() + 3
    while bridge.busy and time.monotonic() < deadline:
        QTest.qWait(5)
    assert not bridge.busy
    assert prompt.property("text") == ""
    job = bridge.service.store.last_job(bridge.currentSessionId)
    assert job is not None
    assert json.loads(job["request"])["source"] == "Fictional unsaved source for this request"


def test_failed_flush_does_not_claim_a_backup_of_pending_edits(
    writing_ui: tuple[WorkspaceBridge, QQuickWindow], monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, window = writing_ui
    editor(window, "draft").setProperty("text", "Fictional unsaved draft for backup")
    button = window.findChild(QQuickItem, "backupWorkspaceButton")
    assert button is not None
    with monkeypatch.context() as failure:
        failure.setattr(
            bridge.service.store,
            "update_result",
            Mock(side_effect=sqlite3.OperationalError("fixture write denied")),
        )
        assert QMetaObject.invokeMethod(button, "clicked")
        assert not list((bridge.service.store.path.parent / "writing-backups").glob("*.sqlite3"))
        assert "Writing backed up" not in bridge.noticeMessage
        assert editor(window, "draft").property("text") == "Fictional unsaved draft for backup"
    assert QMetaObject.invokeMethod(button, "clicked")
    snapshot = next((bridge.service.store.path.parent / "writing-backups").glob("*.sqlite3"))
    with sqlite3.connect(snapshot) as connection:
        assert (
            connection.execute("SELECT result FROM sessions").fetchone()[0]
            == "Fictional unsaved draft for backup"
        )
