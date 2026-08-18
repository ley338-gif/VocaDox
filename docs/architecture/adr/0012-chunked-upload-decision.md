# 0012 — Recording upload: single finalize request, not server-side chunking

## Status
Accepted

## Context
The brief asks explicitly to evaluate upload-once vs. chunked-during-
recording for browser captures, given the target use case includes long
(potentially 120+ minute) medical/therapy conversations where losing an
entire take to a network blip is a real cost. The two designs:

1. **Chunked-during-recording**: the browser uploads each `MediaRecorder`
   `ondataavailable` chunk to the server as it's produced, the server
   assembles them in a tracked `RecordingUpload` session, and a final
   "finalize" call turns the assembled chunks into an immutable
   `MediaAsset` — resilient to a browser/tab crash partway through, since
   already-uploaded chunks aren't lost.
2. **Upload-once**: the browser accumulates `MediaRecorder` chunks
   client-side (already itself chunked internally, just not uploaded
   incrementally) and sends the assembled `Blob` in a single streamed
   request when recording stops.

## Decision
Phase 2 implements **upload-once** with an idempotent finalize endpoint
(`POST /conversations/{id}/recordings?idempotency_key=...`), backed by a
`RecordingUpload` table that already has the shape a real chunked flow
would need (`expected_sequence`, `received_bytes`, `status`,
`idempotency_key`) — so growing into true incremental chunk endpoints
later is additive, not a redesign.

Rationale for deferring true chunking rather than skipping the analysis:
- The dominant failure mode this guards against — a **network blip during
  the final upload**, not a crash mid-recording — is already mitigated by
  the idempotent finalize: a retried finalize with the same
  `idempotency_key` returns the already-created `MediaAsset` instead of
  creating a duplicate (`app.conversations.router.finalize_recording_endpoint`,
  tested in `tests/conversations/test_api.py::
  test_recording_finalize_is_idempotent`).
- A real chunk-by-chunk upload protocol needs: per-chunk auth+conversation
  re-validation, strict sequence enforcement, partial-chunk cleanup on
  abandonment, and a reassembly step that itself needs the same
  hash/validate/atomic-move consistency model as the current single-shot
  path — meaningfully more surface area than Phase 2's scope justifies
  given the mitigation above already covers the primary risk.
- **What chunking would still add and this design does NOT cover**: a
  browser crash or forced tab close *during* an active (unfinalized)
  recording still loses that take — the audio only becomes durable at
  `MediaRecorder.stop()` + finalize. This is a real, honestly-documented
  gap, not something this ADR claims to solve.

## Alternatives considered
- **Full chunked ingestion in Phase 2.** Rejected for the scope reasons
  above; deferred to a later phase if operational experience shows
  crash-during-recording data loss is a frequent problem in practice.
- **No idempotency handling at all.** Rejected — a naive retry-on-
  network-error would create duplicate `MediaAsset` rows for the same
  physical recording, which is both wasteful and confusing in the UI.

## Consequences
- `docs/user/recording.md` documents the crash-during-recording limitation
  plainly: "if your browser or tab crashes while still recording, that
  take is lost — click Stop as soon as it's safe to do so."
- The `RecordingUpload` table and `expected_sequence`/`received_bytes`
  columns are currently write-mostly (`status` transitions
  `in_progress → completed`) rather than driving real sequencing logic —
  intentional scaffolding, not dead code, for the deferred chunked flow.
