# Verification scope

## October 6 worker-dispatch regression

A failed Python worker-thread start now marks the response failed, releases the
active job and preserves saved writing. Retrying does not run the abandoned
queue item. If saving the failure also fails, further requests remain blocked
until reopening the workspace.

Both new tests failed against the October 4 source and pass with this change.
The affected storage/service tests pass **32 tests**; the aggregate run passes
**114 non-UI tests** using fictional temporary databases and synthetic loopback
servers. Ruff check/format (50 files), strict mypy (21 modules), and diff checks
pass. The 50 Qt window tests were excluded because UI launch was outside this
run's scope. The previous full-suite checkpoint was **162 tests on October 4**;
this is not a claim that the expanded 164-test suite was run in full. Native
macOS Quit/Cmd-Q remains untested.

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
