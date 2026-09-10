# 0041 — GDT export formats (PDF-reference + embedded text) and a connector prototype

## Status
Accepted (2026-09-09). Post-GA, organic follow-up to P3-1 (ADR-0039).

## Context

ADR-0039 chose FHIR `DocumentReference` over GDT as VocaDox's one real
Fachsystem export, specifically because GDT's field codes (Feldkennungen)
could not be verified against an authoritative source in that working
environment — not because GDT was technically inferior. Its Consequences
section explicitly left the door open: "GDT support remains a real,
deferred option ... a future implementation with access to a current,
authoritative GDT field-code reference ... would be well-positioned to
add it as a second export format alongside this one."

This work is that attempt, prompted by a concrete customer need
(Patientendaten aus dem PVS holen, fertiges Dokument zurückspielen) that
came up in conversation, not a fresh field-code lookup against the
primary GDT specification (the spec PDF still can't be rendered in this
environment — `pdftoppm`/poppler is unavailable here, exactly the same
limitation ADR-0039 hit). What changed is corroboration: this session
found a real, working GDT+PDF-import example on a practice-software
user forum (indamed/Medical Office), independently cross-checked against
a second source (PADSY's GDT FAQ), and verified the length-prefix
encoding arithmetically against that example's own field lines. That is
a narrower, secondhand form of verification than ADR-0039 was holding
out for, and is disclosed as such below rather than presented as
spec-grade confidence.

The owner explicitly asked for both export variants (PDF-reference and
embedded-text) *and* a connector prototype — not just the backend export
half — after discussing the GDT round-trip (patient data in, document
out) and the practical GDT mechanisms for each direction.

## Decision

**Built now:**

1. Two new document export formats, `gdt-pdf` and `gdt-text`, alongside
   the existing `text`/`json`/`docx`/`pdf`/`fhir` formats, via the same
   `GET .../document/export?format=...` endpoint
   (`app.documents.export_service.render_document_export`, extracted
   from the endpoint that used to hold this dispatch inline — a
   refactor with no behavior change for pre-existing formats, covered by
   the pre-existing test suite staying green).
   - `gdt-pdf`: the existing PDF renderer's output, bundled in a ZIP
     with a `.gdt` file referencing it by bare filename (fields
     6302-6305).
   - `gdt-text`: the document's rendered text, chunked into repeated
     field-6227 lines, with no PDF at all.
2. A pure, independently-tested low-level codec
   (`app.documents.gdt_line_codec`) and format renderers
   (`app.documents.gdt_export`), mirroring `fhir_export.py`'s "no DB, no
   network" shape.
3. Two new Integration API routes (`app.integrations.router`) that were
   simply missing before this work, found while designing the
   connector: `GET .../document/export` (service-account equivalent of
   the human export route — there was previously no non-human-session
   way to download export bytes at all) and
   `POST .../conversations/{id}/participants` (equally missing;
   confirmed, by reading both the service function and the human route,
   that neither requires owner attribution — unlike conversation/
   document writes).
4. A standalone connector prototype, `connectors/gdt-bridge/` — a
   separate Python package, never a dependency of `backend/`, matching
   `future-considerations.md`'s "never runs inside the VocaDox backend
   process" rule for any Fachsystem adapter. Watches a local import
   folder for an inbound GDT file, creates a conversation + PATIENT
   participant via the Integration API, polls for document approval,
   then exports and writes the result (PDF+GDT or text-only GDT) to a
   local export folder with field 6305 rewritten to a real path.

**Deliberately not built / left open:**

- No claim of GDT 2.1/3.0 spec conformance — see Known Limitations.
- The request-side (PVS → VocaDox) Satzart number is unresolved; the
  connector's inbound parser is satzart-agnostic/configurable rather
  than hardcoded to a guess.
- Field 6228's multi-line continuation convention — only the simpler
  6227 repeated-line mechanism is implemented.
- No real PVS has validated any of this end-to-end; the connector is a
  prototype, not a certified integration.

## Consequences

- No new backend dependency, no new network call from the backend
  itself (`gdt-pdf`/`gdt-text` are pure local exports, like `fhir`) —
  consistent with ADR-0007.
- The connector prototype does add two new dependencies, but scoped
  entirely to `connectors/gdt-bridge/`'s own `pyproject.toml`, never
  touching `backend/`'s dependency tree: `httpx` (already used
  elsewhere in this codebase, just not previously as an external-caller
  library) and `watchdog` (genuinely new, Apache-2.0-licensed — verified
  live against https://pypi.org/pypi/watchdog/json, not assumed — for
  folder watching; no folder-watching library existed anywhere in this
  repo before).
- Two pre-existing documentation files were already stale independent
  of this work (`docs/architecture/documents.md`'s Export section still
  claimed PDF/DOCX were "deliberately deferred"; `backend/app/documents/
  README.md` still said "Status: placeholder — not implemented in Phase
  0") — corrected alongside this change rather than left further out of
  date.

### Known Limitations (disclosed, not silently glossed over)

1. **Field-code confidence is moderate, not spec-grade.** Corroborated
   across two independent secondhand sources (an indamed/Medical Office
   forum thread with a real working GDT+PDF example, and PADSY's GDT
   FAQ), not checked against the primary GDT specification PDF (still
   unrenderable in this environment). The per-field length-prefix
   formula (`3 + 4 + len(content) + 2`) is now *arithmetically verified*
   against three exact real field lines from that forum example (fields
   6302/6303/6304 match `010`/`012`/`015` exactly) — a genuine
   improvement over ADR-0039's fully-unverified state. The `8000`/`8100`
   record-wrapper's own total-length semantics remain inferred by
   structural analogy to header lines seen *alongside* (not fully
   within) that one example, not independently confirmed against a
   complete real record.
2. **Request-side Satzart number is unresolved.** Sources found this
   session conflict on whether a PVS's outbound "new patient/
   examination" request uses Satzart 6301 or 6302. The connector does
   not guess — its inbound parser is designed to be satzart-agnostic/
   configurable rather than hardcoded.
3. **No date-of-birth field anywhere in VocaDox.**
   `ConversationParticipant` has no DOB column. Field 3103 (Geburtsdatum)
   is *always* omitted from every GDT export — deliberately never
   parsed out of the free-text `notes` field, which would risk silently
   misreading an unrelated note as a date of birth in a medical-
   documentation-adjacent context. A future real requirement would need
   an actual `date_of_birth` column via migration, not a notes-parsing
   heuristic.
4. **`display_name` is never split into first/last name.** VocaDox's
   participant name is one free-form string (by design — see
   `ConversationParticipant`'s own docstring: real names are never
   required). The whole value goes into field 3101 (Nachname); field
   3102 (Vorname) is always omitted rather than heuristically guessed.
5. **Charset value "3" is treated as Windows-1252, not strict
   ISO-8859-1.** One source found this session labels field-9206 value
   "3" as "ISO8859-1(ANSI) CP 1252" — a single combined label. The two
   encodings are not identical (Windows-1252 assigns printable
   characters — e.g. the em dash U+2014 — to the 0x80-0x9F range that
   strict ISO-8859-1 leaves undefined), but real German documentation
   text routinely contains exactly that Windows-1252-only punctuation,
   and a strict-ISO-8859-1 encoder crashes on ordinary prose (found via
   this work's own test suite). CP1252 is used as the practical
   interpretation, at the cost of not being byte-identical to a strict
   ISO-8859-1 implementation on the few codepoints where they actually
   differ. Text using characters outside Windows-1252 entirely (e.g.
   non-Latin scripts) will still fail to export via `gdt-text`/`gdt-pdf`
   — GDT is fundamentally an 8-bit-per-character legacy format with no
   good answer for that case, and this raises rather than silently
   corrupting content.
6. **Poll, not webhook, for approval detection.** The connector is
   expected to run on/near a practice PC, typically behind NAT with no
   inbound reachability from VocaDox's backend — a poll loop (default
   15s, backoff to 300s) is far more deployable there than requiring an
   inbound webhook, even though webhook-push is the pattern
   `future-considerations.md` describes for the four originally-deferred
   adapters. That documented pattern assumed a connector running
   somewhere reachable; this one doesn't.
7. **ZIP-bundling the `gdt-pdf` variant** (one download containing both
   the PDF and its referencing `.gdt` file) is a judgment call over
   alternatives (two separate calls, a multipart response) — chosen to
   keep the export contract identical in shape to every other format
   (one `GET`, one file).
8. **The GDT codec is duplicated** between `backend/app/documents/
   gdt_line_codec.py` and `connectors/gdt-bridge/gdt_bridge/gdt_codec.py`
   by architectural necessity (the connector must never depend on the
   backend package). A future shared micro-package could remove this,
   but that's premature for a prototype with only one consumer on each
   side.
9. **No registered IANA media type for GDT.** `application/octet-stream`
   (`gdt-text`) and `application/zip` (`gdt-pdf`'s bundle) are pragmatic
   choices, not standards.
10. **Field 6302-6305 are all-or-nothing by design, enforced with a
    hard error, not a silent partial write.** The one real example found
    this session came from a user reporting exactly this failure mode:
    the tested PVS (Medical Office) silently discards a GDT file if any
    one of these four fields is missing, with no error surfaced to the
    practice. `render_gdt_pdf_reference` raises rather than emitting a
    partial block, so a bug here fails loudly during development instead
    of silently at a real practice.

### Phase 14 security addendum (2026-09-10)

The bridge treats both watched files and API export payloads as hostile. Remote
API endpoints require HTTPS (loopback HTTP remains a development exception),
inbound files are capped at 1 MiB and must resolve to a regular file directly
inside the configured import directory, and output names must be control-free
basenames with the expected suffix. A PDF bundle contains exactly one PDF and one
GDT member and is rejected on traversal names, encryption, excessive compressed
or expanded size, or a compression ratio above the configured safety bound.
These checks intentionally live in the standalone connector as well as backend
export validation because the trust boundary is the downloaded byte stream.
