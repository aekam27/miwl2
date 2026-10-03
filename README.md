# Miwl 2

A local desktop workspace for source notes, conversations and editable drafts.
Built by [Aekam](https://github.com/aekam27) with AI assistance as a modern
iteration of his final-year college project. The original
[Kivy application](https://github.com/aekam27/PythonDesktopApplicationUsing-KIVY)
remains a separate repository.

This is the current runnable source, including the integrated composer and
Send/Write/Stop controls. It is an early Mac-focused project, not a signed or
notarized desktop release. Project code is **MIT licensed**; dependencies and
optional models retain their own licenses and terms.

## What works, and what has been verified

| Capability | Current behavior | Verification limits |
| --- | --- | --- |
| Writing | Saved sessions, source notes, streaming chat/refinement, summaries, paraphrases, article tasks and editable drafts | Local Ollama/Gemma exercised with fictional notes; outputs need review |
| Composer | One input surface, multiline growth, bounded scrolling, raised Send/Write, focus/disabled states and cancellable Stop | Native Cocoa Qt synthetic fixtures at normal and compact sizes |
| Documents | Explicit UTF-8 text/Markdown import; selected-source FTS5/BM25 search; optional local selection of exact quotations; snapshot citations with lines and hash | Exact quote checks do not establish relevance, recall, completeness or semantic search quality |
| Voice | Optional local WAV transcription, explicit Mac recording, transcript review and requested system speech playback | Synthetic audio and UI tests; no claim of real microphone reliability or multilingual accuracy |
| Camera and gallery | Two independently configured MJPEG sources; optional consented local face matching; encrypted named gallery | Synthetic streams/model smoke tests and mock descriptors; no real-person accuracy or liveness validation |
| OpenAI cloud | Optional text-only provider, user-owned macOS Keychain credential and consent for each request | Mock SSE tests only; no paid-call verification; no silent cloud fallback |

The deterministic fixture is prominently labelled **Test mode / No AI**. It
demonstrates workflows without a model, network requests or credentials.
Embedding models are not included or installed; document retrieval uses keyword
search. Real sensors and cloud services are never required for the test suite.

## Install and run

The verified environment is Apple Silicon macOS, Python 3.13 and Qt 6.11.
Python 3.12+ is required. Other operating systems are not verified; recording,
speech playback and credential lookup use macOS APIs.

```sh
git clone https://github.com/aekam27/miwl2.git
cd miwl2
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m miwl2 --data-dir .local-data
```

A fresh workspace starts with the labelled fixture provider. Paste source notes,
choose **Summarize notes**, then open **Editable draft** to edit and copy. Chat
can refine a draft; **Write article** takes a topic and optional notes.
The Send control becomes **Stop** during a response. Stopping a response leaves
the completed saved draft intact. Source and result edits save automatically.

The editable installation is intentional: optional runtime tools resolve from
the checkout's `.runtime` directory. A bundled application and non-editable
runtime layout are future packaging work.

With no `--data-dir`, Qt chooses the platform application-data directory
(`~/Library/Application Support/Aekam/Miwl 2` on macOS). One process can open a
workspace at a time. Keep private workspaces outside version control.

### Optional local Ollama

Install Ollama from its [official source](https://ollama.com/download).
Review the model's current terms before downloading it. Configure a loopback
HTTP endpoint such as `http://127.0.0.1:11434` and an installed local model such
as `gemma3:4b` in the provider popup. Miwl accepts loopback Ollama endpoints and
rejects model names marked as cloud. Writing is limited to one job, bounded
input/output and a 4096-token context; large-document synthesis is future work.

No runtime or model weights are distributed here. See
[optional runtime setup](docs/OPTIONAL_RUNTIMES.md) for provenance, pinned hashes,
voice/vision setup and terms. The supplied `start_local_runtime.sh` is for an
optional project-local `Ollama.app`; it is not an installer.

### Optional OpenAI cloud text

In **Keychain Access**, create your own generic password item:

- Item name: `org.aekam.miwl2.openai`
- Account: `Miwl 2`
- Password: your own API key; never put it in this repository or a `.env` file.

Choose **Cloud · OpenAI**, the fixed `https://api.openai.com/v1` endpoint and a
Chat Completions model enabled for your account. Confirm the disclosure checkbox
for each Send, writing operation or Retry. That request's notes, draft and
relevant conversation can leave the Mac; provider billing applies, including
potential charges after cancellation. The key is looked up only for an explicit
authorized request and is not saved to the workspace database.

Cloud document grounding and voice-transcript transmission are disabled. Images,
camera frames and biometric payloads are not sent through this adapter. There
is no live cloud model discovery, price estimate or cloud accuracy claim.

## Test and develop

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests tools
.venv/bin/ruff format --check src tests tools
.venv/bin/mypy
```

The source checkpoint has **136 passing tests**, Ruff check/format and strict
mypy across 20 source modules. Tests use temporary workspaces and synthetic
loopback servers; environments that prohibit localhost socket binds must allow
those fixture servers. Tests do not require microphones, cameras, actual API
keys, paid calls or model weights. See [verification scope](docs/VERIFICATION.md).

`tools/` contains optional synthetic visual checks and explicit local-model
benchmarks. Benchmark scripts are opt-in and are not part of the default test
suite. `native/` contains the optional Swift recording helper source. Generated
previews and temporary QA data are ignored by Git.

## Privacy and appropriate use

Writing sessions and imported document copies are **plaintext SQLite**, not an
encrypted vault. The optional gallery encrypts face descriptors and names with
a passphrase; this does not encrypt writing sessions. The application is a
single-user workspace, not a multi-tenant service.

Import only files you choose. Use camera streams you own or are explicitly
authorized to access. Enroll only consenting adults who understand storage,
matching and deletion. A suggested face match is uncertain similarity evidence,
never authentication or a basis for consequential decisions. Unknown and
uncertain results are expected. See [privacy and safety boundaries](docs/PRIVACY_AND_SAFETY.md).

## License

[MIT](LICENSE) covers original Miwl 2 source, tests, documentation and included
project branding assets to the extent of the project's rights. It does not
relicense Qt/PySide, other dependencies, optional model weights or Apple system
components. The repository contains no dependency binaries or model weights.
Read [third-party notices](THIRD_PARTY_NOTICES.md) before distributing a bundled
application; Qt LGPL obligations require additional packaging work.
