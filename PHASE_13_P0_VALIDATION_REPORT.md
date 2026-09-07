# Phase 13 (Post-GA) — Stage P0 Validation Report

## Executive Summary

Stage P0 of the post-GA competitive roadmap (`[[vocadox-competitive-roadmap]]`,
derived from a 2026-09-07 competitor analysis) is complete: all three
measures merged to `main`, each as its own PR, each with all 7 required
CI checks green, each deployed and spot-checked live against the real
dev stack. **Recommendation: GO** to begin Stage P1.

This is not a Phase 0-12-style hardening/audit report — Stage P0 added
real product features under a standing autonomous GO (see
`[[github-workflow-autonomy]]`), so this report documents what shipped,
how it was verified, and what remains honestly open, rather than
re-running Phase 12's full security/threat-model audit apparatus.

## Scope

Three measures, in dependency order (P0-1 before P0-2/P0-3 was not a
hard requirement; the roadmap's dependency note was P1-1 needing P0-1):

| # | Measure | PR | Merge commit |
|---|---|---|---|
| P0-1 | Full-text search over transcripts/facts/documents | [#63](https://github.com/ley338-gif/VocaDox/pull/63) | `ec34c71` |
| P0-2 | DOCX/PDF/SRT/VTT export for Document/Recap/Transcript | [#64](https://github.com/ley338-gif/VocaDox/pull/64) | `f60813d` |
| P0-3 | Custom org/template-scoped transcription vocabulary | [#65](https://github.com/ley338-gif/VocaDox/pull/65) | `8baa008` |

Each closes the tender-blocking gap the competitor analysis identified:
`Conversation.title.ilike(...)` was the *only* search that existed;
Document/Recap export was text/JSON only (Phase 5 deliberately deferred
PDF/DOCX); there was no way to bias transcription toward an
organization's own jargon.

## P0-1 — Full-text search

- New `search_entries` table: denormalized (org_id/group_id at write
  time, mirroring `follow_up_tasks`), one row per transcript segment /
  extracted fact / conversation document, org/team-scoped exactly like
  `GET /conversations`.
- Real Postgres `tsvector`/GIN (`german` config) on Postgres; a plain
  `ILIKE` fallback proves scoping/upsert/permission behavior under the
  SQLite test suite (see **ADR-0030** for why, and why pgvector was
  deferred to P1-1 rather than silently skipped).
- Index maintenance is inline at every write path (segment create/
  correct, fact create/supersede/correct/remove, document compose) —
  never a batch reindex job. Verified: re-extraction and re-composition
  never leave stale/duplicate entries (reusing #61's supersede logic).
- Frontend: a second, distinct "Inhalte durchsuchen" field on the
  conversation list, with highlighted snippets and jump-to-source
  (a transcript hit scrolls to and highlights the exact segment).

## P0-2 — Export formats

- `app.documents.export_formats` (shared by Document and Recap export):
  DOCX via `python-docx` (MIT), PDF via `reportlab` (BSD-3-Clause) —
  both pure-Python, no native dependency, no network call. Approval
  status and revision number are visible in every DOCX/PDF export.
- `app.transcription.subtitles`: SRT/VTT, no new dependency — pure
  string formatting from the same `start_ms`/`end_ms` every other
  transcript export format already uses.
- Existing plain-text exports are byte-for-byte unchanged (existing
  tests assert exact content) — the new formats carry the new
  visibility requirement, old ones were never touched.
- Compliance: two new direct dependencies recorded and verified
  (`compliance/dependency-inventory.yml`); the full transitive tree was
  regenerated against real Linux containers using CI's own recipe,
  including the AI worker's `[ai]` extra with the CPU-only torch index
  — the first regeneration attempt used the default CUDA-bundled torch
  and pulled in NVIDIA proprietary packages (`blocked`/`unknown`),
  caught locally and corrected before ever reaching CI.

## P0-3 — Custom transcription vocabulary

- New `app.vocabulary` domain: org-scoped, optionally template-scoped
  `VocabularyEntry` rows (hotwords + an `initial_prompt`), managed in
  the Admin Portal. Resolution reuses the conversation's already-
  resolved effective Template (`app.profiles.resolver
  .resolve_effective_config`) rather than a new, parallel "which
  template" mechanism, per the roadmap's own instruction.
- `SpeechToTextProvider.transcribe()` gained `hotwords`/`initial_prompt`
  parameters, threaded straight through to faster-whisper's own
  same-named parameters. `FakeSpeechProvider` accepts but ignores them
  — stays fully deterministic for CI, per the roadmap's explicit
  requirement.
- Evaluation Lab gained a third comparison type,
  `vocabulary_comparison`: real Word Error Rate (`app.analytics.wer`,
  pure stdlib Levenshtein distance) on a real, already-reviewed
  conversation's own audio, with vs. without the resolved vocabulary
  applied. See **ADR-0031** for why this reuses a real conversation's
  audio/ground-truth transcript instead of a new bundled fixture —
  every other Evaluation Lab comparison type is text-only, so this is
  genuinely new infrastructure, kept intentionally narrow.

## Tests

- Backend: `pytest -q` → **346 passed** (up from 327 at the start of
  Stage P0: +8 P0-1, +2 P0-2, +9 P0-3), 0 failed. `ruff check .` and
  `mypy app` clean throughout (176 source files by the end of P0-3).
- Frontend: `vitest run` → **21 passed** (unchanged — no new frontend
  unit tests were added; new UI was verified via `tsc`/`eslint`/
  `vite build` plus a live browser check for P0-1's search UI, matching
  this project's existing "admin surfaces verified via typecheck/lint/
  build, not always a Vitest suite" precedent, see Phase 12 Finding
  #10). `tsc -b --noEmit` and `eslint .` clean on every PR.
- `python compliance/check_licenses.py`: **PASS** on every PR (0
  blocked/0 unknown). P0-1 and P0-3 added zero new dependencies; P0-2's
  two new dependencies are both `approved`-bucket, verified against the
  PyPI JSON API per this project's standing convention.

## GitHub Actions

All three PRs' final commits show all 7 required checks green:

| Check | #63 (P0-1) | #64 (P0-2) | #65 (P0-3) |
|---|---|---|---|
| Backend (lint/typecheck/test) | PASS | PASS | PASS |
| Frontend (lint/typecheck/test/build) | PASS | PASS | PASS |
| Alembic migration (real Postgres) | PASS | PASS | PASS |
| OpenAPI TS client drift check | PASS | PASS | PASS |
| License compliance | PASS | PASS | PASS |
| Docker build | PASS | PASS | PASS |
| Container vulnerability scan (Trivy) | PASS | PASS | PASS |

## Live Deployment

Each PR was deployed to the real local dev stack immediately after
merge: `docker compose build` for every affected image (`backend`,
`frontend`, `migrate`, and — for P0-2/P0-3, which touch code paths the
worker images also import — `worker-extraction`/`worker-speech`/
`worker-diarization`), `docker compose run --rm migrate` for P0-1's and
P0-3's new tables, `python -m app.identity.seed` after P0-3 to pick up
the two new `vocabulary:*` permissions, and a `GET /health/ready` +
one targeted unauthenticated-route spot-check (expecting `401`, proving
the new route is live and not 500ing) after each. No exhaustive
re-verification beyond that was performed once CI was green, per this
session's own established practice (`[[feedback-verification-scope]]`).

## Known Limitations / Assumptions (disclosed, not blocking)

1. **P0-1**: pgvector/semantic search deferred to P1-1 (ADR-0030) —
   this was a confirmed design decision, not an oversight.
2. **P0-2**: no new frontend automated tests for the new export
   buttons; verified manually via the build + the existing pattern of
   trusting backend format/content-type/magic-byte tests as the
   authoritative check.
3. **P0-3**: the `vocabulary_comparison` Evaluation Lab run type
   requires an admin to already have a conversation with both a
   reviewed transcript and a configured vocabulary entry — it cannot
   demonstrate anything standalone like the other two comparison types,
   and it is meaningless against the `fake` speech provider (by
   design — see ADR-0031). No conversation-picker UI was built for it;
   the admin pastes a conversation id directly.
4. No independent security/privacy/threat-model sweep (Phase 12-style)
   was run across Stage P0's new surface area specifically — each PR's
   own authorization/scoping was tested (org/team isolation, permission
   enforcement, cross-organization 403/404), but a dedicated
   cross-cutting audit of the three new domains together was not
   performed. Recommend one before Stage P3 (which adds redaction and
   expiring share links — a natural point to also re-sweep P0-P2's
   surface).

## Findings Register

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Local Windows npm environment was corrupted mid-session by running `npm ci` inside a Linux Docker container against a bind-mounted `frontend/` directory (needed to regenerate `compliance/dependency-inventory-transitive.yml` on Linux, per that file's own documented requirement) — native binaries got overwritten with Linux builds, breaking `openapi-typescript` locally | P3 (process, not product) | **Fixed same session** — `rm -rf node_modules && npm install` restored it; no committed artifact was affected |
| 2 | First attempt at regenerating P0-2's transitive dependency inventory used the default (CUDA-bundled) torch wheel instead of the CPU-only index the real worker image installs from, surfacing 17 NVIDIA-proprietary `blocked`/`unknown` transitive packages | P2 (would have failed CI if pushed) | **Caught and fixed locally before push** — regenerated using the exact `--extra-index-url https://download.pytorch.org/whl/cpu` recipe `.github/workflows/ci.yml` itself uses |

No P0/P1 product-correctness finding was found in this stage.

## Next

Stage P1 begins with **P1-1** ("Ask VocaDox" — chat over conversation
history with enforced citation, discarding any answer without a real
`ExtractedFact` evidence anchor), which the roadmap's own dependency
note identifies as needing P0-1's search index — now in place.
