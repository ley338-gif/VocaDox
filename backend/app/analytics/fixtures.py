"""Synthetic Evaluation Lab fixture (Phase 8, spec §50).

No existing Phase 3/4 fixture covers what the Evaluation Lab needs: Phase
3's `tests/fixtures/audio/german_multispeaker_conversation.*` is an
ASR/diarization fixture (audio + a gold *transcript*, no facts/decisions/
tasks/contradiction it's meant to exercise). Phase 4's extraction tests
build ad-hoc transcripts inline per test rather than a shared, documented,
"gold facts" fixture. This is therefore a genuine gap (per the phase
brief), not a case of reinventing something that already exists — so one
small, new, honestly-documented fixture is added here.

**Provenance**: entirely synthetic, hand-authored for this phase,
German-language (matching the product's primary market and Phase 3's own
fixture language), modeled directly on the spec's own Ramipril
illustration (`docs/architecture/domain-model.md`'s "Source -> Facts ->
Document provenance" section) plus a deliberate self-contradiction (a
dose correction) so contradiction detection has something real to find.
No real person, patient, or organization is referenced. Never audio — the
Evaluation Lab measures the *extraction* pipeline (transcript segments ->
structured facts), not speech-to-text, so plain text segments are
sufficient and avoid re-doing Phase 3's already-covered ASR evaluation.

`GOLD_EXPECTED` is a deliberately loose, human-auditable description of
what a correct extraction should find — matched leniently (case-insensitive
substring matching, see app.analytics.eval_engine) against whatever a real
model actually returns, because two genuinely different models will not
phrase field values identically even when both are "correct". This fixture
is evaluation-only: it is never written to `extracted_facts`/`documents`,
and nothing here is ever used to fine-tune/train a model (see process rule
7 in the phase brief / spec §38).
"""

from __future__ import annotations

from dataclasses import dataclass

FIXTURE_KEY = "consultation_ramipril_v1"

# (sequence, text) pairs, mirroring app.intelligence.prompts.render_transcript's
# [SEG n] convention.
SEGMENTS: list[tuple[int, str]] = [
    (1, "Guten Tag Herr Mueller, ich bin Dr. Weber, schoen dass Sie da sind."),
    (2, "Ich verschreibe Ihnen Ramipril, fuenf Milligramm, einmal taeglich."),
    (
        3,
        "Wir haben entschieden, die Dosis in einem Monat zu ueberpruefen, "
        "abhaengig vom Blutdruck.",
    ),
    (
        4,
        "Herr Mueller, bitte vereinbaren Sie naechste Woche einen Termin fuer "
        "eine Blutuntersuchung.",
    ),
    (
        5,
        "Eine Korrektur zu vorhin: das Ramipril ist tatsaechlich zehn Milligramm, "
        "nicht fuenf.",
    ),
    (6, "Haben Sie noch Fragen dazu?"),
]


@dataclass(frozen=True, slots=True)
class GoldGeneralFact:
    subject_contains: str
    value_contains: str


@dataclass(frozen=True, slots=True)
class GoldDecision:
    description_contains: str


@dataclass(frozen=True, slots=True)
class GoldTask:
    description_contains: str
    assignee_contains: str


# What a correct extraction over SEGMENTS should find. Two GENERAL_FACT
# items sharing (subject="Ramipril", attribute="dose") with different
# values (5mg vs 10mg) is the deliberate self-contradiction (spec §26
# contradiction detection) — segment 5 is a real, in-transcript correction
# of segment 2, exactly the "conflicting values for the same
# subject/attribute" shape app.intelligence.contradictions.detect_contradictions
# looks for.
GOLD_GENERAL_FACTS: list[GoldGeneralFact] = [
    GoldGeneralFact(subject_contains="ramipril", value_contains="5"),
    GoldGeneralFact(subject_contains="ramipril", value_contains="10"),
]
GOLD_DECISIONS: list[GoldDecision] = [
    GoldDecision(description_contains="dosis"),
]
GOLD_TASKS: list[GoldTask] = [
    GoldTask(description_contains="blutuntersuchung", assignee_contains="mueller"),
]
GOLD_CONTRADICTIONS_EXPECTED = 1

GOLD_TOTAL_ITEMS = len(GOLD_GENERAL_FACTS) + len(GOLD_DECISIONS) + len(GOLD_TASKS)
