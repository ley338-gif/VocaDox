# 0034 — Quality report: explicit sample, no persistence, id-only identification

## Status
Accepted (2026-09-07). Post-GA, roadmap item P1-4.

## Context

The roadmap asks for an "exportierbarer, reproduzierbarer Bericht" over
Word Error Rate and extraction quality, suitable for procurement, a
Datenschutzbeauftragter, or EU AI Act documentation. Three design
questions: (1) how the sample of conversations to measure is chosen,
(2) whether the report needs its own persisted table (like
`EvaluationRun`), and (3) how conversations are identified inside a
document meant to leave the system and reach third parties.

## Decision

**1. The admin explicitly lists which conversations to include —
nothing is auto-selected.** An alternative design (e.g. "the 20 most
recently reviewed conversations") was considered and rejected: silently
picking the sample makes the report's honesty depend on trusting that
the selection logic wasn't tuned to look favorable, and any future
change to that logic would silently change what past reports meant. An
explicit list means the exact same input always reproduces the exact
same report, and the report itself can (and does, via its
`conversation_ids`-scoped metrics) show precisely what was measured —
nothing hidden behind an auto-selection heuristic. The admin bears
responsibility for choosing a representative sample, same as they
already do when picking which conversation to run the Fachwortschatz
comparison against.

**2. No new table — the report is computed fresh from current data on
every call, never persisted as an `EvaluationRun`.** `EvaluationRun`
exists to let a two-subject *comparison* be inspected again later
without re-running it (its `result_a`/`result_b` are the historical
record of what that specific run measured at that time). This report is
different in kind: it's a live, publishable snapshot of *current* data
quality, not a comparison whose historical value depends on being
frozen. "Reproducible" here means "the same named sample, run again
against unchanged underlying data, gives the same numbers" — a property
that holds without persistence, and persisting a WER-per-conversation
table would mean deciding a retention policy for exactly the kind of
audio-derived measurement ADR-0007 (air-gapped, minimal retained
artifacts) already pushes against without a concrete need.

**3. Conversations are identified in the report by id only — never by
title.** Every other analytics/Evaluation Lab response in this module is
already structurally counts/ids/labels only, verified by
`tests/analytics/test_privacy.py`'s exact-key-set assertions. This
report is explicitly designed to leave the system (procurement, a DPO,
an auditor) as a PDF/DOCX — exactly the context where a conversation
title (which can itself be identifying or sensitive, e.g. naming a
patient or topic) must not appear. An id-only reference matches the
same posture the Evaluation Lab already applies to its comparison
subjects.

## Consequences

- No new migration, no new retention decision to make.
- A report with an empty or fully-skipped sample shows `null`/zero
  metrics rather than silently falling back to organization-wide numbers
  — `app.analytics.service.quality_metrics(db, conversation_ids=[])`
  deliberately returns "no data for this scope", not "unscoped global
  data", the moment a caller passes an explicit (even empty) list.
- If a future need arises for historical report tracking (e.g. "show me
  last quarter's report"), that is a genuinely new requirement (audit
  trail of what was reported when) distinct from "reproduce this report
  right now" — it should get its own explicit design rather than being
  retrofitted onto this live-computation approach.
