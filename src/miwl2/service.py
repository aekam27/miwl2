from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event, RLock

from miwl2.configuration import ProviderConfiguration
from miwl2.domain import JobState, Operation, Provider, ProviderRequest, Turn
from miwl2.storage import Store


@dataclass
class ActiveJob:
    id: str
    session_id: str
    message_id: str
    request: ProviderRequest
    cancel: Event
    body: str = ""
    state: JobState = JobState.QUEUED


class WorkspaceService:
    """One provider job at a time, isolated session snapshots and late-data gates."""

    def __init__(self, store: Store, provider: Provider) -> None:
        self.store, self.provider = store, provider
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miwl2-provider")
        self._lock = RLock()
        self._active: ActiveJob | None = None
        self.on_change: Callable[[], None] = lambda: None

    @property
    def active(self) -> ActiveJob | None:
        with self._lock:
            return self._active

    def update_source(self, session_id: str, source: str) -> None:
        with self._lock:
            if self.store.session(session_id)["source"] != source:
                self.cancel(session_id)
                self.store.update_source(session_id, source)

    def update_result(self, session_id: str, result: str) -> None:
        with self._lock:
            if self.store.session(session_id)["result"] != result:
                self.cancel(session_id)
                self.store.update_result(session_id, result)

    def configure_provider(self, configuration: ProviderConfiguration) -> None:
        with self._lock:
            if self._active is not None:
                raise ValueError("Stop the current response before changing providers.")
            configuration = configuration.validated()
            provider = configuration.build()
            self.store.save_provider_configuration(configuration)
            self.provider = provider
            self.on_change()

    def start(
        self,
        session_id: str,
        operation: Operation,
        prompt: str = "",
        simulate_error: bool = False,
        *,
        cloud_authorized: bool = False,
    ) -> str:
        with self._lock:
            if self.provider.info.processing_location == "cloud" and not cloud_authorized:
                raise ValueError("Confirm sending this request's text to OpenAI before continuing.")
            if self._active is not None:
                raise ValueError(
                    "Wait for the current response to finish stopping, then try again."
                )
            session = self.store.session(session_id)
            if (
                operation in {Operation.SUMMARIZE, Operation.PARAPHRASE}
                and not str(session["source"]).strip()
            ):
                raise ValueError(f"Paste source text before requesting {operation.value}.")
            if operation in {Operation.CHAT, Operation.ARTICLE} and not prompt.strip():
                raise ValueError(
                    "Write an article topic first."
                    if operation == Operation.ARTICLE
                    else "Write a message before sending it."
                )
            history_turns: list[Turn] = []
            pending_user: Turn | None = None
            for row in self.store.messages(session_id):
                if row["role"] == "user":
                    pending_user = Turn("user", row["body"])
                elif row["status"] == "complete" and (
                    self.provider.info.is_test or not row["provider_is_test"]
                ):
                    if pending_user is not None:
                        history_turns.append(pending_user)
                    history_turns.append(Turn("assistant", row["body"]))
                    pending_user = None
            history = tuple(history_turns[-20:])
            request = ProviderRequest(
                operation,
                session["source"],
                prompt.strip(),
                history,
                session["result"],
                simulate_error,
            )
            job_id, message_id = self.store.create_job(session_id, request, self.provider.info)
            job = ActiveJob(job_id, session_id, message_id, request, Event())
            self._active = job
            self.on_change()
            self._executor.submit(self._run, job)
            return job_id

    def retry(self, session_id: str, *, cloud_authorized: bool = False) -> str:
        previous = self.store.last_job(session_id)
        if previous is None or previous["state"] != JobState.FAILED:
            raise ValueError("There is no failed response to retry in this session.")
        request = json.loads(previous["request"])
        return self.start(
            session_id,
            Operation(request["operation"]),
            request["prompt"],
            cloud_authorized=cloud_authorized,
        )

    def cancel(self, session_id: str | None = None) -> None:
        with self._lock:
            job = self._active
            if job is None or (session_id is not None and job.session_id != session_id):
                return
            job.cancel.set()
            job.state = JobState.CANCELLING
            self.store.set_job_state(job.id, JobState.CANCELLING)
            self.on_change()

    def _state(self, job: ActiveJob, state: JobState) -> None:
        with self._lock:
            if self._active is not job or job.cancel.is_set():
                return
            job.state = state
            self.store.set_job_state(job.id, state)
            self.on_change()

    def _delta(self, job: ActiveJob, delta: str) -> None:
        with self._lock:
            if self._active is not job or job.cancel.is_set():
                return
            job.body += delta
            self.store.set_message(job.message_id, job.body, "pending")
            self.on_change()

    def _run(self, job: ActiveJob) -> None:
        error = ""
        try:
            self._state(job, JobState.LOADING)
            for delta in self.provider.stream(job.request, job.cancel):
                self._state(job, JobState.RUNNING)
                self._delta(job, delta)
        except Exception as exception:
            error = str(exception) or "The provider failed. You can retry this response."
        finally:
            with self._lock:
                if self._active is job:
                    if job.cancel.is_set():
                        self.store.set_job_state(job.id, JobState.CANCELLED)
                        self.store.set_message(job.message_id, job.body, "cancelled")
                    elif error:
                        self.store.set_job_state(job.id, JobState.FAILED, error)
                        self.store.set_message(job.message_id, job.body, "failed")
                    elif not job.body.strip():
                        self.store.set_job_state(
                            job.id,
                            JobState.FAILED,
                            "The provider returned no text. Your source is safe; try again.",
                        )
                        self.store.set_message(job.message_id, "", "failed")
                    else:
                        self.store.complete_job(job.id, job.body)
                    self._active = None
                    self.on_change()

    def shutdown(self) -> None:
        self.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)
