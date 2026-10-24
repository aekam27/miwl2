# Source-and-draft workspace

The previous Documents view showed search results separately from the editable
draft. This change puts both in one workspace on wide windows and adds a compact
Sources/Draft switch. Both draft surfaces edit the same saved session value.

Quotation insertion verifies that the result is still selected and its indexed
chunk still has the expected source hash and exact passage. It inserts a plain
text blockquote, filename, snapshot line range and SHA-256; it does not expose
the original filesystem path or call an AI provider. It preserves pending edits,
flushes them before insertion, and leaves failed saves visible/retryable.

## Verification

- Full suite: 181 passing tests; Ruff check/format; strict mypy on 21 modules.
- New Qt coverage: saved draft survives insertion/reopen; pending-save failure
  blocks insertion; replaced or unselected source cannot be quoted; compact
  switching preserves edits. Existing import/search failure preservation passes.
- Actual offscreen Qt captures use three fictional Markdown notes, three matching
  passages and an existing draft. The wide after view shows evidence and editing
  together; the baseline did not. No model or cloud calls were made.
- A 12-sample view-switch/render probe measured median 1.69 ms before and 0.67 ms
  after; process peak RSS was about 202 MB in each run. This is an offscreen local
  diagnostic, sensitive to warm-up and scheduling, not evidence of an app-wide
  speed improvement. The release claim is the verified workflow change.

## Limits

Keyword retrieval does not guarantee relevance or completeness. Quotations refer
to imported snapshots. Provenance in the draft is plain text, not clickable;
there is no citation manager or automatic bibliography. Writing and imported
snapshots remain plaintext local storage. No signed desktop release is produced.
