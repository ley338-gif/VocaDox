# `app/documents/`

**Status: implemented** (Phase 5, extended in Phase 6, post-GA P0-2/P3-1/ADR-0041).

Document composition, non-destructive revisions, the Review Wizard
(review-issue resolution), human-only approval, and export. See
`docs/architecture/documents.md` for the full picture; this file is a
code map.

- `models.py` — `Document`, `DocumentRevision` (`DRAFT` →
  `REVIEW_REQUIRED`/`READY_FOR_APPROVAL` → `APPROVED`, database-enforced
  immutability once `APPROVED`).
- `service.py` — `compose_document` (deterministic, template-driven,
  never an LLM call), `approve_document` (human-only, blocked by open
  HIGH/CRITICAL review issues), `resolve_review_issue`.
- `router.py` — `/conversations/{id}/document`, `/document/compose`,
  `/document/revisions`, `/document/approve`, `/document/export`.
- `export_service.py` — the shared per-format export dispatch
  (`text`/`json`/`docx`/`pdf`/`fhir`/`gdt-pdf`/`gdt-text`), used by both
  the human router above and the Integration API's equivalent route in
  `app.integrations.router`.
- `export_formats.py` — DOCX/PDF rendering (post-GA P0-2), shared with
  `app.recap`.
- `fhir_export.py` — FHIR R4 `DocumentReference` export (post-GA P3-1,
  ADR-0039).
- `gdt_export.py` / `gdt_line_codec.py` — GDT export formats and their
  low-level line/record codec (post-GA, ADR-0041).
