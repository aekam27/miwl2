"""Opt-in real local inference, using synthetic notes and an isolated workspace.

Run only after the chosen runtime/model have been approved and installed.
This script never downloads models, starts servers, or accesses cameras/microphones.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import urllib.request
from pathlib import Path
from threading import Event

from miwl2.domain import JobState, Operation, ProviderRequest
from miwl2.ollama import OllamaProvider
from miwl2.service import WorkspaceService
from miwl2.storage import Store

SOURCE = (
    "The fictional Cedar Library ran a six-week pilot beginning on 1 May 2026. "
    "Forty adult volunteers used a local writing assistant twice a week. "
    "The assistant summarised notes and rewrote draft emails on the library's computers. "
    "Text stayed on those computers, and participants could delete their sessions. "
    "The pilot cost £600 for staff training; the report does not state hardware costs. "
    "Twenty-eight participants completed the final survey; twelve did not respond. "
    "Of the twenty-eight respondents, twenty-one reported saving time. "
    "These self-reported results do not establish how much time was saved or whether "
    "the assistant improved writing accuracy. The library has not decided to expand the pilot."
)
CASES = [
    (
        Operation.CHAT,
        "How many survey respondents reported saving time, and what can we not conclude?",
    ),
    (Operation.SUMMARIZE, ""),
    (
        Operation.ARTICLE,
        "Write a 150-word report about this fictional pilot for library staff. "
        "Include limitations.",
    ),
    (Operation.PARAPHRASE, ""),
]


def api(path: str) -> dict[str, object]:
    with urllib.request.urlopen(f"http://127.0.0.1:11434{path}", timeout=3) as response:
        result: dict[str, object] = json.load(response)
        return result


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evidence/local-inference.json"))
    args = parser.parse_args()
    provider = OllamaProvider("http://127.0.0.1:11434", "gemma3:4b")
    before = api("/api/ps")
    results: list[dict[str, object]] = []
    for index, (operation, prompt) in enumerate(CASES):
        started, first = time.monotonic(), None
        pieces: list[str] = []
        for delta in provider.stream(ProviderRequest(operation, SOURCE, prompt), Event()):
            if first is None:
                first = time.monotonic() - started
            pieces.append(delta)
        result = {
            "operation": operation.value,
            "load_state": "cold (no model resident before run)"
            if index == 0 and not before.get("models")
            else "warm",
            "first_text_seconds": first,
            "elapsed_seconds": time.monotonic() - started,
            "output": "".join(pieces),
            "metrics": dict(provider.last_metrics),
        }
        results.append(result)
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in ("operation", "load_state", "first_text_seconds", "elapsed_seconds")
                }
            ),
            flush=True,
        )
    # Repeat the same chat request warm to make cold/warm comparison meaningful.
    started, first = time.monotonic(), None
    pieces = []
    for delta in provider.stream(ProviderRequest(Operation.CHAT, SOURCE, CASES[0][1]), Event()):
        if first is None:
            first = time.monotonic() - started
        pieces.append(delta)
    results.append(
        {
            "operation": "chat-repeat",
            "load_state": "warm",
            "first_text_seconds": first,
            "elapsed_seconds": time.monotonic() - started,
            "output": "".join(pieces),
            "metrics": dict(provider.last_metrics),
        }
    )
    # Exercise the actual service: cooperative Stop preserves a saved edited draft.
    temporary = tempfile.TemporaryDirectory(prefix="miwl2-local-benchmark-")
    store = Store(Path(temporary.name) / "workspace.sqlite3")
    service = WorkspaceService(store, provider)
    try:
        session = store.create_session()
        service.update_source(session, SOURCE)
        service.update_result(session, "A manually saved draft that must survive Stop.")
        job = service.start(
            session, Operation.ARTICLE, "Write a detailed 1000-word article about the pilot."
        )
        deadline = time.monotonic() + 30
        while (
            service.active is not None and not service.active.body and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        partial_observed = bool(service.active and service.active.body)
        started = time.monotonic()
        service.cancel()
        while service.active is not None and time.monotonic() - started < 3:
            time.sleep(0.005)
        cancellation = {
            "elapsed_seconds": time.monotonic() - started,
            "partial_observed": partial_observed,
            "state": store.job(job)["state"],
            "saved_draft_preserved": store.session(session)["result"]
            == "A manually saved draft that must survive Stop.",
        }
        assert cancellation["state"] == JobState.CANCELLED and cancellation["saved_draft_preserved"]
    finally:
        service.shutdown()
        temporary.cleanup()
    missing_error = ""
    try:
        list(
            OllamaProvider(provider.endpoint, "miwl-does-not-exist:fixture").stream(
                ProviderRequest(Operation.CHAT, "", "hello"),
                Event(),
            )
        )
    except RuntimeError as exception:
        missing_error = str(exception)
    report = {
        "synthetic_source": SOURCE,
        "runtime": api("/api/version"),
        "model_inventory": api("/api/tags"),
        "resident_after": api("/api/ps"),
        "request_options": {"num_ctx": 4096, "num_predict": 1024, "temperature": 0.4},
        "results": results,
        "cancellation": cancellation,
        "missing_model_error": missing_error,
        "limitations": (
            "One synthetic case per task, plus a warm chat repeat. "
            "No general quality score or extensive benchmarking."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"Evidence saved to {args.output}", flush=True)


if __name__ == "__main__":
    run()
