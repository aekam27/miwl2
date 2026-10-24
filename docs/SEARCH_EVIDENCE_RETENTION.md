# Rejected document searches retain evidence

A source search can already have useful passages and an open citation when the
user clears the search field and presses Return. Previously `search()` cleared
that evidence before validating the replacement text. The rejected input left
an empty results area and a status that still described the old matches.

Validation now happens before evidence is cleared. A rejected empty, whitespace,
or overlong search retains its passages, citation, and accepted question. The
status identifies the retained search. Local quotation selection continues to
use that accepted question, rather than the rejected replacement. An accepted
new search still clears the previous evidence, including when no matches exist.
Changing selected sources, removal, and cancellation retain their existing
invalidation behavior.

Verification: the three new regression cases fail on the previous implementation
and pass with the fix; all 177 tests pass. Ruff check/format and strict mypy pass.
The actual QML Enter-key path was also exercised on the offscreen Qt backend
with one fictional Markdown document; before/after window captures have no QML
warnings. No model service, real documents, or credentials were used.

This is a local source change. It does not establish semantic retrieval quality,
OS file-picker accessibility, native Cocoa keyboard delivery, or packaged-release
readiness. Failures after a valid search starts retain the existing behavior.
