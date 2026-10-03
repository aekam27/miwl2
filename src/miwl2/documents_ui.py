from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from miwl2.bridge import WorkspaceBridge
from miwl2.documents import (
    DocumentError,
    DocumentIndex,
    EvidenceChunk,
    check_query,
    quoted_request,
    validate_quotations,
)
from miwl2.domain import Provider, ProviderRequest
from miwl2.ollama import OllamaProvider


class QuotationProvider(OllamaProvider):
    def payload(self, request: ProviderRequest) -> dict[str, object]:
        payload = super().payload(request)
        payload["format"] = {
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "citation": {"type": "integer"},
                            "quote": {"type": "string"},
                        },
                        "required": ["citation", "quote"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["claims"],
            "additionalProperties": False,
        }
        return payload


class DocumentsBridge(QObject):
    changed = Signal()
    documentsChanged = Signal()
    resultsChanged = Signal()
    citationChanged = Signal()
    _completed = Signal(object)

    def __init__(self, index: DocumentIndex, workspace: WorkspaceBridge) -> None:
        super().__init__()
        self.index, self.workspace = index, workspace
        self._documents = index.list_documents()
        self._selected: set[str] = set()
        self._chunks: list[EvidenceChunk] = []
        self._results: list[dict[str, Any]] = []
        self._citation: dict[str, Any] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miwl2-documents")
        self._future: Future[dict[str, Any]] | None = None
        self._cancel = Event()
        self._token = 0
        self._closed = False
        self._busy = False
        self._phase = "idle"
        self._error = ""
        self._question = ""
        self._status = "Import selected text or Markdown files, then choose sources for search."
        self._model_provider: Provider | None = None
        self._completed.connect(self._finish)
        workspace.documents_busy = lambda: self._busy
        workspace.contextChanged.connect(self._workspace_changed)

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=changed)
    def phase(self) -> str:
        return self._phase

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status

    @Property(str, notify=changed)
    def question(self) -> str:
        return self._question

    @Property(bool, notify=changed)
    def canUseModel(self) -> bool:
        return self.workspace.service.provider.info.processing_location == "local"

    @Property(list, notify=documentsChanged)
    def documents(self) -> list[dict[str, Any]]:
        return [{**row, "selected": row["id"] in self._selected} for row in self._documents]

    @Property(list, notify=resultsChanged)
    def results(self) -> list[dict[str, Any]]:
        return self._results

    @Property(dict, notify=citationChanged)
    def citation(self) -> dict[str, Any]:
        return self._citation

    def _clear_evidence(self) -> None:
        self._chunks = []
        self._results = []
        self._citation = {}
        self.resultsChanged.emit()
        self.citationChanged.emit()

    def _ready(self) -> bool:
        if self._closed or self._busy or self.workspace.busy or self.workspace.voice_busy():
            self._error = "Finish or stop the active writing, voice or document task first."
            self.changed.emit()
            return False
        self._error = ""
        return True

    def _submit(self, kind: str, work: Callable[[Event], Any]) -> None:
        self._token += 1
        token = self._token
        cancel = Event()
        self._cancel = cancel
        self._busy = True
        self._phase = kind
        self._error = ""
        self.changed.emit()
        self.workspace.contextChanged.emit()

        def run() -> dict[str, Any]:
            try:
                return {"kind": kind, "token": token, "value": work(cancel)}
            except DocumentError as error:
                return {"kind": kind, "token": token, "error": str(error)}
            except Exception:
                return {
                    "kind": kind,
                    "token": token,
                    "error": (
                        "The local document task could not complete. "
                        "Check the selected file, index or local provider."
                    ),
                }

        self._future = self._executor.submit(run)
        self._future.add_done_callback(
            lambda future: self._completed.emit(future.result()) if not future.cancelled() else None
        )

    @Slot(QUrl)
    def importFile(self, url: QUrl) -> None:
        if not self._ready():
            return
        if not url.isLocalFile() or url.host() not in {"", "localhost"}:
            self._error = "Select a local text or Markdown file. Remote URLs are not fetched."
            self.changed.emit()
            return
        from pathlib import Path

        path = Path(url.toLocalFile())
        self._clear_evidence()
        self._status = "Importing the selected file locally…"
        self._submit("importing", lambda cancel: self.index.import_file(path, cancel))

    @Slot(str, bool)
    def selectDocument(self, identifier: str, selected: bool) -> None:
        if identifier not in {row["id"] for row in self._documents}:
            return
        if self._busy:
            self.stop()
        if selected:
            self._selected.add(identifier)
        else:
            self._selected.discard(identifier)
        self._clear_evidence()
        self._status = "Sources changed. Search again to build a fresh evidence set."
        self.documentsChanged.emit()
        self.changed.emit()

    @Slot(str)
    def deleteDocument(self, identifier: str) -> None:
        if not self._ready():
            return
        if identifier not in {row["id"] for row in self._documents}:
            return
        self._clear_evidence()
        self._status = "Removing the imported copy and search entries…"
        self._submit("deleting", lambda cancel: self.index.delete(identifier))

    @Slot(str)
    def search(self, question: str) -> None:
        if not self._ready():
            return
        self._clear_evidence()
        try:
            question = check_query(question)
            if not self._selected:
                raise DocumentError("Select at least one imported document for this search.")
        except DocumentError as error:
            self._error = str(error)
            self.changed.emit()
            return
        self._question = question
        selected = tuple(sorted(self._selected))
        self._status = "Searching the selected imported copies with local FTS5…"
        self._submit("searching", lambda cancel: self.index.search(question, selected, cancel))

    @Slot()
    def chooseQuotations(self) -> None:
        if not self._ready():
            return
        if not self._chunks:
            self._error = "Search selected sources and find evidence first."
            self.changed.emit()
            return
        original = self.workspace.service.provider
        if original.info.processing_location != "local":
            self._error = (
                "Documents use local retrieval and local AI only. "
                "Choose Local Ollama for quotations."
            )
            self.changed.emit()
            return
        provider: Provider = (
            QuotationProvider(original.endpoint, original.model, original.limits)
            if isinstance(original, OllamaProvider)
            else original
        )
        chunks = tuple(self._chunks)
        try:
            request = quoted_request(self._question, chunks)
        except DocumentError as error:
            self._error = str(error)
            self.changed.emit()
            return
        self._model_provider = original
        self._status = "Choosing exact source quotations locally. Every quotation will be verified…"

        def choose(cancel: Event) -> list[dict[str, Any]]:
            parts = []
            total = 0
            stream: Iterator[str] = provider.stream(request, cancel)
            try:
                for part in stream:
                    if cancel.is_set():
                        raise DocumentError("Local quotation selection stopped.")
                    total += len(part.encode("utf-8"))
                    if total > 12_000:
                        raise DocumentError("Local quotation response exceeded 12 KB.")
                    parts.append(part)
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
            if cancel.is_set():
                raise DocumentError("Local quotation selection stopped.")
            return validate_quotations("".join(parts), chunks)

        self._submit("quoting", choose)

    @Slot(str)
    def openCitation(self, url: str) -> None:
        match = re.fullmatch(r"doc://chunk/([0-9]{1,18})", url)
        if match is None or self._busy:
            return
        identifier = int(match[1])
        row = next(
            (
                result
                for result in self._results
                if result["id"] == identifier and result["documentId"] in self._selected
            ),
            None,
        )
        if row is None:
            self._error = "This citation is no longer part of the selected evidence."
            self.changed.emit()
            return
        try:
            current = self.index.chunk(identifier)
            if current.source_sha256 != row["sha256"]:
                raise DocumentError(
                    "This imported source changed. Search again for a current citation."
                )
            self._citation = {**current.display(), "quotedText": row["text"]}
            self.citationChanged.emit()
        except DocumentError as error:
            self._error = str(error)
            self.changed.emit()

    @Slot()
    def stop(self) -> None:
        self._token += 1
        self._cancel.set()
        self._model_provider = None
        self._clear_evidence()
        self._status = "Document task stopped. Late output will be discarded."
        self.changed.emit()

    @Slot()
    def _workspace_changed(self) -> None:
        if (
            self._model_provider is not None
            and self.workspace.service.provider is not self._model_provider
        ):
            self.stop()
        self.changed.emit()

    @Slot(object)
    def _finish(self, outcome: dict[str, Any]) -> None:
        self._busy = False
        self._phase = "idle"
        self._model_provider = None
        if self._closed:
            return
        if outcome["kind"] in {"importing", "deleting"}:
            self._documents = self.index.list_documents()
            self._selected.intersection_update(row["id"] for row in self._documents)
            self.documentsChanged.emit()
        if outcome["token"] == self._token:
            if "error" in outcome:
                self._error = outcome["error"]
                self._status = "No unverified model answer was added."
            elif outcome["kind"] == "importing":
                self._selected.add(outcome["value"])
                self.documentsChanged.emit()
                self._status = (
                    "Imported locally and selected for search. The original file is unchanged."
                )
            elif outcome["kind"] == "deleting":
                self._status = (
                    "Removed the imported copy and index entries. "
                    "The original file is unchanged; backups are separate."
                )
            elif outcome["kind"] == "searching":
                self._chunks = outcome["value"]
                self._results = [chunk.display() for chunk in self._chunks]
                self.resultsChanged.emit()
                self._status = (
                    f"{len(self._results)} matching passages. "
                    "Click a citation to review its imported source."
                    if self._results
                    else (
                        "I couldn't find matching evidence in the selected documents. "
                        "Try specific terms or another source."
                    )
                )
            elif outcome["kind"] == "quoting":
                self._results = outcome["value"]
                self.resultsChanged.emit()
                self._status = (
                    "Verified source quotations selected by the local model. "
                    "Review relevance before using them."
                    if self._results
                    else "The local model found no supported quotation. No answer was generated."
                )
        self.changed.emit()
        self.workspace.contextChanged.emit()

    def shutdown(self) -> None:
        self._closed = True
        self.stop()
        self._executor.shutdown(wait=True, cancel_futures=True)
