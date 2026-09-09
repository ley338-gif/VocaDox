# ADR-0042: Protokoll — a structured, LLM-generated conversation protocol

## Status

Accepted (MVP scope — see "Deferred" below).

## Context

VocaDox's conversation detail page had Übersicht/Transkript/Fakten/Dokumentation/Review/Aufgaben/Recap/Audio. None of these show *what happened in the conversation* as a scannable, chronological structure:

- **Transkript** is verbatim, timestamped, source-of-truth — not scannable for a long conversation.
- **Fakten** is flat extracted data (general_fact/decision/task or a template's own categories) — not chronological, no narrative.
- **Dokumentation** is a *formal* generated document: deterministic composition (`app.documents.service.compose_document`, spec's explicitly-rejected-elsewhere "LLM writes a report" architecture never applies there), no free prose summary, and it's the artifact meant for export/sharing — not a working view.

The owner asked for a new **Protokoll** tab: a compact, timeline-based protocol (sections, important points, decisions, open questions, action items), fully traceable back to the transcript, visually native to VocaDox, between Fakten and Dokumentation. It must not replace Dokumentation and must not become a second, disconnected task/marker system.

## Decision

### Generation is LLM-driven and async, unlike Document composition

Document composition is deterministic (spec §23's rejected "write a report" architecture) and therefore correctly runs synchronously in the request handler (ADR-0027). A protocol is inherently a *generated summary* — narrative, judgment calls about what's a "decision" vs a "note" — so it genuinely needs an LLM call, and per every other provider-backed stage in this codebase (Phase 3 speech/diarization, Phase 4 extraction), that means the async `ProcessingJob`/worker pipeline, never inline in a request handler.

### One structured call per generation, not a multi-stage pipeline

A more accurate design would run topic segmentation, then section classification, then per-section summarization, then fact/decision/action-item extraction, then source mapping, as separate stages. VocaDox has no existing multi-turn-pipeline infrastructure, and building one safely is real, separate scope. Phase 4's own extraction is already "one structured call per category" (`app.intelligence.service._extract_category`) — this reuses that same shape at the level of "one call producing the whole section+item tree," via `LLMProvider.complete_structured()` against `app.protocols.schemas.ProtocolGenerationResult`.

### Source traceability mirrors Phase 4's evidence-fabrication guard exactly

The prompt requires every section and item to cite transcript segment `sequence` numbers (`app.transcription.rendering.render_transcript`'s `[SEG n]` numbering — the same mechanism Phase 4 extraction already uses). `app.protocols.service.run_protocol_generation` resolves each claimed sequence against a real `TranscriptSegment` of *this* transcript and silently drops anything that doesn't resolve — a hallucinated citation is never trusted, never surfaced as if it were real evidence (`ProtocolSource`, mirroring `app.evidence.models.FactEvidence`).

### Reuses the extraction worker/queue

`JobType.GENERATE_PROTOCOL` rides on the same `worker-extraction` process and queue topology as `JobType.EXTRACT` (`app.processing.queues.EXTRACTION_WORKER_JOB_TYPES`) — it's the same kind of LLM work with the same resource profile; a dedicated worker service for one more job type was judged unwarranted scope.

### No coupling to `Conversation.status`

Extraction's trigger transitions the conversation to `EXTRACTING` and back to `READY` — it's part of the primary processing pipeline gate. Protocol generation deliberately never touches `Conversation.status`: it's an optional, repeatable side-view of an already-READY conversation, re-triggerable any time, not a pipeline stage. Progress is tracked purely via the `ProcessingJob`'s own status.

### Immutable revisions, `Protocol`/`ProtocolRevision` mirroring `Document`/`DocumentRevision`

Every "Neu erstellen" click creates a **new** `ProtocolRevision`; nothing is ever mutated or deleted. Unlike `DocumentRevision.structured_content` (one JSON blob — acceptable there since Documents are never edited section-by-section), `ProtocolSection`/`ProtocolItem` are normalized child rows, because the (deferred, but planned) manual-editing feature needs row-level PATCH targets. `manually_edited` columns ship now, unused, so that follow-up work is additive rather than another migration that reshapes this table.

A `ProtocolRevision` row is only ever created *after* a successfully validated LLM response — there is no "pending" row written before the call (mirrors `run_extraction` only ever creating `ExtractedFact` rows post-validation). A client polling "is generation in progress" reads the `ProcessingJob` status, not a `Protocol`/`ProtocolRevision` row.

### No new ModelProfile purpose / Template Engine integration

Protocol generation reuses the existing `ModelProfilePurpose.EXTRACTION` profile. A dedicated "protocol" model purpose (with its own admin UI) and template-driven prompting are both real scope beyond what was asked; one well-crafted system prompt (`app.protocols.prompts`) covers every conversation type via the LLM's own judgment about which of the generic `ProtocolSectionType`/`ProtocolItemType` values actually fit.

### `responsible_label` is free text, not a `Participant` FK

Matches how Phase 4's own `task`/`decision` categories already model "who" (`assignee`/`decided_by` in `ExtractedFact.structured_value`) as free text copied from a speaker label — the LLM only ever has a speaker label to go on, never a resolved `Participant` identity.

## Deferred (explicitly, to a follow-up PR)

Every item below is additive on top of the shape described above — nothing here needs to change to support them later:

- Manual editing of sections/items (title/summary/text/ordering) and the "don't silently overwrite a manual edit on regenerate" logic that only matters once edits exist.
- Revision *browsing* UI ("Versionen" list/detail) — the `GET .../protocol/revisions` endpoint ships now; only the UI is deferred.
- "Als Aufgabe übernehmen" (`ProtocolItem` → real `FollowUpTask`) linking.
- Section split/merge, "aus Protokoll ausblenden".
- Marker icons inline in the timeline.

## Consequences

- Two new permissions, `protocol:read`/`protocol:generate`, granted to the same roles as `fact:read`/`fact:extract` (Manager/User get generate+read, Reviewer/Auditor get read-only) — mirrors the existing extraction permission shape rather than inventing a new grant pattern.
- `app.transcription.rendering` is a new shared module, extracted from `app.intelligence.service` (which owned the speaker-labeling/transcript-rendering helpers first, Phase 4) once Protokoll needed the exact same "speaker-labeled transcript text for a prompt" logic — a pure refactor, behavior-preserving (existing extraction tests cover it unchanged).
