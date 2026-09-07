# 0031 — Vocabulary Evaluation Lab comparison uses a real conversation's own audio, not a bundled fixture

## Status
Accepted (2026-09-07). Post-GA, roadmap item P0-3.

## Context

P0-3 (custom transcription vocabulary/hotwords) needed its effect to be
"messbar" (measurable) in the Evaluation Lab, per the roadmap. Every
existing Evaluation Lab comparison type (`model_comparison`,
`prompt_comparison`) runs the SAME synthetic, bundled text fixture
(`app.analytics.fixtures`) through two LLM-extraction subjects — no
audio, no speech-to-text step, at all. Vocabulary/hotwords only affect
ASR (speech-to-text) decoding, never text-based fact extraction, so
there is no way to measure their effect by reusing that existing
text-only fixture.

A real measurement needs: real audio, a real reference (ground-truth)
transcript to compute Word Error Rate against, and a real
`SpeechToTextProvider` call. Two options were considered:

1. **Bundle a new synthetic audio fixture** (a short recorded or
   synthesized clip + a hand-written gold transcript), mirroring how
   `app.analytics.fixtures` bundles a synthetic text transcript today.
2. **Reuse an existing, already-reviewed real conversation** — its
   normalized audio (already on disk) and its human-corrected transcript
   segments (`TranscriptSegment.corrected_text`, already the product of
   the existing Review workflow) as ground truth.

## Decision

Option 2. `app.analytics.service.run_vocabulary_comparison` takes a
`conversation_id`, requires that conversation to already have an active,
READY transcript, and re-runs the real, already-configured speech
provider on its own normalized audio twice (once with no vocabulary,
once with the resolved one) — comparing each hypothesis to the
conversation's own corrected segment text via a real Levenshtein-
distance Word Error Rate (`app.analytics.wer`, pure stdlib, no new
dependency).

**Why not a bundled fixture:** a synthetic audio clip would need to be
recorded/synthesized, licensed, and maintained, and — critically —
wouldn't contain the SAME domain-specific terms a given customer's real
vocabulary is actually meant to help with. A generic bundled fixture
proves the mechanism works but not whether a specific organization's
glossary actually helps; reusing a real, already-reviewed conversation
proves the latter directly, with zero new assets to maintain.

**Consequence, disclosed honestly:** this comparison type requires the
admin to already have at least one conversation with a reviewed
transcript and a configured vocabulary entry — it cannot run standalone
like the other two comparison types, and it is meaningless against the
`fake` speech provider (CI/dev-without-a-model) since `FakeSpeechProvider`
ignores hotwords entirely by design (P0-3's own requirement: "der
fake-Provider bleibt deterministisch"). CI still exercises the full
mechanism end-to-end (wiring, WER computation, persistence, HTTP
surface) — it just can't demonstrate a real accuracy improvement,
exactly like the model/prompt comparison tests already disclose for
their own `fake` LLM provider.
