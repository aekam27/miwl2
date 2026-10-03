"""Opt-in selected synthetic documents and actual installed Gemma quotation checks."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
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
from miwl2.ollama import OllamaProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store
from miwl2.vision import VisionPaths, VisionRuntime
from miwl2.vision_ui import VisionBridge
from miwl2.voice import VoiceEngine, VoicePaths, VoiceRuntime
from miwl2.voice_ui import VoiceBridge

SOURCE = (
    "# Cedar Library pilot — fictional evaluation\n"
    "This synthetic six-week pilot included 40 participants.\n"
    "21 of 28 survey respondents reported saving time; 7 did not.\n"
    "The survey was self-selected and had no randomized comparison group.\n"
    "These reports do not establish a causal improvement.\n"
)


def run() -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests"))
    from test_qt import click, item, settle_documents

    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with tempfile.TemporaryDirectory(prefix="miwl2-documents-ui-") as directory:
        data = Path(directory)
        source = data / "Cedar-pilot-synthetic.md"
        source.write_text(SOURCE)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        service = WorkspaceService(
            Store(data / "workspace.sqlite3"), OllamaProvider("http://127.0.0.1:11434", "gemma3:4b")
        )
        bridge = WorkspaceBridge(service)
        bridge.updateSource("PRIVATE_SYNTHETIC_WRITING_SENTINEL")
        bridge.renameSession("Cedar Library · document check")
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
            QTest.qWait(150)
            path = root / "evidence" / name
            assert window.grabWindow().save(str(path))
            previews.append(str(path.relative_to(root)))

        try:
            documents.importFile(QUrl.fromLocalFile(str(source)))
            settle_documents(app, documents)
            identifier = documents.documents[0]["id"]
            click(app, window, "documentsTab")
            item(window, "documentsQuestion").setProperty(
                "text", "How many respondents reported saving time?"
            )
            click(app, window, "documentsSearch")
            settle_documents(app, documents)
            assert documents.results and not documents.error
            search_results = documents.results.copy()
            capture("Miwl-2-documents-search-preview.png")
            started = time.monotonic()
            click(app, window, "documentsQuote")
            while documents.busy and time.monotonic() - started < 60:
                QTest.qWait(10)
            assert not documents.busy and not documents.error, documents.error
            assert documents.results, documents.statusText
            quotes = documents.results.copy()
            assert all(row["text"] == SOURCE[row["start"] : row["end"]] for row in quotes)
            assert "21 of 28" in " ".join(row["text"] for row in quotes)
            elapsed = time.monotonic() - started
            capture("Miwl-2-documents-quotations-preview.png")
            click(app, window, "documentCitation" + str(quotes[0]["id"]))
            assert item(window, "documentCitationText").property("text") == SOURCE
            capture("Miwl-2-documents-citation-preview.png")
            reader = window.findChild(QObject, "documentCitationDialog")
            assert reader is not None
            QMetaObject.invokeMethod(reader, "close")
            window.resize(960, 720)
            capture("Miwl-2-documents-compact-preview.png")
            item(window, "documentsQuestion").setProperty("text", "Zephyr launch budget")
            click(app, window, "documentsSearch")
            settle_documents(app, documents)
            assert not documents.results and "couldn't find" in documents.statusText
            assert not item(window, "documentsQuote").isEnabled()
            capture("Miwl-2-documents-abstention-preview.png")
            assert service.store.messages(bridge.currentSessionId) == []
            documents.deleteDocument(identifier)
            settle_documents(app, documents)
            assert not documents.documents and not documents.index.search("respondents")
            assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
            assert not warnings, warnings
            report = {
                "platform": app.platformName(),
                "data": "one fictional temporary document",
                "provider": service.provider.info.label,
                "model_seconds": elapsed,
                "search_results": search_results,
                "verified_quotations": quotes,
                "citation_opened": True,
                "unsupported_query_abstained": True,
                "original_unchanged": True,
                "active_index_deleted": True,
                "writing_session_unchanged": True,
                "qml_warnings": warnings,
                "previews": previews,
                "embedding_model": "not installed; terms pending",
                "limitations": (
                    "Keyword retrieval; exact quotations do not prove relevance or completeness."
                ),
            }
            (root / "evidence/documents-ui-verification.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            )
            print(
                json.dumps({"model_seconds": elapsed, "quotes": quotes, "previews": previews}),
                flush=True,
            )
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
