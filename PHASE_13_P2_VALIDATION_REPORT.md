# Phase 13 (Post-GA) — Stage P2 Validation Report

## Executive Summary

Stage P2 of the post-GA competitive roadmap (`[[vocadox-competitive-roadmap]]`)
is complete: all three measures merged to `main` — five PRs in total,
since P2-2 split cleanly into two independently-shippable halves — each
with all 7 required CI checks green, each deployed and spot-checked live
against the real dev stack. **Recommendation: GO** to begin Stage P3.

Same posture as the P0/P1 reports: this documents what shipped, how it
was verified, and what remains honestly open, under the standing
autonomous GO (`[[github-workflow-autonomy]]`) — not a Phase 0-12-style
full hardening audit. Stage P2 is also the first stage where the
standing directive's own ESKALATION criteria were actually triggered —
see P2-2 below.

## Scope

| # | Measure | PR(s) | Merge commit(s) |
|---|---|---|---|
| P2-1 | Live transcript + live draft during recording | [#72](https://github.com/ley338-gif/VocaDox/pull/72) | `6fd80e8` |
| P2-2 | System-audio/tab capture (bot-free) | [#73](https://github.com/ley338-gif/VocaDox/pull/73) | `13ee512` |
| P2-2 | Calendar automation (local `.ics` import) | [#74](https://github.com/ley338-gif/VocaDox/pull/74) | `8c4c26c` |
| P2-3 | Mobile PWA + offline recording queue | [#75](https://github.com/ley338-gif/VocaDox/pull/75) | `dd9cace` |

Each addresses "reach": a live preview during recording instead of
waiting until upload to see anything; recording a video call already
running in the browser without a meeting bot; pre-filling a conversation
from a calendar entry instead of retyping it; and a genuinely usable
mobile experience that survives losing connectivity.

## P2-1 — Live transcript + live draft

- New `app.live` module (backend): while recording, the browser
  periodically (~10s) sends the whole recording-so-far, which the
  configured speech provider re-transcribes, replacing a cache-only
  (never database) live transcript. A coarser, word-count-gated LLM call
  regenerates a short, explicitly-provisional plain-text draft.
- Both are discarded once the real, authoritative post-recording
  pipeline takes over — never persisted as a real `Transcript`/
  `ExtractedFact`, never carry evidence links.
- **Disclosed assumption** (ADR-0035): whole-prefix re-transcription
  rather than true delta streaming, since only the first `MediaRecorder`
  timeslice carries a decodable WebM header. Cost grows with recording
  length — accepted for a live preview during a typical recording.

## P2-2 — System-audio capture + calendar automation

- **Audio capture** (PR #73): `useRecorder.ts` gained a `system-audio`
  source using `getDisplayMedia({audio:true, video:true})` — video is
  required by Chromium to reliably surface the "share tab audio"
  checkbox, and is stopped/discarded immediately, never recorded. A
  share with no audio track is a clear, actionable error, not silent
  silence-recording. No backend change; the finalize path doesn't care
  which source a recording came from.
- **Calendar automation** (PR #74) — **the roadmap's own ESKALATION
  criteria were triggered here** and honored: any design giving
  genuinely live/automatic upcoming-meeting detection needs a runtime
  network connection to an external calendar service plus an OAuth
  account/secret, both explicit stop-and-ask triggers in the standing
  directive, in direct tension with ADR-0007's air-gapped posture. This
  was escalated to the user via `AskUserQuestion` before any
  implementation began; the user chose local `.ics` file import over
  live OAuth sync or deferring the measure. A small, dependency-free
  RFC 5545 subset parser (`frontend/src/lib/icsParser.ts`) runs entirely
  client-side; nothing from the calendar file reaches the backend until
  the user explicitly creates a conversation, and even then only the
  title. See ADR-0037 for the full record and disclosed
  recurrence/timezone limitations.

## P2-3 — Mobile PWA + offline recording queue

- Installable PWA: `manifest.webmanifest`, placeholder icons (generated
  with Pillow — an existing **backend** dependency, reused rather than
  adding a new frontend one), and a hand-written service worker
  (`public/sw.js`, runtime cache-as-you-go, never caching `/api/`).
- Offline recording queue: a finished recording whose upload fails at
  the network level (offline — distinguished from a server-rejected
  upload by error type) is now saved to IndexedDB
  (`app.recording.offlineQueue`) instead of only the pre-existing
  in-memory "click retry" state, which never survived a page reload —
  the realistic mobile scenario. `useOfflineQueueSync` flushes
  automatically on reconnect/app load; a new `queued-offline` state was
  added to `recordingMachine.ts` alongside (not replacing) the existing
  `upload-failed` path.
- **Disclosed assumption** (ADR-0038): hand-written service worker and
  hand-wrapped IndexedDB rather than `vite-plugin-pwa`/`idb`, avoiding
  new dependencies at the cost of no build-time asset precaching (a
  page/asset is offline-available only after being loaded online once).

## Test / CI Summary

- Backend: `pytest -q` grew from 374 (unchanged since P1-4, since P2-1
  was the only Stage-P2 measure touching the backend at all — P2-2 and
  P2-3 are frontend-only) throughout the stage, 0 failed. `ruff check .`
  and `mypy app` clean on every PR (193 source files by the end of
  P2-3).
- Frontend: `vitest run` grew from 21 → 26 (P2-2's calendar half, +5
  `icsParser` tests) → 27 (P2-3, +1 `recordingMachine` test for the new
  `queued-offline` transition). `tsc -b --noEmit`/`eslint .`/`vite build`
  clean on every PR — P2-1's live-preview panel and P2-2's audio-source
  picker/calendar-import UI were verified via typecheck/lint/build only
  (no new component-level Vitest suites), matching this project's
  established precedent (Phase 12 Finding #10).
- `python compliance/check_licenses.py`: **PASS** on every PR. Stage P2
  added **zero new dependencies** anywhere — backend or frontend.

## GitHub Actions

All five PRs' final commits show all 7 required checks green:

| Check | #72 (P2-1) | #73 (P2-2a) | #74 (P2-2b) | #75 (P2-3) |
|---|---|---|---|---|
| Backend (lint/typecheck/test) | PASS | PASS | PASS | PASS |
| Frontend (lint/typecheck/test/build) | PASS | PASS | PASS | PASS |
| Alembic migration (real Postgres) | PASS | PASS | PASS | PASS |
| OpenAPI TS client drift check | PASS | PASS | PASS | PASS |
| License compliance | PASS | PASS | PASS | PASS |
| Docker build | PASS | PASS | PASS | PASS |
| Container vulnerability scan (Trivy) | PASS | PASS | PASS | PASS |

## Live Deployment

Each PR was deployed to the real local dev stack immediately after
merge. P2-1 (the only backend-touching measure) got a full
`backend`/`frontend` rebuild, no migration (cache-only state, no schema
change), and a `GET /health/ready` + unauthenticated-route spot-check
(`GET .../live` → `401`). P2-2 and P2-3 needed only a `frontend`
rebuild/restart each, verified with a `GET /health/ready` check and,
for P2-3, a direct check that `/manifest.webmanifest` and `/sw.js` are
actually served (`200`) by the running container. No exhaustive
re-verification beyond that, per `[[feedback-verification-scope]]`.

## Known Limitations / Assumptions (disclosed, not blocking)

1. **P2-1**: re-transcription cost scales with recording length; a
   genuinely long recording would need a real streaming ASR provider,
   not a fix to this measure.
2. **P2-2 (audio)**: Firefox's tab-audio-sharing support varies by
   version/platform — `isSystemAudioCaptureSupported()` feature-detects
   the API itself, not whether a given browser's picker will actually
   offer audio; the empty-audio-track check at grant time is the real
   safety net.
3. **P2-2 (calendar)**: local import only, no live sync — a user must
   re-export and re-import to see newly added events. No `RRULE`
   recurrence expansion, no `TZID` timezone resolution. Both disclosed,
   real gaps, not silently worked around — the fallback is simply typing
   the title manually, same as before this measure existed.
4. **P2-3**: service worker caching is opportunistic (cache-as-you-go),
   not build-time precached — first-visit-offline is not guaranteed.
   The offline queue's flush is sequential and stops at the first
   failure per pass (simplicity over exhausting retry combinations).
   PWA icons are placeholder brand assets (a Pillow-generated "V"), not
   designed artwork.
5. No independent security/privacy/threat-model sweep (Phase 12-style)
   was run across Stage P2's new surface area specifically. The
   recommendation from the P0/P1 reports stands: do one before Stage P3
   (redaction + expiring share links).

## Findings Register

No process or product-correctness finding was found in this stage — all
five PRs' first CI run passed on every check. The one process deviation
worth naming explicitly: P2-2's calendar-automation half is the first
measure in this roadmap where the standing directive's ESKALATION
criteria were actually triggered and honored (see above) — not a defect,
the mechanism working exactly as the directive specified.

## Next

Stage P3 begins with **P3-1** (one real backend-system integration — FHIR
DocumentReference or GDT for German practice-management systems,
decided and justified in an ADR) followed by **P3-2** (fact-level
redaction with the evidence chain preserved, plus expiring share links
for the Recap).
