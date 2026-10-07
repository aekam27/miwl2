# Verification scope

## October 7 native Cmd-Q coverage

The existing save guard passes five native Cocoa scenarios without a production
code change: clean Quit, pending source/draft saves, rejected source saves,
rejected draft saves, and repeated Quit requests. Each scenario also reopens the
same fictional workspace in a fresh app process and checks the actual editors.
Failed saves leave the app open with the edited text, prior stored writing and a
visible error. A further edit followed by retrying Quit saves the latest text.
Three queued Quit requests during failure remain serialized; successful recovery
produces one shutdown notification.

The harness queues actual AppKit `NSEvent` Cmd-Q events to its own application and
observes their delivery while the normal Cocoa event loop runs. It does not call
the QML close handler or Qt's quit slot as the test action. The enabled native
menu action is `terminate:`. Automatic foreground activation is disabled, and
the foreground process stays unchanged at the checked points. Fixtures use
temporary writing and injected SQLite errors; no devices, models or user stores
are opened. Error-banner captures contain only the fictional fixture.

The full offscreen regression baseline was refreshed: **164 passed in 19.85 s**.
The native checks are separate from that count. A disposable negative-control
copy with the save guard bypassed fails the four writing-protection scenarios;
clean Quit still passes. The real application source is unchanged.

This covers Cocoa delivery of the native menu shortcut. It does **not** cover a
physical keyboard, OS-posted input, or a mouse/Accessibility click on the macOS
menu bar. The current executor reports both Accessibility trust and event-posting
access as false. Those input paths remain pending an authorized desktop session
with the required permissions; no permission prompts or focus changes were used.

To rerun on macOS with the prepared environment and Command Line Tools:

```sh
PYTHONPATH=src .venv/bin/python tools/verify_native_quit.py
```

The helper is compiled into a temporary directory. JSON receipts, process logs
and fictional error previews are saved under ignored `evidence/native-quit`.
Each child has a bounded timeout and checks its actual `cocoa` platform.

## October 6 worker-dispatch regression

A failed Python worker-thread start now marks the response failed, releases the
active job and preserves saved writing. Retrying does not run the abandoned
queue item. If saving the failure also fails, further requests remain blocked
until reopening the workspace.

Both new tests failed against the October 4 source and pass with this change.
The affected storage/service tests pass **32 tests**; the aggregate run passes
**114 non-UI tests** using fictional temporary databases and synthetic loopback
servers. Ruff check/format (50 files), strict mypy (21 modules), and diff checks
pass. The initial run excluded 50 Qt window tests. An explicitly authorized
offscreen follow-up then passed the full **164 tests in 17.27 s**, with runtime
checks confirming the offscreen platform. Native Quit was not tested at that
checkpoint; the October 7 section describes the subsequent native coverage and
its remaining input-delivery limits.

## Earlier source checkpoint

The initial source checkpoint passed **136 regression tests** on Apple Silicon macOS with
Python 3.13, Qt 6.11 and the locked dependency set. Ruff check/format and strict
mypy pass across 20 source modules. This is a development checkpoint, not a
production certification or accuracy benchmark.

Tests cover local storage/restart, request snapshots, provider attribution,
bounded streaming, cancellation and recovery; mocked OpenAI and Ollama HTTP
protocol behavior; synthetic camera streams; encrypted gallery lifecycle and
mock descriptor matching; local voice state handling; selected-source search,
exact quotation/citation checks; and Qt control/layout behavior.

The final composer was visually inspected in actual Cocoa Qt windows at
1380×844 and 960×720 using synthetic QTest interactions. Empty/disabled, ready,
Send focus, Write label, four-line prompts, long scrolling and pending Stop states
were captured. Four short lines fit without clipping, and stopping the fixture
response preserves the completed draft and source. Earlier native accessibility
checks are separate evidence; the final composer pass did not use CUA.

Local Gemma writing and exact quotation selection were exercised with fictional
text. Whisper transcription was exercised with synthetic speech. YuNet/SFace
smoke checks used generated imagery; gallery matching used mock descriptors.
No release claim is made for real microphone/camera operation, real-person
recognition, liveness, semantic retrieval quality, multilingual speech accuracy,
paid OpenAI calls, signed/notarized packaging or alternate operating systems.

To rerun:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests tools
.venv/bin/ruff format --check src tests tools
.venv/bin/mypy
```

The synthetic HTTP tests bind only loopback sockets. A sandbox can block those
fixtures; permit loopback test servers before interpreting network-test failures
as application failures. The default suite needs no models or credentials.

Optional composer captures, using only a deterministic fixture:

```sh
QT_QPA_PLATFORM=cocoa QT_QUICK_BACKEND=software \
  .venv/bin/python tools/verify_composer.py --stage after
```

This creates ignored evidence previews and disposable fictional data. Other
`tools/` scripts can exercise an explicitly configured local runtime; inspect
their prerequisites before running them. Private local evidence and user data
are not distributed with the repository.
