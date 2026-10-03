# Daily-use candidate — 0.1.1

This local Mac candidate adds a source-backed launcher and writing reliability
safeguards. It is ready for owner evaluation on the prepared Mac; a standalone,
Developer ID signed and notarized release remains a separate gate.

## Launch

Prepare the environment described in the README, then build the local launcher:

```sh
.venv/bin/python tools/build_mac_launcher.py
open '.build/Miwl 2.app'
```

Use `--python /absolute/path/to/prepared/python` to reuse an existing environment.
Use `--data-dir /absolute/path/to/disposable-workspace` when building a QA launcher.
The generated bundle records local checkout/environment paths. Moving either
requires rebuilding; it does not bundle Python, dependencies, runtimes or models.
It is ad-hoc signed. The owner-evaluation build reuses the previously prepared
Python environment and approved runtimes through an ignored local runtime link.
No runtime/model is included in Git or downloaded by the launcher.

## Writing safeguards

- New writing databases are mode 0600. Newer schema versions are refused before
  writes. Legacy migration first creates a verified snapshot, then commits DDL
  and the version together. A failed migration rolls back its schema changes.
- Startup creates one writing snapshot per UTC day; **Writing provider → Back up
  writing** first flushes pending editor changes and creates an explicit copy.
  Five managed snapshots are retained in `writing-backups` beside the workspace.
  The folder is mode 0700 and copies are mode 0600. They contain plaintext
  writing, history and settings. Document indexes and galleries are separate.
- Backups use SQLite's consistent backup API, including committed WAL contents,
  integrity checks, fsync and atomic file publication. Unmanaged files are left
  alone. A failed publication preserves previous copies and the original.
- Invalid saved provider settings activate the labelled fixture with a notice.
  The invalid setting is retained until the owner explicitly saves a provider.
- Current source, draft and request remain intact. Only the newest complete chat
  exchanges fitting the UTF-8 budget are included. A notice records omitted
  exchanges. Current text that exceeds the budget is rejected before a writing
  job or cloud credential lookup begins.
- Streaming persistence is limited to 20 updates per second, with the first
  chunk immediate and terminal text flushed. Stopped/failed job status and
  partial text commit together. A generic 64 Ki-character response limit protects
  adapters in addition to their transport limits.
- A final storage failure releases the active job, displays an actionable error,
  and blocks further generation until reopening. An editor write failure is
  visible and asks the owner to copy edits before closing. Prior saved drafts
  remain protected by transactions and revision gates.

### Recover without overwriting the original

Close Miwl. Choose a snapshot from `writing-backups`, copy it to a **new empty
folder** as `workspace.sqlite3`, then run:

```sh
.venv/bin/python -m miwl2 --data-dir /absolute/path/to/recovered-workspace
```

Inspect the recovered writing before using it. This creates a separate workspace;
it does not restore a document index, gallery, or changes after that snapshot.
Interrupted responses are marked failed and can be retried. Keep originals and
snapshots until the recovered writing has been checked. A schema refusal needs
an app version supporting that schema, rather than a forced downgrade.

## Verification and measurements

The final checkpoint passes **152 tests**, Ruff check/format and strict mypy
across **21 source modules**. New tests cover future-version refusal, migration
rollback, reopenable prior snapshots, WAL-aware backups, publication failure,
permissions/retention, corrupt provider settings, Unicode history budgets,
preflight isolation, coalesced burst output, generic output overflow and atomic
terminal transitions. Existing tests cover cancellation, stale results, retry,
document deletion and privacy boundaries.

Native Cocoa Qt fixtures at 1380×844 and 960×720 completed four Stop cycles,
backup actions, failure/retry, and two document import/search/citation/confirmed
removal cycles. The selected fictional originals were unchanged; no QML warnings
were emitted. Import used a local QUrl. These checks do not substitute for OS
file-picker, accessibility, Dock or real hardware checks.

LaunchServices opened the real app through a temporary auto-quit QA wrapper;
the prepared source-backed launcher passed ad-hoc signature verification and
exited after the app closed. It was tested against an isolated workspace.

Measured on Apple M3 Pro, 18 GiB RAM, 11 logical CPUs, macOS 27.0, with the
already approved Ollama 0.35.0 / Gemma 3 4B Q4_K_M. Model requests used fictional
Cedar Library notes, temperature 0.4, context 4096 and up to 1024 output tokens.

| Check | First visible text/window | Completion |
| --- | --- | --- |
| Fresh writing workspace, new process | 0.658 s | — |
| Existing workspace, two new processes | 0.646 / 0.668 s | — |
| Chat, no model resident beforehand | 3.542 s | 4.476 s |
| Summary, warm model | 0.520 s | 4.897 s |
| Article, warm model | 0.518 s | 5.022 s |
| Paraphrase, warm model | 0.543 s | 4.591 s |

Startup includes a 100 ms paint allowance; OS caches were not cleared. App peak
RSS was 235–239 MB (224–228 MiB). A separate fixed warm-chat follow-up sampled
Ollama service plus `llama-server` RSS every 100 ms: peak sum **4,655,988,736 bytes**
(4.34 GiB). Provider-reported model/VRAM size was 3,724,730,695 bytes; these measures
can overlap and must not be added. The original sampler measured only the service;
the corrected follow-up includes the separate inference worker.

These are small sequential observations, not latency/quality guarantees. Warm
repetition can benefit from caching. No real sensors, people, credentials or
paid calls were used. The existing owner app/workspaces were left intact.

Reproduce checks with the prepared environment:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests tools
.venv/bin/ruff format --check src tests tools
.venv/bin/mypy
.venv/bin/python tools/verify_daily_use.py
.venv/bin/python tools/verify_mac_launcher.py
.venv/bin/python tools/benchmark_startup.py
# Requires the already approved installed model and running local service:
.venv/bin/python tools/benchmark_local.py --output evidence/readiness-local-inference.json
.venv/bin/python tools/update_milestones.py
```

Generated evidence stays ignored. Root `milestones.json` is the public-safe
status summary, refreshed from local verification receipts.

## Release gates

- [x] Version-safe transactional writing migrations and consistent private backups.
- [x] Bounded conversation context, response output and streaming persistence.
- [x] Stop/retry, draft protection, and visible storage failures.
- [x] Synthetic document search, snapshot citation and confirmed removal.
- [x] Local source-backed Mac launcher and LaunchServices QA.
- [x] Full synthetic suite, native normal/compact fixtures and measured local tasks.
- [ ] Standalone packaging, fresh-machine install/upgrade and long-running soak.
- [ ] Developer ID signing/notarization; manual Dock identity and permission attribution.
- [ ] Owner-triggered real microphone capture and audible playback/Stop.
- [ ] Explicitly budgeted real cloud compatibility check with owner credentials.
- [ ] Consented held-out face accuracy, quality and spoofing evaluation.
- [ ] EmbeddingGemma terms review before any installation; keyword retrieval remains active.
- [ ] Review and authorize the local branch before public pushing.
