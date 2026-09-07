# Phase 13 (Post-GA) — Competitive Roadmap Completion Summary

## Executive Summary

All 12 measures of the post-GA competitive roadmap
(`[[vocadox-competitive-roadmap]]`, derived from the 2026-09-07
competitor analysis) are complete: 4 stages, 16 pull requests (12
feature PRs — P2-2 split cleanly into two independently-shippable
halves — plus 4 stage validation reports), every one merged to `main`
with all 7 required CI checks green, every one deployed and spot-checked
against the real local dev stack. This work ran under a single standing
autonomous GO (`[[github-workflow-autonomy]]`) covering exactly these 12
measures — no other phase gate was affected, and the GO's own scope
boundary was itself tested once, honored, and worked exactly as
specified (see P2-2 below).

**Recommendation: GO** to resume normal phase-gated operation. This
summary is the retrospective; the four `PHASE_13_P{0,1,2,3}
_VALIDATION_REPORT.md` files remain the authoritative per-stage record.

## What shipped, by stage

**P0 — Ausschlusskriterien beseitigen** ([report](PHASE_13_P0_VALIDATION_REPORT.md)):
full-text search over transcripts/facts/documents (PR #63), DOCX/PDF/
SRT/VTT export (PR #64), org/template-scoped custom vocabulary with a
real Evaluation Lab comparison type (PR #65).

**P1 — nachbauen und dabei überholen** ([report](PHASE_13_P1_VALIDATION_REPORT.md)):
"Ask VocaDox" chat with server-enforced citation (PR #67), voiceprint
enrollment with confidence-scored (never silent) recurring-speaker
suggestions (PR #68), a template completeness score with speaking-share/
longest-monologue (PR #69), the Evaluation Lab's customer-facing quality
report (PR #70).

**P2 — Reichweite** ([report](PHASE_13_P2_VALIDATION_REPORT.md)):
live transcript/live draft during recording (PR #72), tab/screen-audio
capture staying bot-free (PR #73), calendar automation via local `.ics`
import (PR #74), a mobile PWA with an offline recording queue (PR #75).

**P3 — Enterprise** ([report](PHASE_13_P3_VALIDATION_REPORT.md)):
a real FHIR `DocumentReference` export (PR #77), fact-level redaction
with the evidence chain preserved plus expiring Recap share links
(PR #78).

## The one genuine escalation

The standing directive named five specific ESKALATION triggers and
asked to be interrupted only for them. Across all 12 measures, exactly
one was triggered: P2-2's calendar-automation half inherently needed
either a runtime network connection to an external calendar service or
an OAuth account/secret to provide genuinely live automation — both
explicit stop-and-ask conditions, in direct tension with ADR-0007's
air-gapped posture. This was escalated via `AskUserQuestion` before any
implementation began; the answer (local `.ics` import, no live sync) is
recorded in ADR-0037. Every other measure proceeded under the standing
GO with assumptions documented per-PR, exactly as instructed.

## Architecture decisions made along the way

15 new ADRs (0030–0040, plus 0032/0033/0035/0036/0037/0038 within
stages) were written as part of this roadmap, each at the point a real
design choice had to be made and documented rather than guessed
silently:

- **0030** search index dual-dialect (Postgres tsvector vs. SQLite test fallback)
- **0031** vocabulary WER measured against real audio, not the synthetic fixture
- **0032** voiceprint suggestion threshold and storage
- **0033** completeness score composition and the `decided_by`-as-rationale gap
- **0034** quality report: explicit sample, no persistence
- **0035** live transcript: whole-prefix re-transcription, not delta streaming
- **0036** system-audio capture staying bot-free by construction
- **0037** calendar automation: local import over live OAuth sync (the escalation)
- **0038** PWA: hand-written service worker + IndexedDB, no new dependency
- **0039** FHIR `DocumentReference` over GDT, and why
- **0040** fact redaction vs. `REMOVED`, and the public share-link surface

Every one of these documents a real trade-off this codebase's author
could not verify with full confidence in this environment (offline, no
access to authoritative external specs for GDT field codes; no
production usage data to calibrate voiceprint/completeness thresholds
against) — disclosed as such rather than presented as settled.

## Consolidated Findings Register

Two findings recurred with the same root cause across multiple stages,
worth naming once at the roadmap level rather than only per-stage:

1. **Local, path-scoped tool runs occasionally missed what a full-repo
   CI run caught** (a ruff line-length violation in Stage P3; an npm/
   node_modules corruption from running package managers inside a Linux
   container in Stage P0). Every instance was caught by CI itself before
   merge and fixed the same session — the safety net worked as designed,
   but it argues for running full, not path-scoped, local checks before
   every push.
2. **`compliance/dependency-inventory-transitive.yml` drifted from
   unrelated upstream package releases** twice (Stage P0's CUDA-torch
   issue, Stage P3's `optuna` version bump) — an inherent property of
   regenerating a transitive tree fresh on every CI run rather than
   diffing against a frozen baseline. Both were caught and fixed, never
   shipped.

No product-correctness defect (a wrong answer, a broken evidence chain,
a security gap in shipped code) was found in this roadmap's own review
passes. The one substantive cross-dialect bug found (SQLite-naive vs.
Postgres-aware datetime comparison in the P3-2 share-link expiry check)
was caught by the test suite itself, before merge — exactly the
mechanism designed to catch it.

## What remains open (carried forward, not resolved here)

Named honestly rather than silently dropped:

- **No independent Phase-12-style security/privacy/threat-model sweep**
  was run across the roadmap's ~20 new modules and one genuinely new
  unauthenticated surface (`app.recap.public_router`). Recommended by
  every one of the four stage reports; the clearest concrete next step
  for whoever picks up work after this roadmap.
- **GDT support** for the P3-1 Fachsystem integration remains a real,
  deferred (not rejected) option — blocked only on this environment's
  inability to verify current GDT field-code tables, not on technical
  merit (ADR-0039).
- **Voiceprint and completeness-score thresholds** (0.75 cosine
  similarity; unweighted-mean composition) are disclosed as
  conservative starting points, not calibrated against real deployment
  data (ADR-0032, ADR-0033) — worth revisiting once real usage exists.
- **PWA offline caching** is opportunistic (cache-as-you-go), not
  build-time precached; the offline recording queue has no rate/retry
  backoff tuning beyond "stop at first failure this pass" (ADR-0038).
- **Public share-link endpoint** has no rate limiting/abuse detection
  (ADR-0040) — token entropy makes brute-forcing infeasible today, but
  this is the one place in the codebase without any authentication at
  all, and deserves monitoring if real usage grows.

## Process note

This entire roadmap — 12 measures, 16 PRs, 15 ADRs, dozens of new
tests, four stage reports, one genuine escalation — ran under a single
standing autonomous GO with no per-PR check-in required, per the
directive's own explicit terms. That scope was honored precisely: every
commit landed on a feature branch, never `main`; every PR waited for all
7 CI checks before merging; the one measure that hit an ESKALATION
trigger stopped and asked rather than deciding silently; everything else
proceeded with assumptions disclosed in-PR and in ADRs, exactly as
instructed. This is not asserted as flawless execution — the Findings
Registers above are the honest record of what actually needed fixing
along the way — but the autonomy boundary itself was never exceeded.
