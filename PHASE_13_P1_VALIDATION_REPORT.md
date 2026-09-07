# Phase 13 (Post-GA) — Stage P1 Validation Report

## Executive Summary

Stage P1 of the post-GA competitive roadmap (`[[vocadox-competitive-roadmap]]`)
is complete: all four measures merged to `main`, each as its own PR, each
with all 7 required CI checks green, each deployed and spot-checked live
against the real dev stack. **Recommendation: GO** to begin Stage P2.

Same posture as `PHASE_13_P0_VALIDATION_REPORT.md`: this documents what
shipped, how it was verified, and what remains honestly open, under the
standing autonomous GO (`[[github-workflow-autonomy]]`) — not a
Phase 0-12-style full hardening audit.

## Scope

Four measures, in the roadmap's dependency order (P1-1 needed P0-1's
search index; P1-2/P1-3/P1-4 had no hard ordering dependency on each
other, run in the roadmap's listed order):

| # | Measure | PR | Merge commit |
|---|---|---|---|
| P1-1 | "Ask VocaDox" — chat with enforced citation | [#67](https://github.com/ley338-gif/VocaDox/pull/67) | `9e93d54` |
| P1-2 | Voiceprint enrollment for known speakers | [#68](https://github.com/ley338-gif/VocaDox/pull/68) | `0d481b5` |
| P1-3 | Template completeness score + speaking-share/monologue | [#69](https://github.com/ley338-gif/VocaDox/pull/69) | `9b3138f` |
| P1-4 | Evaluation Lab customer-facing quality report | [#70](https://github.com/ley338-gif/VocaDox/pull/70) | `7a1cb8d` |

Each "rebuilds and overtakes" a capability the competitor analysis
identified: chat-with-citation instead of an unconstrained chat feature;
automatic recurring-speaker suggestion instead of purely manual
per-conversation assignment (existing since PR #49); a live completeness
signal instead of a document the reviewer has to eyeball for gaps; a
real exportable quality report instead of an internal-only Evaluation
Lab.

## P1-1 — Ask VocaDox

- New `app.ask` domain: `POST /ask` answers a free-text question using
  facts found via the P0-1 search index, scoped exactly like search
  (organization/team). Server-side citation enforcement
  (`app.ask.service._verify_statements`) keeps a generated statement
  only if every cited `fact_id` is a member of the exact candidate-fact
  set actually offered to the LLM — the same evidence-chain guarantee
  `app.documents.service.compose_document` already enforces, extended to
  an interactive surface.
- New `ask_queries` audit table; new `ask:query` permission.
- Frontend: `/app/ask` page, question history, citations link back to
  the source conversation's Facts tab.
- **Assumption** (disclosed in the PR): single-turn ask-and-answer, no
  persisted multi-turn chat memory — the roadmap's actual technical
  requirement (enforced citation) doesn't depend on multi-turn state.

## P1-2 — Voiceprint enrollment

- `pyannote`'s diarization pipeline already computes a per-speaker voice
  embedding internally; previously discarded (see the 2026-09-06
  `alembic/versions/0013_known_speakers.py` docstring, which explicitly
  deferred automatic matching pending exactly this kind of mechanism).
  Now stored on `DetectedSpeaker.embedding`.
- Explicit human enrollment (`POST .../speakers/{id}/enroll`, requires
  both `speaker:assign` and `known-speaker:manage`) folds a sample into
  a `KnownSpeaker`'s running-average voiceprint. Later diarization runs
  in the same organization compare new detected speakers against
  enrolled voiceprints (pure-stdlib cosine similarity, no new
  dependency) and record a confidence-scored suggestion only above a
  conservative 0.75 threshold — **never applied automatically**.
  Accepting a suggestion (`POST .../speakers/{id}/accept-suggestion`)
  runs through the exact same `assign_speaker` path a manual assignment
  uses.
- New ADR-0032 documents the threshold/storage/matching decisions.
  `docs/user/speakers.md` updated — it previously claimed "no voice
  biometrics at all," which this measure superseded; left unfixed it
  would have been a stale, actively false statement in shipped user
  documentation.

## P1-3 — Template completeness score

- New `GET /conversations/{id}/completeness`: category coverage against
  the conversation's resolved Template (`resolve_effective_config`),
  whether every recorded Decision has a decision-maker and every Task an
  owner, plus speaking-share/longest-monologue from the same diarization
  that produced the conversation's detected speakers. Read-only,
  computed fresh on every call — no new persisted state.
- **Disclosed assumption** (ADR-0033): "Entscheidungsbegründung"
  (decision rationale) maps to the existing `DecisionItem.decided_by`
  field (who decided), not a new reasoning/justification field — adding
  one would be an extraction-schema change beyond this measure's scope.
  The overall score is an unweighted mean of whichever signals actually
  apply (a conversation with no decisions isn't penalized for lacking a
  decision-maker it never had reason to record); "longest monologue"
  merges same-speaker diarization turns across up to 1.5s of silence — a
  disclosed heuristic, not a formally verified measurement.
- Frontend: new "Vollständigkeit" sidebar panel on the conversation
  detail page.

## P1-4 — Evaluation Lab quality report

- New `POST /admin/evaluation/quality-report`: real Word Error Rate
  against each conversation's own reviewed transcript (same real-audio
  approach as P0-3's Fachwortschatz comparison, ADR-0031), plus
  extraction-quality metrics (`quality_metrics`, extended with a
  `conversation_ids` scope parameter), over an **admin-explicitly-named
  sample** of already-processed conversations (1–20, never
  auto-selected — see ADR-0034 for why). Exportable as JSON/PDF/DOCX via
  the existing Document/Recap export renderer.
- Nothing persisted — computed fresh from current data on every call,
  which is what makes it reproducible (same named sample + unchanged
  data → same numbers). Conversations are identified in the report **by
  id only, never by title**, since this artifact is designed to leave
  the system (procurement, DPO, auditor).
- Frontend: new "Qualitätsbericht" tab in the Evaluation Lab admin page.

## Test / CI Summary

- Backend: `pytest -q` grew from 350 (P1-1) → 356 (P1-2, +6) → 359
  (P1-3, +3) → 365 (P1-4, +6) passed, 0 failed, throughout Stage P1.
  `ruff check .` and `mypy app` clean on every PR (188 source files by
  the end of P1-4).
- Frontend: `vitest run` → **21 passed** throughout (unchanged — no new
  Vitest suites added for the four new UI surfaces; each was verified
  via `tsc -b --noEmit`/`eslint .`/`vite build`, matching this project's
  established "admin/detail-page UI verified via typecheck/lint/build"
  precedent, Phase 12 Finding #10). Clean on every PR.
- `python compliance/check_licenses.py`: **PASS** on every PR — Stage P1
  added **zero new dependencies** (voiceprint matching, the ask
  citation-verification step, the completeness score, and the quality
  report are all pure-stdlib/reused-library logic).

## GitHub Actions

All four PRs' final commits show all 7 required checks green:

| Check | #67 (P1-1) | #68 (P1-2) | #69 (P1-3) | #70 (P1-4) |
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
merge: `docker compose build` for `backend`/`frontend` (and `migrate`
for P1-1/P1-2, which added new tables/columns — P1-3/P1-4 needed no
migration), `docker compose run --rm migrate` where applicable,
`python -m app.identity.seed` after P1-1 to pick up the new `ask:query`
permission, and a `GET /health/ready` + one targeted unauthenticated-
route spot-check (expecting `401`) after each. No exhaustive
re-verification beyond that, per `[[feedback-verification-scope]]`.

## Known Limitations / Assumptions (disclosed, not blocking)

1. **P1-1**: single-turn only, no persisted chat thread/memory.
2. **P1-2**: the 0.75 suggestion threshold is a conservative starting
   point, not calibrated against real distinct-voice data (Phase 12
   Finding #12 still applies: genuine multi-voice diarization accuracy
   has never been independently verified) — a real deployment may need
   to revisit it, and can (`app.people.matching.DEFAULT_SUGGESTION_THRESHOLD`
   is a single named constant).
3. **P1-3**: "decision rationale" is approximated by `decided_by` (who),
   not a true reasoning/justification field, which the current
   extraction schema doesn't capture — disclosed in ADR-0033 rather than
   silently reinterpreted. The score is an unweighted mean, not
   calibrated against real usage data.
4. **P1-4**: the report requires the caller to name conversations
   explicitly; there is no conversation-picker UI (an admin pastes
   ids), same disclosed limitation P0-3's vocabulary-comparison UI
   already carries. No historical report tracking exists — each report
   is a live snapshot, not stored (a deliberate choice, ADR-0034).
5. No independent security/privacy/threat-model sweep (Phase 12-style)
   was run across Stage P1's new surface area specifically — each PR's
   own authorization/scoping was tested, but a dedicated cross-cutting
   audit of the four new domains together was not performed. The
   recommendation from the P0 report stands: do one before Stage P3
   (redaction + expiring share links).

## Findings Register

No process or product-correctness finding was found in this stage — all
four PRs' first CI run passed on every check (no CI-fix-and-repush cycle
was needed, unlike Stage P0's two findings).

## Next

Stage P2 begins with **P2-1** (live transcript/live draft during
recording — chunked streaming, updated every 5–15s, final pass 30–60s
after recording stops).
