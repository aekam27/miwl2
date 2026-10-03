# Privacy and safety boundaries

## Writing and documents

Source notes, conversation and drafts remain in a chosen local workspace by
default. Sessions use plaintext SQLite/WAL. Imported UTF-8 text/Markdown is
copied into a separate plaintext local index; source paths and hashes are
stored with the snapshot. Files are imported only after explicit selection,
not by scanning personal folders.

Document limits are 1 MB per file, 100 files and 10 MB total imported text.
Search uses only selected imported sources. Optional local quotation selection
receives the question and retrieved passages; saved writing, voice and gallery
data are excluded. Exact quotation checks verify provenance, not truth,
retrieval completeness or freedom from malicious source instructions.

Removing an imported source removes its active copy/index; its original stays
untouched. Secure deletion in the active SQLite index does not erase backups,
filesystem snapshots or previously exported copies. Consider disk encryption
and your backup policy before using sensitive content.

## Cloud text

Cloud is optional and requires a user-owned Keychain credential and disclosure
confirmation for every request. Request notes, draft and relevant history can
be transmitted to OpenAI and incur charges. Stopping a request does not
guarantee zero provider billing. No silent local-to-cloud fallback occurs.
Document grounding, voice-transcript cloud sending, image and biometric cloud
payloads are disabled. Read the provider's current terms and privacy policy.

## Voice

Recording starts only from an explicit action and needs macOS permission.
Temporary recording/control files are removed after completion or cancellation;
the reviewed transcript can become saved session text after you choose to send
it. Imported WAV originals are unchanged. Transcription accepts up to 60 seconds
of 16 kHz mono 16-bit PCM WAV, at most 2 MB. Speech recognition can change meaning;
review the transcript before sending it. Playback uses system speech only when
requested. Real microphone behavior has not been validated by this release.

## Camera and gallery

Use only streams you own or are explicitly authorized to access. Each source
connects and enables matching independently. Never point the app at a stranger's
camera or treat a reachable URL as permission. Frames are processed locally;
this release does not publish a remote camera service.

Enrollment requires an explicit consent confirmation. Limit enrollment to
consenting adults who understand why they are enrolled, what descriptor/name
data is retained, and how it can be removed. Avoid bystanders and keep consent
records outside the repository. Gallery names and face descriptors are encrypted
with a passphrase using scrypt-derived keys and AES-GCM; writing databases are
not covered by gallery encryption. Forgetting the passphrase prevents recovery.

Matching returns **possible**, **uncertain** or **unknown** similarity outcomes.
It does not authenticate identity, test liveness or detect spoofs. Thresholds
are experimental and not calibrated on real people. Never use it to make access,
employment, education, housing, financial or other consequential decisions.
Synthetic tests do not demonstrate real-world recognition accuracy or fairness.

## Development and sharing

Use synthetic fixtures and disposable workspaces. Do not commit databases,
face profiles, recordings, documents, source URLs containing credentials,
API keys, model weights or user exports. This publication contains one clean
source history; local development evidence and private workspaces are excluded.
