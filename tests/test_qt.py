from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from typing import cast

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete
from test_cameras import StreamFixture, stream_fixture

from miwl2.bridge import SAMPLE_SOURCE, WorkspaceBridge
from miwl2.camera_ui import CameraBridge, CameraImages
from miwl2.cameras import CameraManager
from miwl2.documents import DocumentIndex
from miwl2.documents_ui import DocumentsBridge
from miwl2.domain import Operation, ProviderInfo, ProviderRequest
from miwl2.gallery import Gallery
from miwl2.providers import TEST_LABEL, DeterministicProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store
from miwl2.vision import VisionPaths, VisionRuntime
from miwl2.vision_ui import VisionBridge
from miwl2.voice import VoiceEngine, VoicePaths, VoiceRuntime
from miwl2.voice_ui import VoiceBridge


@pytest.fixture(scope="module")
def app() -> QGuiApplication:
    application = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    return application


@pytest.fixture
def bridge(tmp_path: Path, app: QGuiApplication) -> Iterator[WorkspaceBridge]:
    service = WorkspaceService(Store(tmp_path / "ui.sqlite3"), DeterministicProvider(0, 0.01))
    result = WorkspaceBridge(service)
    yield result
    service.shutdown()
    app.processEvents()


def settle(app: QGuiApplication, bridge: WorkspaceBridge) -> None:
    deadline = time.monotonic() + 3
    while bridge.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert not bridge.busy


@pytest.fixture
def ui(app: QGuiApplication, bridge: WorkspaceBridge) -> Iterator[QQuickWindow]:
    engine = QQmlApplicationEngine()
    cameras = CameraManager(bridge.service.store)
    camera_context = CameraBridge(cameras)
    camera_context.setParent(bridge)
    engine.addImageProvider("cameras", CameraImages(cameras))
    engine.rootContext().setContextProperty("cameraContext", camera_context)
    voice_context = VoiceBridge(
        VoiceEngine(VoiceRuntime(VoicePaths.local(Path("/nonexistent-miwl-test-runtime")))), bridge
    )
    voice_context.setParent(bridge)
    engine.rootContext().setContextProperty("voiceContext", voice_context)
    vision_context = VisionBridge(
        Gallery(bridge.service.store.path.parent / "test-gallery.sqlite3"),
        VisionRuntime(VisionPaths.local(Path("/nonexistent-miwl-test-runtime"))),
        camera_context,
    )
    vision_context.setParent(bridge)
    engine.rootContext().setContextProperty("visionContext", vision_context)
    documents_context = DocumentsBridge(
        DocumentIndex(bridge.service.store.path.parent / "test-documents.sqlite3"), bridge
    )
    documents_context.setParent(bridge)
    engine.rootContext().setContextProperty("documentsContext", documents_context)
    warnings: list[str] = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/miwl2/ui/Main.qml")))
    assert engine.rootObjects()
    window = cast(QQuickWindow, engine.rootObjects()[0])
    QTest.qWait(20)
    yield window
    window.setVisible(False)
    documents_context.shutdown()
    vision_context.shutdown()
    camera_context.shutdown()
    voice_context.shutdown()
    delete(engine)
    assert warnings == [], "QML runtime warnings: " + "\n".join(warnings)


def item(window: QQuickWindow, name: str) -> QQuickItem:
    result = window.findChild(QQuickItem, name)
    if result is None:
        # ListView delegates live in the visual tree, outside QObject parent ownership.
        def visual_child(parent: QQuickItem) -> QQuickItem | None:
            if parent.objectName() == name:
                return parent
            for child in parent.childItems():
                found = visual_child(child)
                if found is not None:
                    return found
            return None

        result = visual_child(window.contentItem())
    assert result is not None, name
    return result


def click(app: QGuiApplication, window: QQuickWindow, name: str) -> None:
    QTest.qWait(20)  # Let visible-view layout and scroll bounds settle before coordinates.
    target = item(window, name)
    assert target.isVisible() and target.isEnabled(), name
    ancestor = target.parentItem()
    while ancestor is not None:
        if ancestor.metaObject().indexOfProperty("contentY") >= 0:
            position = target.mapToItem(ancestor, QPointF(0, 0))
            viewport = ancestor.height()
            if viewport > 0 and (position.y() < 0 or position.y() + target.height() > viewport):
                content_y = float(ancestor.property("contentY"))
                maximum = max(0.0, float(ancestor.property("contentHeight")) - viewport)
                ancestor.setProperty(
                    "contentY",
                    max(
                        0.0,
                        min(maximum, content_y + position.y() - (viewport - target.height()) / 2),
                    ),
                )
                QTest.qWait(20)
            break
        ancestor = ancestor.parentItem()
    point = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
    QTest.mouseClick(
        window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint()
    )
    app.processEvents()


def test_voice_transcript_review_sends_only_after_explicit_action_and_session_switch_clears_it(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    click(app, ui, "voiceTab")
    assert not item(ui, "voiceRecordButton").isEnabled()
    assert not item(ui, "voiceImportButton").isEnabled()
    editor = item(ui, "voiceTranscript")
    editor.setProperty("text", "Summarize these synthetic notes.")
    app.processEvents()
    assert bridge.service.store.messages(bridge.currentSessionId) == []
    click(app, ui, "voiceSendButton")
    settle(app, bridge)
    assert (
        bridge.service.store.messages(bridge.currentSessionId)[0]["body"]
        == "Summarize these synthetic notes."
    )
    bridge.newSession()
    app.processEvents()
    assert editor.property("text") == ""


class CloudUiFixture(DeterministicProvider):
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo("cloud-fixture", "Cloud fixture · no network", True, "cloud")


def test_cloud_ui_requires_per_request_confirmation_and_blocks_voice_transmission(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    assert bridge.configureProvider("cloud", "https://api.openai.com/v1", "synthetic-model")
    bridge.service.provider = CloudUiFixture(0, 0)
    app.processEvents()
    editor = item(ui, "promptEditor")
    editor.setProperty("text", "Synthetic request")
    app.processEvents()
    assert item(ui, "cloudConsent").isVisible()
    assert not item(ui, "sendButton").isEnabled()
    click(app, ui, "cloudConsent")
    assert item(ui, "sendButton").isEnabled()
    click(app, ui, "sendButton")
    settle(app, bridge)
    assert not item(ui, "cloudConsent").property("checked")
    assert len(bridge.service.store.messages(bridge.currentSessionId)) == 2
    click(app, ui, "voiceTab")
    item(ui, "voiceTranscript").setProperty("text", "Audio-derived synthetic text")
    app.processEvents()
    click(app, ui, "voiceSendButton")
    assert "local" in str(item(ui, "voiceError").property("text"))
    assert len(bridge.service.store.messages(bridge.currentSessionId)) == 2


def test_cloud_provider_popup_and_compact_voice_layout_fit(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    ui.resize(960, 640)
    app.processEvents()
    click(app, ui, "providerButton")
    picker = item(ui, "providerPicker")
    picker.forceActiveFocus()
    QTest.keyClick(ui, Qt.Key.Key_Down)
    QTest.keyClick(ui, Qt.Key.Key_Down)
    app.processEvents()
    assert picker.property("currentIndex") == 2
    item(ui, "modelField").setProperty("text", "synthetic-model")
    click(app, ui, "saveProviderButton")
    assert bridge.providerKind == "cloud"
    click(app, ui, "voiceTab")
    panel = item(ui, "voicePanel")
    assert panel.width() > 600 and panel.height() > 200
    assert item(ui, "voiceTranscript").isVisible()


def test_explicit_paraphrase_and_article_controls(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    bridge.loadSample()
    app.processEvents()
    click(app, ui, "paraphraseButton")
    settle(app, bridge)
    job = bridge.service.store.last_job(bridge.currentSessionId)
    assert job is not None and '"operation": "paraphrase"' in job["request"]
    assert "does not paraphrase" in bridge.resultText
    picker = item(ui, "operationPicker")
    picker.forceActiveFocus()
    QTest.keyClick(ui, Qt.Key.Key_Down)
    app.processEvents()
    assert picker.property("currentIndex") == 1
    editor = item(ui, "promptEditor")
    editor.forceActiveFocus()
    editor.setProperty("text", "A practical article about local writing tools")
    click(app, ui, "sendButton")
    settle(app, bridge)
    job = bridge.service.store.last_job(bridge.currentSessionId)
    assert job is not None and '"operation": "article"' in job["request"]
    assert "fixed test outline" in bridge.resultText


def test_provider_popup_saves_configuration_without_inference_and_validates_address(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    click(app, ui, "providerButton")
    picker = item(ui, "providerPicker")
    picker.forceActiveFocus()
    QTest.keyClick(ui, Qt.Key.Key_Down)
    app.processEvents()
    assert picker.property("currentIndex") == 1
    endpoint = item(ui, "endpointField")
    endpoint.setProperty("text", "http://example.com:11434")
    click(app, ui, "saveProviderButton")
    assert bridge.providerError and bridge.providerIsTest
    endpoint.setProperty("text", "http://127.0.0.1:11434")
    click(app, ui, "saveProviderButton")
    assert bridge.providerKind == "ollama" and not bridge.providerIsTest
    assert bridge.providerModel == "gemma3:4b" and not bridge.providerError
    assert bridge.service.active is None
    assert bridge.service.store.messages(bridge.currentSessionId) == []
    # Switching providers cannot retroactively change the fixture draft label.
    bridge.configureProvider("deterministic", "http://127.0.0.1:11434", "gemma3:4b")
    bridge.service.provider = DeterministicProvider(0, 0)
    bridge.updateSource("A saved fixture draft.")
    bridge.service.start(bridge.currentSessionId, Operation.SUMMARIZE)
    settle(app, bridge)
    bridge.updateResult("Edited fixture draft")
    bridge.configureProvider("ollama", "http://127.0.0.1:11434", "gemma3:4b")
    bridge.copyResult()
    assert QGuiApplication.clipboard().text().startswith(TEST_LABEL)


def test_camera_controls_connect_only_synthetic_sources_and_keep_views_isolated(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    context = bridge.findChild(CameraBridge)
    assert context is not None
    first, second = StreamFixture(), StreamFixture(color="#bd7632")
    with stream_fixture(first) as url1, stream_fixture(second) as url2:
        click(app, ui, "cameraTab")
        assert ui.property("activeView") == 2
        assert not item(ui, "composer").isVisible()
        assert not item(ui, "cameraConnect0").isEnabled()
        for index, url in enumerate((url1, url2)):
            item(ui, f"cameraName{index}").setProperty("text", f"Synthetic source {index + 1}")
            item(ui, f"cameraUrl{index}").setProperty("text", url)
            click(app, ui, f"cameraAuthorized{index}")
            click(app, ui, f"cameraSave{index}")
        assert first.connections == second.connections == 0
        assert all(row["authorized"] and row["url"] for row in context.sources), context.sources
        click(app, ui, "cameraConnect0")
        click(app, ui, "cameraConnect1")
        deadline = time.monotonic() + 2
        while (
            any(image.isNull() for image in context.manager.frames) and time.monotonic() < deadline
        ):
            QTest.qWait(5)
        app.processEvents()
        assert all(not image.isNull() for image in context.manager.frames)
        assert "connected" in str(item(ui, "cameraState0").property("text"))
        assert "connected" in str(item(ui, "cameraState1").property("text"))
        assert bridge.service.store.messages(bridge.currentSessionId) == []
        # Frame updates must not destroy/recreate a partially edited URL field.
        item(ui, "cameraUrl0").setProperty("text", "http://127.0.0.1:12345/unsaved")
        context.manager.on_change()
        app.processEvents()
        assert item(ui, "cameraUrl0").property("text") == "http://127.0.0.1:12345/unsaved"
        click(app, ui, "cameraPause0")
        click(app, ui, "cameraStop1")
        context.manager.wait_stopped()
        app.processEvents()
        assert context.manager.snapshot()[0]["state"] == "paused"
        assert context.manager.snapshot()[1]["state"] == "stopped"
        click(app, ui, "conversationTab")
        assert item(ui, "composer").isVisible()
        assert not bridge.busy


@pytest.mark.parametrize("width", [960, 1380])
def test_camera_setup_layout_remains_scrollable_at_compact_sizes(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow, width: int
) -> None:
    ui.resize(width, 640)
    click(app, ui, "cameraTab")
    QTest.qWait(30)
    panel = item(ui, "cameraPanel")
    assert panel.width() > 0 and panel.height() > 0
    assert item(ui, "cameraUrl0").width() > 250
    assert item(ui, "cameraUrl1").width() > 250
    assert not item(ui, "cameraConnect0").isEnabled()
    assert not item(ui, "cameraConnect1").isEnabled()


def test_actual_qml_load_and_bridge_roundtrip(
    app: QGuiApplication, bridge: WorkspaceBridge
) -> None:
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)
    path = Path(__file__).parents[1] / "src/miwl2/ui/Main.qml"
    engine.load(QUrl.fromLocalFile(str(path)))
    assert engine.rootObjects(), "Actual desktop QML did not load"
    window = engine.rootObjects()[0]
    source = window.findChild(QObject, "sourceEditor")
    output = window.findChild(QObject, "resultEditor")
    assert source is not None and output is not None
    bridge.loadSample()
    app.processEvents()
    assert source.property("text") == SAMPLE_SOURCE
    bridge.summarize()
    settle(app, bridge)
    assert str(output.property("text")).startswith(TEST_LABEL)
    bridge.updateResult("An edited result")
    bridge.copyResult()
    assert QGuiApplication.clipboard().text().startswith(TEST_LABEL)
    assert "An edited result" in QGuiApplication.clipboard().text()
    first = bridge.currentSessionId
    bridge.newSession()
    app.processEvents()
    assert source.property("text") == "" and output.property("text") == ""
    bridge.selectSession(first)
    app.processEvents()
    assert source.property("text") == SAMPLE_SOURCE
    assert output.property("text") == "An edited result"
    window.setProperty("visible", False)
    delete(engine)


def test_switch_during_job_does_not_show_previous_session_output(
    app: QGuiApplication, bridge: WorkspaceBridge
) -> None:
    bridge.loadSample()
    first = bridge.currentSessionId
    bridge.summarize()
    bridge.newSession()
    second = bridge.currentSessionId
    settle(app, bridge)
    assert second != first
    assert bridge.sourceText == "" and bridge.resultText == ""
    assert bridge.messages == []
    assert bridge.service.store.last_job(first)["state"] == "cancelled"


def test_failure_retry_and_reopen_error_state(
    app: QGuiApplication, bridge: WorkspaceBridge
) -> None:
    bridge.loadSample()
    bridge.setSimulateFailure(True)
    bridge.summarize()
    settle(app, bridge)
    assert "Simulated" in bridge.errorMessage
    assert bridge.retryAvailable
    assert not bridge.simulateFailure
    bridge.retry()
    settle(app, bridge)
    assert not bridge.errorMessage
    assert bridge.resultText.startswith(TEST_LABEL)


def test_desktop_navigation_typing_draft_copy_and_session_search(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    assert ui.title() == "Miwl 2"
    click(app, ui, "sampleButton")
    click(app, ui, "summarizeButton")
    settle(app, bridge)
    first = bridge.currentSessionId
    bridge.renameSession("Research notes")
    prompt = item(ui, "promptEditor")
    prompt.setProperty("text", "make it shorter")
    prompt.forceActiveFocus()
    QTest.keyClick(ui, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    settle(app, bridge)
    assert "Shorter preview" in bridge.resultText
    assert prompt.property("text") == ""
    QTest.keyClick(ui, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert ui.property("activeView") == 1
    output = item(ui, "resultEditor")
    output.forceActiveFocus()
    QTest.keyClick(ui, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(ui, Qt.Key.Key_X)
    app.processEvents()
    assert output.property("text") == "x"
    click(app, ui, "copyResultButton")
    assert bridge.resultText == "x"
    assert QGuiApplication.clipboard().text() == TEST_LABEL + "\n\nx"
    click(app, ui, "newSessionButton")
    assert bridge.messages == [] and bridge.resultText == ""
    search = item(ui, "sessionSearch")
    search.setProperty("text", "research")
    QTest.qWait(20)
    assert item(ui, "sessionsView").property("count") == 1
    click(app, ui, "session_" + first)
    assert bridge.sourceText == SAMPLE_SOURCE and bridge.resultText == "x"
    assert item(ui, "resultEditor").property("text") == "x"


def test_pending_source_edits_survive_stream_refreshes(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    click(app, ui, "sampleButton")
    click(app, ui, "summarizeButton")
    source = item(ui, "sourceEditor")
    typed = "A new unsaved sentence. Another sentence."
    source.setProperty("text", typed)
    deadline = time.monotonic() + 1
    while bridge.busy and time.monotonic() < deadline:
        app.processEvents()
        assert source.property("text") == typed
        time.sleep(0.005)
    QTest.qWait(380)
    assert bridge.sourceText == typed
    assert source.property("text") == typed


@pytest.mark.parametrize("size", [(960, 640), (1100, 720), (1380, 900), (1720, 1000)])
def test_responsive_layout_keeps_composer_and_source_reachable(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow, size: tuple[int, int]
) -> None:
    ui.resize(*size)
    QTest.qWait(30)
    composer = item(ui, "composer")
    position = composer.mapToScene(QPointF(0, 0))
    assert composer.width() >= 300 and composer.height() >= 105
    assert position.x() >= 0 and position.x() + composer.width() <= ui.width()
    assert position.y() >= 0 and position.y() + composer.height() <= ui.height()
    assert QMetaObject.invokeMethod(ui, "focusSource")
    QTest.qWait(20)
    inspector = item(ui, "sourceInspector")
    assert inspector.isVisible()
    assert item(ui, "sourceEditor").hasActiveFocus()
    if size[0] < 1180:
        assert not item(ui, "sidebar").isVisible()
    position = inspector.mapToScene(QPointF(0, 0))
    assert position.x() + inspector.width() <= ui.width()
    assert position.y() + inspector.height() <= ui.height()
    for name in ("sidebarToggle", "inspectorToggle", "summarizeButton", "sendButton"):
        control = item(ui, name)
        assert str(control.property("text")).strip()
        label = cast(QQuickItem, control.property("contentItem"))
        assert label.width() >= label.implicitWidth(), name
    if item(ui, "sidebar").isVisible():
        click(app, ui, "sidebarToggle")
        QTest.qWait(20)
    click(app, ui, "sidebarToggle")
    assert item(ui, "sidebar").isVisible()
    if size[0] < 1180:
        assert not item(ui, "sourceInspector").isVisible()


def test_visible_provider_controls_cancellation_failure_and_retry(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    click(app, ui, "sampleButton")
    click(app, ui, "summarizeButton")
    click(app, ui, "sendButton")
    settle(app, bridge)
    assert bridge.service.store.last_job(bridge.currentSessionId)["state"] == "cancelled"
    click(app, ui, "providerButton")
    QTest.qWait(20)
    click(app, ui, "failureToggle")
    click(app, ui, "reduceMotionToggle")
    assert ui.property("reduceMotion")
    assert ui.property("motionDuration") == 0
    popup = ui.findChild(QObject, "providerPopup")
    assert popup is not None and QMetaObject.invokeMethod(popup, "close")
    app.processEvents()
    click(app, ui, "summarizeButton")
    settle(app, bridge)
    assert item(ui, "errorBanner").isVisible() and bridge.retryAvailable
    click(app, ui, "retryButton")
    settle(app, bridge)
    assert not item(ui, "errorBanner").isVisible()
    assert bridge.resultText.startswith(TEST_LABEL)


def test_sidebar_history_groups_long_titles_and_keyboard_selection(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    first = bridge.currentSessionId
    title = "A long session title that must truncate without covering neighboring controls"
    bridge.renameSession(title)
    bridge.newSession()
    second = bridge.currentSessionId
    yesterday = (datetime.now().astimezone() - timedelta(days=1)).isoformat()
    with bridge.service.store.connection() as connection:
        connection.execute("UPDATE sessions SET updated_at=? WHERE id=?", (yesterday, first))
    bridge.refresh()
    QTest.qWait(20)
    assert [row["historyGroup"] for row in bridge.sessions] == ["Today", "Yesterday"]
    control = item(ui, "session_" + first)
    assert control.property("text") == title
    assert control.width() <= item(ui, "sessionsView").width()
    sessions = item(ui, "sessionsView")
    sessions.setProperty("currentIndex", 0)
    sessions.forceActiveFocus()
    QTest.keyClick(ui, Qt.Key.Key_Down)
    QTest.keyClick(ui, Qt.Key.Key_Return)
    app.processEvents()
    assert bridge.currentSessionId == first and bridge.currentSessionId != second
    item(ui, "sessionSearch").setProperty("text", "unmatched search")
    app.processEvents()
    assert sessions.property("count") == 0
    assert "No matching" in str(item(ui, "emptyHistoryLabel").property("text"))
    click(app, ui, "clearSearchButton")
    assert item(ui, "sessionSearch").property("text") == ""
    assert sessions.property("count") == 2


def test_text_and_functional_accent_contrast(ui: QQuickWindow) -> None:
    def luminance(value: object) -> float:
        color = QColor(value)
        channels = (color.redF(), color.greenF(), color.blueF())
        linear = [
            part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4
            for part in channels
        ]
        return sum(
            part * weight for part, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)
        )

    def contrast(a: object, b: object) -> float:
        light, dark = sorted((luminance(a), luminance(b)), reverse=True)
        return (light + 0.05) / (dark + 0.05)

    for foreground in (ui.property("ink"), ui.property("muted")):
        for surface in ("#ffffff", "#f6f6f3", "#e8ede4"):
            assert contrast(foreground, surface) >= 4.5
    assert contrast("#ffffff", ui.property("accent")) >= 4.5
    assert contrast(ui.property("accent"), "#e3ecfb") >= 4.5


def wait_vision(app: QGuiApplication, condition: object, seconds: float = 3) -> None:
    from collections.abc import Callable

    check = cast(Callable[[], bool], condition)
    deadline = time.monotonic() + seconds
    while not check() and time.monotonic() < deadline:
        QTest.qWait(5)
    assert check()
    app.processEvents()


def test_gallery_ui_and_two_source_matching_use_only_mock_enrollment_and_synthetic_streams(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    from unittest.mock import PropertyMock, patch

    import numpy as np

    from miwl2.vision import FaceSample

    vision = bridge.findChild(VisionBridge)
    cameras = bridge.findChild(CameraBridge)
    assert vision is not None and cameras is not None
    click(app, ui, "galleryTab")
    item(ui, "galleryPassphrase").setProperty("text", "synthetic UI passphrase")
    app.processEvents()
    click(app, ui, "galleryUnlock")
    assert item(ui, "galleryPassphrase").property("text") == ""
    wait_vision(app, lambda: vision.unlocked and not vision.busy)
    assert not item(ui, "galleryEnroll").isEnabled()

    class MockRuntime(VisionRuntime):
        def samples(self, image: object, enrollment: bool = False) -> list[FaceSample]:
            descriptor = np.zeros(128, dtype=np.float32)
            descriptor[0] = 1
            return [FaceSample((10, 10, 60, 60), 1.0, descriptor)]

    vision.runtime = MockRuntime(vision.runtime.paths)
    # Advertise model availability; this UI test uses only synthetic mock descriptors.
    with patch.object(VisionPaths, "available", new_callable=PropertyMock, return_value=True):
        vision.changed.emit()
        with (
            stream_fixture(StreamFixture()) as first,
            stream_fixture(StreamFixture(color="#bd7632")) as second,
        ):
            assert cameras.configure(0, "Synthetic 1", first, True)
            assert cameras.configure(1, "Synthetic 2", second, True)
            cameras.connectSource(0)
            cameras.connectSource(1)
            wait_vision(app, lambda: all(row["state"] == "streaming" for row in cameras.sources))
            item(ui, "galleryName").setProperty("text", "Synthetic consent fixture")
            app.processEvents()
            assert not item(ui, "galleryEnroll").isEnabled()
            click(app, ui, "galleryEnrollmentConsent")
            click(app, ui, "galleryEnroll")
            assert not item(ui, "galleryEnrollmentConsent").property("checked")
            wait_vision(app, lambda: len(vision.profiles) == 1)
            assert b"Synthetic consent fixture" not in vision.gallery.path.read_bytes()
            click(app, ui, "cameraTab")
            click(app, ui, "cameraRecognitionConsent0")
            click(app, ui, "cameraRecognitionConsent1")
            assert all(row["enabled"] for row in vision.sources), vision.sources
            wait_vision(
                app, lambda: all("Possible match" in row["result"] for row in vision.sources)
            )
            assert all(row["enabled"] for row in vision.sources)
            cameras.pause(0)
            wait_vision(app, lambda: not vision.sources[0]["enabled"])
            assert "Possible match" not in vision.sources[0]["result"]
            click(app, ui, "galleryTab")
            identifier = vision.profiles[0]["id"]
            click(app, ui, "galleryDelete" + identifier)
            dialog = ui.findChild(QObject, "galleryDeleteDialog")
            assert dialog is not None and dialog.property("visible")
            assert len(vision.profiles) == 1  # Opening the confirmation does not delete.
            assert QMetaObject.invokeMethod(dialog, "accept")
            wait_vision(app, lambda: vision.profiles == [])
            wait_vision(app, lambda: "Unknown" in vision.sources[1]["result"])
            vision.lock()
            app.processEvents()
            assert vision.profiles == [] and not any(row["enabled"] for row in vision.sources)
            assert all("Possible match" not in row["result"] for row in vision.sources)


def test_gallery_late_enrollment_is_discarded_after_source_stop(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    import threading

    import numpy as np

    from miwl2.vision import FaceSample

    vision = bridge.findChild(VisionBridge)
    cameras = bridge.findChild(CameraBridge)
    assert vision is not None and cameras is not None
    vision.unlock("synthetic stale passphrase", True)
    wait_vision(app, lambda: vision.unlocked and not vision.busy)
    entered, release = threading.Event(), threading.Event()

    class DelayedRuntime(VisionRuntime):
        def samples(self, image: object, enrollment: bool = False) -> list[FaceSample]:
            entered.set()
            assert release.wait(3)
            descriptor = np.zeros(128, dtype=np.float32)
            descriptor[0] = 1
            return [FaceSample((10, 10, 60, 60), 1.0, descriptor)]

    vision.runtime = DelayedRuntime(vision.runtime.paths)
    with stream_fixture(StreamFixture()) as source:
        assert cameras.configure(0, "Synthetic delayed source", source, True)
        cameras.connectSource(0)
        wait_vision(app, lambda: cameras.sources[0]["state"] == "streaming")
        vision.enroll(0, "Late synthetic enrollment", True)
        assert entered.wait(2)
        cameras.stop(0)
        app.processEvents()
        release.set()
        wait_vision(app, lambda: not vision.busy)
        assert vision.profiles == []


def test_gallery_compact_layout_and_default_off_are_visible(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    vision = bridge.findChild(VisionBridge)
    assert vision is not None and not vision.unlocked
    assert not vision.gallery.exists
    assert not any(row["enabled"] for row in vision.sources)
    ui.resize(960, 720)
    app.processEvents()
    click(app, ui, "galleryTab")
    assert item(ui, "galleryPassphrase").isVisible()
    assert not item(ui, "galleryUnlock").isEnabled()
    assert not item(ui, "composer").isVisible()
    for name in ("galleryPassphrase", "galleryUnlock"):
        target = item(ui, name)
        point = target.mapToScene(QPointF(0, 0))
        assert 0 <= point.x() <= ui.width() - target.width()
        assert point.y() + target.height() <= ui.height()


def test_stale_received_frame_is_rejected_even_after_a_late_ui_notification(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    from unittest.mock import PropertyMock, patch

    from PySide6.QtGui import QImage

    vision = bridge.findChild(VisionBridge)
    cameras = bridge.findChild(CameraBridge)
    assert vision is not None and cameras is not None
    vision.unlock("synthetic stale-frame passphrase", True)
    wait_vision(app, lambda: vision.unlocked and not vision.busy)
    frame = QImage(100, 100, QImage.Format.Format_RGB888)
    frame.fill(QColor("#245dc9"))
    with cameras.manager._lock:
        cameras.manager.frames[0] = frame
        cameras.manager.frame_times[0] = time.monotonic() - 10
        cameras.manager.frame_revisions[0] += 1
        cameras.manager.states[0] = ("streaming", "Synthetic stale frame")
    cameras.manager.on_change()
    app.processEvents()
    vision.enroll(0, "Rejected synthetic input", True)
    assert "fresh frame" in vision.error and not vision.busy and vision.profiles == []
    with patch.object(VisionPaths, "available", new_callable=PropertyMock, return_value=True):
        vision.enableSource(0, True)
        vision._tick()
        assert vision.sources[0]["result"] == "Waiting for a fresh connected frame"
        assert not vision.busy


def test_source_change_during_unlock_preserves_gallery_notification_and_idle_lock(
    app: QGuiApplication,
    bridge: WorkspaceBridge,
    ui: QQuickWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    import numpy as np
    from PySide6.QtTest import QSignalSpy

    vision = bridge.findChild(VisionBridge)
    cameras = bridge.findChild(CameraBridge)
    assert vision is not None and cameras is not None
    passphrase = "synthetic concurrent unlock passphrase"
    gallery = vision.gallery
    gallery.unlock(passphrase, True, gallery.generation)
    descriptor = np.zeros(128, dtype=np.float32)
    descriptor[0] = 1
    gallery.add("Synthetic stored fixture", descriptor, True, gallery.generation)
    gallery.lock()
    entered, release = threading.Event(), threading.Event()
    original = gallery._derive

    def delayed(passphrase: str, salt: bytes) -> bytes:
        entered.set()
        assert release.wait(3)
        return original(passphrase, salt)

    monkeypatch.setattr(gallery, "_derive", delayed)
    notifications = QSignalSpy(vision.profilesChanged)
    vision.unlock(passphrase, False)
    assert entered.wait(2)
    assert cameras.configure(0, "Synthetic source change", "", False)
    app.processEvents()
    release.set()
    wait_vision(app, lambda: vision.unlocked and not vision.busy)
    assert "Gallery unlocked" in vision.statusText
    assert notifications.count() == 1
    assert vision.profiles[0]["name"] == "Synthetic stored fixture"
    vision._last_active = time.monotonic() - 601
    vision._tick()
    assert not vision.unlocked and vision.profiles == []
    assert notifications.count() == 2


class DocumentProviderFixture(DeterministicProvider):
    def __init__(self, wait_for_release: bool = False) -> None:
        super().__init__(0, 0)
        self.requests: list[ProviderRequest] = []
        self.started = Event()
        self.release = Event()
        self.closed = Event()
        self.wait_for_release = wait_for_release

    def stream(self, request: ProviderRequest, cancel: Event) -> Iterator[str]:
        self.requests.append(request)
        self.started.set()
        if self.wait_for_release:
            self.release.wait(2)
        try:
            evidence = json.loads(request.source)["evidence"][0]
            yield json.dumps(
                {"claims": [{"citation": evidence["citation"], "quote": evidence["text"]}]}
            )
        finally:
            self.closed.set()


def documents_context(bridge: WorkspaceBridge) -> DocumentsBridge:
    context = bridge.findChild(DocumentsBridge)
    assert context is not None
    return context


def settle_documents(app: QGuiApplication, context: DocumentsBridge) -> None:
    deadline = time.monotonic() + 4
    while context.busy and time.monotonic() < deadline:
        QTest.qWait(5)
    app.processEvents()
    assert not context.busy


def import_synthetic_document(
    app: QGuiApplication, bridge: WorkspaceBridge, tmp_path: Path
) -> DocumentsBridge:
    source = tmp_path / "synthetic-selected.md"
    source.write_text("Fictional Cedar pilot: 21 of 28 survey respondents reported saving time.\n")
    context = documents_context(bridge)
    context.importFile(QUrl.fromLocalFile(str(source)))
    settle_documents(app, context)
    assert len(context.documents) == 1 and context.documents[0]["selected"]
    return context


def test_documents_screen_search_citation_compact_and_confirmed_removal(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow, tmp_path: Path
) -> None:
    context = import_synthetic_document(app, bridge, tmp_path)
    source = tmp_path / "synthetic-selected.md"
    original = source.read_bytes()
    click(app, ui, "documentsTab")
    item(ui, "documentsQuestion").setProperty("text", "respondents saving time")
    click(app, ui, "documentsSearch")
    settle_documents(app, context)
    result = context.results[0]
    click(app, ui, "documentCitation" + str(result["id"]))
    assert item(ui, "documentCitationText").property("text") == source.read_text()
    reader = ui.findChild(QObject, "documentCitationDialog")
    assert reader is not None and reader.property("opened")
    assert item(ui, "documentCitationBackground").property("color") == QColor("#ffffff")
    citation_scroll = item(ui, "documentCitationScroll")
    assert float(citation_scroll.property("contentHeight")) <= float(
        citation_scroll.property("availableHeight")
    )
    QMetaObject.invokeMethod(reader, "close")
    ui.resize(960, 720)
    QTest.qWait(20)
    for name in ("documentsImport", "documentsSearch", "documentsQuote", "documentsStop"):
        button = item(ui, name)
        position = button.mapToScene(QPointF(0, 0))
        assert 0 <= position.x() < ui.width() - button.width(), name
    click(app, ui, "documentDelete" + context.documents[0]["id"])
    dialog = ui.findChild(QObject, "documentRemoveDialog")
    assert dialog is not None and dialog.property("opened")
    assert context.documents
    QMetaObject.invokeMethod(dialog, "accept")
    settle_documents(app, context)
    assert context.documents == [] and context.results == [] and context.citation == {}
    assert source.read_bytes() == original


def test_document_model_context_excludes_writing_and_cloud_calls(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow, tmp_path: Path
) -> None:
    context = import_synthetic_document(app, bridge, tmp_path)
    bridge.updateSource("PRIVATE_WRITING_SENTINEL")
    provider = DocumentProviderFixture()
    bridge.service.provider = provider
    bridge.contextChanged.emit()
    context.search("respondents")
    settle_documents(app, context)
    context.chooseQuotations()
    settle_documents(app, context)
    assert "Verified" in context.statusText and context.results
    request = provider.requests[0]
    assert request.history == () and request.previous_result == ""
    assert "PRIVATE_WRITING_SENTINEL" not in request.source + request.prompt
    assert bridge.service.store.messages(bridge.currentSessionId) == []
    cloud = CloudUiFixture()
    bridge.service.provider = cloud
    bridge.contextChanged.emit()
    click(app, ui, "documentsTab")
    assert not item(ui, "documentsQuote").isEnabled()
    context.chooseQuotations()
    assert "local" in context.error and not context.busy
    assert len(provider.requests) == 1


@pytest.mark.parametrize("invalidate", ["stop", "selection", "provider"])
def test_document_late_output_discarded_and_writing_blocked_during_model_task(
    app: QGuiApplication,
    bridge: WorkspaceBridge,
    ui: QQuickWindow,
    tmp_path: Path,
    invalidate: str,
) -> None:
    context = import_synthetic_document(app, bridge, tmp_path)
    provider = DocumentProviderFixture(wait_for_release=True)
    bridge.service.provider = provider
    bridge.contextChanged.emit()
    context.search("respondents")
    settle_documents(app, context)
    context.chooseQuotations()
    assert provider.started.wait(1)
    bridge.sendMessage("must not save this while Documents runs")
    assert bridge.service.store.messages(bridge.currentSessionId) == []
    if invalidate == "stop":
        context.stop()
    elif invalidate == "selection":
        context.selectDocument(context.documents[0]["id"], False)
    else:
        bridge.service.provider = DeterministicProvider()
        bridge.contextChanged.emit()
    provider.release.set()
    settle_documents(app, context)
    assert context.results == [] and context.citation == {} and provider.closed.is_set()
    assert ("Sources changed" if invalidate == "selection" else "discarded") in context.statusText


def test_document_restart_requires_selection_and_remote_urls_never_import(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow, tmp_path: Path
) -> None:
    context = import_synthetic_document(app, bridge, tmp_path)
    context.importFile(QUrl("https://example.invalid/private.md"))
    assert "Remote URLs" in context.error and len(context.documents) == 1
    reopened = DocumentsBridge(DocumentIndex(context.index.path), bridge)
    try:
        assert reopened.documents and not reopened.documents[0]["selected"]
        reopened.search("respondents")
        assert "Select at least one" in reopened.error and not reopened.busy
    finally:
        reopened.shutdown()


def test_styled_dropdown_mouse_keyboard_escape_and_compact_overlay(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    ui.resize(960, 720)
    QTest.qWait(20)
    click(app, ui, "operationPicker")
    menu = ui.findChild(QObject, "operationPickerMenu")
    assert menu is not None and menu.property("opened")
    assert item(ui, "operationPickerOption0").isVisible()
    assert item(ui, "operationPickerOption1").property("text") == "Write article"
    position = item(ui, "operationPickerOption1").mapToScene(QPointF(0, 0))
    assert 0 <= position.y() < ui.height() - 20
    QTest.keyClick(ui, Qt.Key.Key_Down)
    QTest.keyClick(ui, Qt.Key.Key_Return)
    app.processEvents()
    assert item(ui, "operationPicker").property("currentIndex") == 1
    assert not menu.property("opened")
    click(app, ui, "operationPicker")
    QTest.keyClick(ui, Qt.Key.Key_Up)
    QTest.keyClick(ui, Qt.Key.Key_Escape)
    app.processEvents()
    assert item(ui, "operationPicker").property("currentIndex") == 1
    assert not menu.property("opened")
    item(ui, "promptEditor").forceActiveFocus()
    app.processEvents()
    assert item(ui, "promptEditorSurface").property("focused")


def test_styled_nested_provider_menu_readonly_field_and_error_state(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    click(app, ui, "providerButton")
    click(app, ui, "providerPicker")
    menu = ui.findChild(QObject, "providerPickerMenu")
    assert menu is not None and menu.property("opened")
    click(app, ui, "providerPickerOption1")
    assert item(ui, "providerPicker").property("currentIndex") == 1
    endpoint = item(ui, "endpointField")
    endpoint.setProperty("text", "http://example.com:11434")
    click(app, ui, "saveProviderButton")
    assert bridge.providerError and item(ui, "endpointFieldSurface").property("invalid")
    click(app, ui, "providerPicker")
    click(app, ui, "providerPickerOption2")
    assert endpoint.property("readOnly")
    assert item(ui, "endpointFieldSurface").property("readOnly")
    endpoint.forceActiveFocus()
    QTest.keyClick(ui, Qt.Key.Key_X)
    assert endpoint.property("text") == "https://api.openai.com/v1"
    assert bridge.service.store.messages(bridge.currentSessionId) == []


def test_styled_fields_keep_password_masking_plain_text_and_disabled_focus(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    click(app, ui, "galleryTab")
    field = item(ui, "galleryPassphrase")
    field.setProperty("text", "synthetic-visible-only-as-dots")
    assert field.property("displayText") != field.property("text")
    field.forceActiveFocus()
    app.processEvents()
    assert item(ui, "galleryPassphraseSurface").property("focused")
    click(app, ui, "voiceTab")
    transcript = item(ui, "voiceTranscript")
    transcript.setProperty("text", "<b>Synthetic plain text</b>")
    expression = QQmlExpression(
        QQmlEngine.contextForObject(transcript), transcript, "getText(0, length)"
    )
    assert expression.evaluate()[0] == "<b>Synthetic plain text</b>"
    transcript.setProperty("enabled", False)
    app.processEvents()
    assert not item(ui, "voiceTranscriptSurface").property("available")


def test_styled_gallery_popup_fits_right_edge_and_compact_viewport(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    vision = bridge.findChild(VisionBridge)
    assert vision is not None
    vision.unlock("synthetic-disposable-style-test", True)
    deadline = time.monotonic() + 3
    while vision.busy and time.monotonic() < deadline:
        QTest.qWait(5)
    assert vision.unlocked
    click(app, ui, "galleryTab")
    for width, height in ((1380, 900), (960, 720)):
        ui.resize(width, height)
        click(app, ui, "gallerySource")
        option = item(ui, "gallerySourceOption1")
        position = option.mapToScene(QPointF(0, 0))
        assert position.x() >= 0 and position.x() + option.width() <= width - 5
        assert position.y() >= 0 and position.y() + option.height() <= height - 5
        QTest.keyClick(ui, Qt.Key.Key_Escape)
        QTest.qWait(10)
    vision.lock()


def test_multiline_editor_contract_has_no_spurious_scroll_and_keeps_long_text_reachable(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    prompt = item(ui, "promptEditor")
    scroll = item(ui, "promptScroll")
    prompt.setProperty("text", "Short fictional question.")
    QTest.qWait(30)
    assert float(scroll.property("contentHeight")) <= float(scroll.property("availableHeight"))
    source = item(ui, "sourceEditor")
    source_scroll = item(ui, "sourceScroll")
    source_position = source_scroll.mapToScene(QPointF(0, 0))
    assert source_position.x() > item(ui, "sourceInspector").mapToScene(QPointF(0, 0)).x()
    prompt.setProperty("text", "\n".join(f"Fictional test line {i}" for i in range(80)))
    prompt.forceActiveFocus()
    QTest.keyClick(ui, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(30)
    assert float(scroll.property("contentHeight")) > float(scroll.property("availableHeight"))
    assert "Fictional test line 79" in str(prompt.property("text"))
    source.setProperty("text", "\n".join(f"Synthetic source line {i}" for i in range(100)))
    QTest.qWait(30)
    assert float(source_scroll.property("contentHeight")) > source_scroll.height()


@pytest.mark.parametrize("size", [(1380, 844), (960, 720)])
def test_composer_grows_for_four_lines_without_losing_send_or_status(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow, size: tuple[int, int]
) -> None:
    ui.resize(*size)
    prompt = item(ui, "promptEditor")
    scroll = item(ui, "promptScroll")
    prompt.setProperty("text", "")
    QTest.qWait(30)
    initial_height = item(ui, "composer").height()
    assert not item(ui, "sendButton").isEnabled()
    prompt.setProperty("text", "First fictional line.\nSecond line.\nThird line.\nFourth line.")
    prompt.forceActiveFocus()
    QTest.qWait(30)
    assert item(ui, "composer").height() > initial_height
    assert float(scroll.property("contentHeight")) <= float(scroll.property("availableHeight"))
    assert item(ui, "composerSurface").property("focused")
    button = item(ui, "sendButton")
    assert button.isEnabled()
    assert button.property("text") == "Send"
    position = button.mapToItem(item(ui, "composer"), QPointF(0, 0))
    assert position.x() >= 0 and position.y() >= 0
    assert position.x() + button.width() < item(ui, "composer").width()
    assert position.y() + button.height() < item(ui, "composer").height()
    assert bridge.service.store.messages(bridge.currentSessionId) == []


def test_voice_scroll_panes_contain_focus_and_preserve_long_text(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    click(app, ui, "voiceTab")
    transcript = item(ui, "voiceTranscript")
    scroll = item(ui, "voiceTranscriptScroll")
    transcript.setProperty("text", "Short fictional transcript.")
    transcript.forceActiveFocus()
    QTest.qWait(30)
    assert float(scroll.property("contentHeight")) <= float(scroll.property("availableHeight"))
    focus = item(ui, "voiceTranscriptSurfaceContainedFocus")
    assert focus.isVisible()
    assert focus.x() >= 0 and focus.y() >= 0
    assert focus.width() <= transcript.width() and focus.height() <= transcript.height()
    transcript.setProperty("text", "\n".join(f"Synthetic transcript line {i}" for i in range(80)))
    bridge.updateResult("\n".join(f"Synthetic draft line {i}" for i in range(100)))
    QTest.qWait(30)
    assert float(scroll.property("contentHeight")) > float(scroll.property("availableHeight"))
    reply_scroll = item(ui, "voiceReplyScroll")
    assert float(reply_scroll.property("contentHeight")) > float(
        reply_scroll.property("availableHeight")
    )
    assert "Synthetic draft line 99" in str(item(ui, "voiceReply").property("text"))


def test_custom_vertical_scrollbars_track_the_viewport_right_edge(
    app: QGuiApplication, bridge: WorkspaceBridge, ui: QQuickWindow
) -> None:
    click(app, ui, "cameraTab")
    ui.resize(960, 720)
    QTest.qWait(30)
    panel = item(ui, "cameraPanel")
    bars = [
        child
        for child in panel.findChildren(QQuickItem)
        if child.metaObject().className().startswith("MiwlScrollBar")
    ]
    assert len(bars) == 1
    bar = bars[0]
    assert bar.height() >= panel.height() - 4
    position = bar.mapToScene(QPointF(0, 0))
    panel_position = panel.mapToScene(QPointF(0, 0))
    assert position.x() >= panel_position.x() + panel.width() - 16
