from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass
from enum import StrEnum
from threading import Event
from typing import Protocol, runtime_checkable


class Operation(StrEnum):
    CHAT = "chat"
    SUMMARIZE = "summarize"
    ARTICLE = "article"
    PARAPHRASE = "paraphrase"


class JobState(StrEnum):
    QUEUED = "queued"
    LOADING = "loading"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class ProviderInfo:
    identifier: str
    label: str
    is_test: bool
    processing_location: str


@dataclass(frozen=True)
class Turn:
    role: str
    body: str


@dataclass(frozen=True)
class ProviderRequest:
    operation: Operation
    source: str
    prompt: str
    history: tuple[Turn, ...] = ()
    previous_result: str = ""
    simulate_error: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@runtime_checkable
class Provider(Protocol):
    """Adapters stream text cooperatively; they never own UI or persistence.

    A future process/cloud adapter can implement this same contract. Cancelled
    responses are discarded by the service even if an adapter emits late data.
    """

    @property
    def info(self) -> ProviderInfo: ...

    def stream(self, request: ProviderRequest, cancel: Event) -> Iterator[str]: ...
