from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from miwl2.configuration import ProviderConfiguration
from miwl2.domain import JobState, Operation
from miwl2.providers import TEST_LABEL
from miwl2.service import WorkspaceService

SAMPLE_SOURCE = (
    "Miwl 2 keeps source text, conversations, and editable outputs in a local workspace. "
    "You can select local Ollama for AI writing, or a labelled fixture for interface testing. "
    "Summary and paraphrase use source notes; article writing uses a topic and optional notes. "
    "You can refine a draft, stop a response, and reopen a saved session. "
    "Local voice transcripts can be reviewed before sending; "
    "camera recognition belongs to a later stage."
)


class WorkspaceBridge(QObject):
    contextChanged = Signal()
    sourceTextChanged = Signal()
    resultTextChanged = Signal()
    messagesChanged = Signal()
    sessionsChanged = Signal()
    currentSessionChanged = Signal()
    _changed = Signal()

    def __init__(self, service: WorkspaceService) -> None:
        super().__init__()
        self.service = service
        sessions = service.store.list_sessions()
        self._current_id = sessions[0]["id"] if sessions else service.store.create_session()
        self._session: dict[str, Any] = {}
        self._messages: list[dict[str, Any]] = []
        self._sessions: list[dict[str, Any]] = []
        self._last_job: dict[str, Any] | None = None
        self._validation_error = ""
        self._dismissed_job = ""
        self._notice = ""
        self._simulate_failure = False
        self._provider_error = ""
        self.voice_busy: Callable[[], bool] = lambda: False
        self.documents_busy: Callable[[], bool] = lambda: False
        self._cloud_authorized = False
        self._changed.connect(self.refresh)
        service.on_change = self._changed.emit
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        session = self.service.store.session(self._current_id)
        source_changed = session.get("source") != self._session.get("source")
        result_changed = session.get("result") != self._session.get("result")
        self._session = session
        messages = self.service.store.messages(self._current_id)
        sessions = self.service.store.list_sessions()
        today = datetime.now().astimezone().date()
        for item in sessions:
            updated = datetime.fromisoformat(item["updated_at"]).astimezone()
            item["updatedLabel"] = updated.strftime("%b %d · %H:%M")
            item["historyGroup"] = (
                "Today"
                if updated.date() == today
                else "Yesterday"
                if updated.date() == today - timedelta(days=1)
                else updated.strftime("%b %d, %Y")
            )
        if messages != self._messages:
            self._messages = messages
            self.messagesChanged.emit()
        if sessions != self._sessions:
            self._sessions = sessions
            self.sessionsChanged.emit()
        self._last_job = self.service.store.last_job(self._current_id)
        if source_changed:
            self.sourceTextChanged.emit()
        if result_changed:
            self.resultTextChanged.emit()
        self.contextChanged.emit()

    @Property(list, notify=sessionsChanged)
    def sessions(self) -> list[dict[str, Any]]:
        return self._sessions

    @Property(list, notify=messagesChanged)
    def messages(self) -> list[dict[str, Any]]:
        return self._messages

    @Property(str, notify=currentSessionChanged)
    def currentSessionId(self) -> str:
        return self._current_id

    @Property(str, notify=contextChanged)
    def sessionTitle(self) -> str:
        return str(self._session.get("title", "Untitled session"))

    @Property(str, notify=sourceTextChanged)
    def sourceText(self) -> str:
        return str(self._session.get("source", ""))

    @Property(str, notify=resultTextChanged)
    def resultText(self) -> str:
        return str(self._session.get("result", ""))

    @Property(int, notify=sourceTextChanged)
    def sourceWordCount(self) -> int:
        return len(str(self._session.get("source", "")).split())

    @Property(bool, notify=contextChanged)
    def busy(self) -> bool:
        return self.service.active is not None

    @Property(str, notify=contextChanged)
    def jobState(self) -> str:
        job = self.service.active
        return job.state.value if job is not None else "idle"

    @Property(str, notify=contextChanged)
    def statusText(self) -> str:
        job = self.service.active
        if job is None:
            return (
                "Ready · fixture, no AI"
                if self.providerIsTest
                else f"Ready · {self.service.provider.info.label}"
            )
        if job.session_id != self._current_id:
            return "Stopping the previous session's response…"
        return {
            JobState.QUEUED: "Response queued…",
            JobState.LOADING: "Preparing a fixture response…"
            if self.providerIsTest
            else "Waiting for OpenAI cloud…"
            if self.service.provider.info.processing_location == "cloud"
            else "Waiting for local Ollama…",
            JobState.RUNNING: "Writing the fixture response…"
            if self.providerIsTest
            else "Writing with OpenAI cloud…"
            if self.service.provider.info.processing_location == "cloud"
            else "Writing with local Ollama…",
            JobState.CANCELLING: "Stopping the response…",
        }.get(job.state, "Ready")

    @Property(str, notify=contextChanged)
    def errorMessage(self) -> str:
        if self._validation_error:
            return self._validation_error
        if (
            self._last_job is not None
            and self._last_job["state"] == JobState.FAILED
            and self._last_job["id"] != self._dismissed_job
        ):
            return str(self._last_job["error"])
        return ""

    @Property(bool, notify=contextChanged)
    def retryAvailable(self) -> bool:
        return (
            not self.busy
            and self._last_job is not None
            and self._last_job["state"] == JobState.FAILED
        )

    @Property(str, notify=contextChanged)
    def savedLabel(self) -> str:
        date = self._session.get("updated_at")
        if not date:
            return "Saved on this Mac"
        time = datetime.fromisoformat(date).astimezone().strftime("%H:%M")
        return f"Saved locally · {time}"

    @Property(str, notify=contextChanged)
    def noticeMessage(self) -> str:
        return self._notice

    @Property(bool, notify=contextChanged)
    def simulateFailure(self) -> bool:
        return self._simulate_failure

    @Property(bool, notify=contextChanged)
    def providerIsTest(self) -> bool:
        return self.service.provider.info.is_test

    @Property(str, notify=contextChanged)
    def providerLabel(self) -> str:
        return "Test mode · No AI" if self.providerIsTest else self.service.provider.info.label

    @Property(str, notify=contextChanged)
    def providerKind(self) -> str:
        return self.service.store.provider_configuration().provider

    @Property(str, notify=contextChanged)
    def providerEndpoint(self) -> str:
        return self.service.store.provider_configuration().endpoint

    @Property(str, notify=contextChanged)
    def providerModel(self) -> str:
        return self.service.store.provider_configuration().model

    @Property(str, notify=contextChanged)
    def providerError(self) -> str:
        return self._provider_error

    @Property(str, notify=contextChanged)
    def usageText(self) -> str:
        usage = getattr(self.service.provider, "last_usage", {})
        if not usage:
            return "Token usage unavailable · no cost estimate configured"
        return (
            f"Provider usage: {usage.get('prompt_tokens', '?')} input / "
            f"{usage.get('completion_tokens', '?')} output tokens · no cost estimate"
        )

    @Slot()
    def authorizeCloudRequest(self) -> None:
        self._cloud_authorized = True

    @Slot(str, str, str, result=bool)
    def configureProvider(self, kind: str, endpoint: str, model: str) -> bool:
        try:
            self.service.configure_provider(ProviderConfiguration(kind, endpoint, model))
        except ValueError as exception:
            self._provider_error = str(exception)
            self.contextChanged.emit()
            return False
        self._provider_error = ""
        self._cloud_authorized = False
        self._validation_error = ""
        self._simulate_failure = False
        self._notice = "Provider saved. The model runs when you send a request."
        self.refresh()
        QTimer.singleShot(3500, self._clear_notice)
        return True

    @Slot(bool)
    def setSimulateFailure(self, enabled: bool) -> None:
        self._simulate_failure = enabled
        self.contextChanged.emit()

    @Slot(str)
    def updateSource(self, source: str) -> None:
        self.service.update_source(self._current_id, source)
        self.refresh()

    @Slot(str)
    def updateResult(self, result: str) -> None:
        self.service.update_result(self._current_id, result)
        self.refresh()

    @Slot()
    def loadSample(self) -> None:
        self.updateSource(SAMPLE_SOURCE)

    @Slot()
    def newSession(self) -> None:
        self.service.cancel(self._current_id)
        self._current_id = self.service.store.create_session()
        self._switch()

    @Slot(str)
    def selectSession(self, session_id: str) -> None:
        if session_id == self._current_id:
            return
        self.service.store.session(session_id)
        self.service.cancel(self._current_id)
        self._current_id = session_id
        self._switch()

    def _switch(self) -> None:
        self._cloud_authorized = False
        self._validation_error = ""
        self._dismissed_job = ""
        self.refresh()
        self.sourceTextChanged.emit()
        self.resultTextChanged.emit()
        self.currentSessionChanged.emit()

    @Slot(str)
    def renameSession(self, title: str) -> None:
        try:
            self.service.store.rename(self._current_id, title)
            self.refresh()
        except ValueError as exception:
            self._validation_error = str(exception)
            self.contextChanged.emit()

    @Property(bool, notify=contextChanged)
    def documentsBusy(self) -> bool:
        return self.documents_busy()

    def _start(self, operation: Operation, prompt: str = "") -> None:
        self._validation_error = ""
        consent, self._cloud_authorized = self._cloud_authorized, False
        try:
            if self.documents_busy():
                raise ValueError("Finish or stop the document task before sending a response.")
            if self.voice_busy():
                raise ValueError("Finish or stop the voice task before sending a response.")
            self.service.start(
                self._current_id,
                operation,
                prompt,
                self._simulate_failure,
                cloud_authorized=consent,
            )
            self._simulate_failure = False
        except ValueError as exception:
            self._validation_error = str(exception)
        self.refresh()

    @Slot()
    def summarize(self) -> None:
        self._start(Operation.SUMMARIZE)

    @Slot()
    def paraphrase(self) -> None:
        self._start(Operation.PARAPHRASE)

    @Slot(str)
    def writeArticle(self, topic: str) -> None:
        self._start(Operation.ARTICLE, topic)

    @Slot(str)
    def sendMessage(self, prompt: str) -> None:
        self._start(Operation.CHAT, prompt)

    @Slot()
    def stop(self) -> None:
        self.service.cancel()
        self.refresh()

    @Slot()
    def retry(self) -> None:
        self._validation_error = ""
        consent, self._cloud_authorized = self._cloud_authorized, False
        try:
            if self.documents_busy():
                raise ValueError("Finish or stop the document task before sending a response.")
            if self.voice_busy():
                raise ValueError("Finish or stop the voice task before retrying.")
            self.service.retry(self._current_id, cloud_authorized=consent)
        except ValueError as exception:
            self._validation_error = str(exception)
        self.refresh()

    @Slot()
    def dismissError(self) -> None:
        self._validation_error = ""
        self._dismissed_job = self._last_job["id"] if self._last_job is not None else ""
        self.contextChanged.emit()

    @Slot()
    def copyResult(self) -> None:
        result = str(self._session.get("result", "")).strip()
        if not result:
            return
        # Attribution belongs to the saved draft's producing job, not the
        # currently selected provider (which may have changed since generation).
        producing_job = self.service.store.last_completed_job(self._current_id)
        is_test = producing_job is None or bool(producing_job["provider_is_test"])
        if is_test and not result.startswith(TEST_LABEL):
            result = f"{TEST_LABEL}\n\n{result}"
        QGuiApplication.clipboard().setText(result)
        self._notice = "Copied with the test-provider label" if is_test else "Draft copied"
        self.contextChanged.emit()
        QTimer.singleShot(3500, self._clear_notice)

    @Slot()
    def _clear_notice(self) -> None:
        self._notice = ""
        self.contextChanged.emit()
