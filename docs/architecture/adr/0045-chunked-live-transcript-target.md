# ADR-0045: Chunked live-transcript target architecture

- Status: Accepted target; implementation deferred
- Date: 2026-09-10
- Supersedes the long-recording suitability assumption in ADR-0035

## Context

ADR-0035 deliberately chose whole-prefix retranscription as a small, reliable
preview implementation for short recordings. The browser uploads the entire
recording-so-far every ten seconds and the backend replaces the cached preview.
Phase 14 requires evaluating this design for realistic 20–60-minute sessions.

The reproducible workload benchmark in
`backend/benchmarks/live_transcript_scaling.py` proves that the algorithm is
quadratic in recording duration. At 20 minutes it asks the provider to process
20.17 audio-hours (60.5 times the source); at 60 minutes it asks for 180.50
audio-hours (180.5 times the source). This is not suitable for the target
duration even if a particular GPU temporarily hides the latency.

## Decision

Keep the current implementation as a short-recording preview while the
replacement is built behind a configuration flag. Do not extend or optimize
whole-prefix retranscription as the long-term path.

The target pipeline is:

1. Capture the authoritative recording unchanged with `MediaRecorder` for the
   existing finalize/upload path.
2. In parallel, derive independently decodable, fixed-duration audio windows
   for live preview. Prefer browser-produced mono PCM/WAV windows over parsing
   opaque WebM continuation clusters. Each window carries a session ID,
   monotonic sequence number, start/end time, SHA-256 digest, and idempotency
   key.
3. Use a ten-second new-audio window with two seconds of overlap by default.
   Allow only one in-flight window per session. Under backpressure, coalesce
   unsent preview work rather than building an unbounded queue; the
   authoritative recording must never be affected.
4. Transcribe each window with the local speech provider. Pass a bounded tail
   of the accepted transcript as rolling prompt context where the provider
   supports it; never resend the full audio prefix.
5. Merge on word timings within the overlap. Text older than the overlap
   becomes stable; the newest tail remains explicitly provisional and may be
   replaced by the following result. Duplicate sequence/digest submissions
   return the prior result.
6. Keep live audio and text ephemeral in Valkey/storage with a bounded TTL.
   Delete each raw preview window immediately after inference. Do not create
   `Transcript` domain rows or evidence links from provisional content.
7. When recording ends, discard live state and run the existing full-file,
   full-quality transcription. That authoritative reconciliation remains the
   only source for review, facts, protocols, documents, evidence, and export.

## Rollout gates

Implementation requires, before becoming the default:

- browser compatibility tests for independent live windows while the final
  Opus/WebM recording remains byte-correct;
- merge tests covering repeated words, silence, boundary-split words, changed
  partial hypotheses, missing/out-of-order/duplicate windows, and reconnects;
- 20-, 40-, and 60-minute soak tests on documented CPU and GPU profiles;
- bounded-memory/backpressure tests and organization/authz regression tests;
- comparison of preview lag and word error rate against whole-prefix preview;
- an operator-visible fallback when live preview is unavailable. Final
  recording and authoritative processing must remain functional.

## Consequences

At the benchmark defaults, rolling overlap work stays near 1.20 times source
duration instead of growing to 60.5–180.5 times. The design adds merge logic
and a parallel preview encoding path, so implementing it immediately in this
architecture-only change would create unacceptable recording risk. ADR-0035
remains an honest description of current behavior, but its current approach is
not approved as the production architecture for 20–60-minute conversations.
