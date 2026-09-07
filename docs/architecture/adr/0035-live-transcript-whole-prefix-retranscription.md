# 0035 — Live transcript: whole-prefix re-transcription, ephemeral cache-only state

## Status
Accepted (2026-09-07). Post-GA, roadmap item P2-1.

## Context

The roadmap asks for a live transcript and live draft during recording:
"gestückeltes Streaming, finaler Lauf danach" (chunked streaming, final
pass afterward), updating every 5–15s live, with the final pass 30–60s
after recording stops. VocaDox has no real-time streaming ASR provider —
`faster-whisper`/`FakeSpeechProvider` both transcribe a complete audio
file, not a live audio stream. Three design questions: (1) how to get
periodic partial transcripts out of a file-based transcription API,
(2) where live state lives, and (3) what "final pass" means here.

## Decision

**1. The frontend periodically sends the WHOLE recording-so-far, not a
delta.** `MediaRecorder`'s `ondataavailable` timeslices are opaque WebM
continuation clusters after the first one — only a blob that includes
the very first timeslice is independently decodable. Sending genuine
deltas would require the browser to either restart the recorder per
chunk (audible artifacts, real complexity) or ship a WebM
demuxer/remuxer client-side (a new dependency for a live-preview
feature). Sending the whole growing blob every ~10s and having the
backend re-transcribe it, replacing the previous live transcript
wholesale, sidesteps this entirely at the cost of re-transcription work
growing with recording length — accepted for a live PREVIEW during a
typical few-minutes recording; the authoritative transcript is still
produced once, efficiently, by the existing post-recording pipeline
(`app.processing.orchestrator.execute_transcribe`), which this feature
does not change or replace.

**2. Live state lives only in the cache (`CacheBackend`/Valkey), never
the database.** A `Transcript`/`TranscriptSegment` row carries real
meaning elsewhere in this codebase — review status, evidence links,
speaker assignment, export. A live-preview transcript has none of that:
no final segment boundaries, no review, no evidence chain. Modeling it
as a real (if temporary) `Transcript` row would mean either fabricating
that structure or special-casing every consumer of `Transcript` to know
"this one might not be real yet" — both worse than keeping it entirely
out of the domain model. `app.live.store.LiveSessionStore` mirrors
`app.identity.sessions.SessionStore`'s existing "thin wrapper over
CacheBackend, TTL-bound" pattern exactly. State is lost if Valkey
restarts or the 30-minute TTL elapses — both acceptable, since this is a
discardable aid, never the system of record, and a lost live preview
costs nothing (the recording itself is unaffected; the real transcript
is produced fresh after upload regardless).

**3. "Final pass" is the EXISTING post-recording pipeline, unchanged.**
The roadmap's "final nach 30–60s" describes the latency users should
expect once recording stops — which the already-async, worker-based
pipeline (queued jobs, a worker picks them up) already delivers for a
typical recording; this measure does not need to build a new "final
pass," only make sure the live preview gets out of the way once it's
done (frontend clears live state via `DELETE .../live` at finalize/
discard time — see `RecordingWorkspace.tsx`).

**4. The live draft is a plain-text LLM summary, never a structured
extraction.** `app.intelligence.service`'s real extraction produces
evidence-linked `ExtractedFact` rows tied to real segment sequence
numbers — a mid-recording transcript has no final segments to link to
yet. The live draft instead asks the LLM (`LLMProvider.complete`,
unstructured) for a short, explicitly-labeled-provisional bullet
summary of the transcript-so-far, gated to regenerate only after
meaningful transcript growth (word-count thresholds in
`app.live.service`) so it doesn't call the LLM on every 10s tick.

## Consequences

- No new dependency (no WebSocket library, no client-side WebM
  demuxer, no streaming-ASR model).
- Re-transcription cost scales with recording length — acceptable for
  the target use case (a live preview during recording), disclosed as a
  known trade-off; a genuinely long recording (say, over an hour) would
  see this cost grow noticeably, at which point a real streaming ASR
  provider would be the correct fix, not a workaround here.
- The live transcript can never be perfectly in sync with what's
  literally being said right now — there is always a "transcribe the
  last ~10s of growing audio" latency baked in, consistent with the
  roadmap's own 5–15s target rather than true sub-second streaming.
- Because live state is cache-only, restarting the backend/Valkey mid-
  recording loses the live preview but never the actual recorded audio
  (that stays in the browser's `MediaRecorder` buffer until upload) —
  the failure mode is "the preview goes blank," never data loss.
