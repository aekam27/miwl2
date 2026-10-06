from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event, RLock
from typing import cast

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
    last_persisted: float = 0


class WorkspaceService:
    """One provider job at a time, isolated session snapshots and late-data gates."""

    def __init__(self, store: Store, provider: Provider) -> None:
        self.store, self.provider = store, provider
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miwl2-provider")
        self._lock = RLock()
        self._active: ActiveJob | None = None
        self._closed = False
        self.persistence_error = ""
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
            if self._closed:
                raise ValueError("This workspace is closing. Reopen Miwl to send a response.")
            if self.persistence_error:
                raise ValueError(self.persistence_error)
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
                omitted_history_turns=len(history_turns) - len(history),
            )
            prepare = getattr(self.provider, "prepare_request", None)
            if callable(prepare):
                request = cast(Callable[[ProviderRequest], ProviderRequest], prepare)(request)
            job_id, message_id = self.store.create_job(session_id, request, self.provider.info)
            job = ActiveJob(job_id, session_id, message_id, request, Event())
            self._active = job
            self.on_change()
            try:
                self._executor.submit(self._run, job)
            except RuntimeError:
                # An executor can enqueue work before failing to start its worker.
                # Retire that job even if a later submission drains the old queue item.
                job.cancel.set()
                job.state = JobState.FAILED
                try:
                    self.store.finish_job(
                        job.id,
                        JobState.FAILED,
                        "",
                        "The response worker could not start. Retry this response "
                        "when the computer has available resources.",
                    )
                except sqlite3.Error as exception:
                    self.persistence_error = (
                        f"The response failure could not be saved: {exception}. "
                        "Your prior draft is retained. Check storage space/permissions, "
                        "then reopen this workspace before sending again."
                    )
                finally:
                    self._active = None
                self.on_change()
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
            try:
                self.store.set_job_state(job.id, JobState.CANCELLING)
            except sqlite3.Error as exception:
                self.persistence_error = (
                    f"Stop was requested, but its status could not be saved: {exception}. "
                    "Check storage space/permissions, then reopen the workspace."
                )
            self.on_change()

    def _state(self, job: ActiveJob, state: JobState) -> None:
        with self._lock:
            if self._active is not job or job.cancel.is_set() or job.state == state:
                return
            job.state = state
            self.store.set_job_state(job.id, state)
            self.on_change()

    def _delta(self, job: ActiveJob, delta: str) -> None:
        with self._lock:
            if self._active is not job or job.cancel.is_set():
                return
            if len(job.body) + len(delta) > 64 * 1024:
                raise ValueError("The response exceeded the text limit. Your saved draft is safe.")
            job.body += delta
            now = time.monotonic()
            if now - job.last_persisted >= 0.05:
                self.store.set_message(job.message_id, job.body, "pending")
                job.last_persisted = now
                self.on_change()

    def _run(self, job: ActiveJob) -> None:
        with self._lock:
            if self._active is not job:
                return
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
                    try:
                        if job.cancel.is_set():
                            self.store.finish_job(job.id, JobState.CANCELLED, job.body)
                        elif error:
                            self.store.finish_job(job.id, JobState.FAILED, job.body, error)
                        elif not job.body.strip():
                            self.store.finish_job(
                                job.id,
                                JobState.FAILED,
                                "",
                                "The provider returned no text. Your source is safe; try again.",
                            )
                        else:
                            self.store.complete_job(job.id, job.body)
                    except sqlite3.Error as exception:
                        self.persistence_error = (
                            f"The response could not be saved: {exception}. "
                            "Your prior draft is retained. Check storage space/permissions, "
                            "then reopen this workspace before sending again."
                        )
                    finally:
                        self._active = None
                    self.on_change()

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            self.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)
