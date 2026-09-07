# Vollständigkeit (completeness score)

## What this shows

Every conversation's detail page has a "Vollständigkeit" panel in the
sidebar, once at least one processing run has happened. It answers three
questions, purely from data already on the conversation — it never
generates or claims anything new:

1. **Category coverage** — does the conversation have at least one fact
   in every category its resolved Template defines? (e.g. the "General
   Conversation" template asks for General Facts, Decisions, and Tasks —
   a checkmark next to each shows at least one was found, an empty
   outline means none was.)
2. **Decision/task completeness** — for every recorded Decision, was a
   decision-maker named? For every recorded Task, was an owner named?
   Both are only shown if such facts exist at all — a conversation with
   no decisions isn't flagged for missing something it never had.
3. **Speaking share and longest monologue** — from the same diarization
   that produced the conversation's detected speakers: roughly what
   share of the conversation each speaker held, and who held the floor
   longest without interruption.

## What the score is not

- **Not a quality judgment on the conversation itself.** A short check-in
  call with nothing to decide will show 0% coverage on "Decisions" —
  that's accurate, not a problem to fix.
- **Not part of the generated Document.** Nothing here is exported,
  cited, or treated as AI Evidence — it's a live indicator for you,
  computed fresh every time the panel loads.
- **Not exact.** "Longest monologue" merges nearby speaking turns from
  the same detected speaker with a short pause tolerance — a reasonable
  approximation, not a formally verified measurement (see
  `docs/architecture/adr/0033-completeness-score-composition.md`).

## Why a category might show as "missing"

- No extraction has run yet (process the conversation's audio first).
- The conversation genuinely didn't cover that category — nothing to
  fix.
- A human reviewer removed every fact in that category during review
  (Review Wizard) — this reflects that decision, since a removed fact is
  correctly treated as "not really there."
