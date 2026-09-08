"""GDT (Gerätedatentransfer) document export — the second Fachsystem
export format alongside FHIR `DocumentReference` (`app.documents.
fhir_export`), added per ADR-0041 as a real, deferred option ADR-0039
explicitly left open for a future attempt with corroborated field
codes.

Pure local export, no network call, no GDT-parsing/generation library
dependency (ADR-0007) -- exactly the same "pure function, no DB/network"
shape as `fhir_export.render_fhir_document_reference`, built on the
line/record primitives in `app.documents.gdt_line_codec`.

**No real patient identity is ever claimed here either.** Field 3101
(surname) receives VocaDox's free-form `ConversationParticipant.
display_name` verbatim -- never split into a first/last name pair
VocaDox was never given (field 3102 is always omitted). Field 3103
(Geburtsdatum) has no VocaDox schema equivalent at all and is *always*
omitted -- deliberately never parsed out of the free-text `notes` field,
which would risk silently misreading an unrelated note as a date of
birth. See ADR-0041's Known Limitations for the full list of disclosed
gaps (field-code confidence, the unresolved request-side Satzart number,
the 6227-vs-6228 scope decision).
"""

from __future__ import annotations

from app.documents.gdt_line_codec import GdtCharset, encode_record

# Result/document-transmission Satzart, per the one real (secondhand,
# forum-sourced) example verified this session -- see ADR-0041.
RESULT_SATZART = "6310"

# Field 6227 (Kommentar) is documented at a maximum of 60 characters per
# line but is repeatable -- the simpler, better-corroborated mechanism
# versus field 6228's multi-line continuation-count convention, which is
# deliberately not implemented (scope decision, see ADR-0041).
_COMMENT_LINE_MAX_CHARS = 60


def _patient_fields(
    *, patient_number: str | None, patient_display_name: str | None
) -> list[tuple[str, str]]:
    """Only emits fields for data VocaDox actually holds -- mirrors
    `fhir_export`'s `if subject_display:` pattern. Never fabricates
    3102 (Vorname) or 3103 (Geburtsdatum)."""
    fields: list[tuple[str, str]] = []
    if patient_number:
        fields.append(("3000", patient_number))
    if patient_display_name:
        fields.append(("3101", patient_display_name))
    return fields


def _wrap_comment_lines(text: str) -> list[tuple[str, str]]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks = [
        normalized[i : i + _COMMENT_LINE_MAX_CHARS]
        for i in range(0, len(normalized), _COMMENT_LINE_MAX_CHARS)
    ]
    return [("6227", chunk) for chunk in chunks]


def render_gdt_text(
    *,
    patient_number: str | None,
    patient_display_name: str | None,
    rendered_text: str,
    satzart: str = RESULT_SATZART,
    charset: GdtCharset = GdtCharset.ISO8859_1,
) -> str:
    """The document's rendered text, chunked into repeated field-6227
    lines (≤60 chars each). No PDF, no external file reference -- the
    whole document travels inside the `.gdt` file itself."""
    fields = _patient_fields(
        patient_number=patient_number, patient_display_name=patient_display_name
    )
    fields.extend(_wrap_comment_lines(rendered_text))
    return encode_record(satzart, fields, charset=charset)


def render_gdt_pdf_reference(
    *,
    patient_number: str | None,
    patient_display_name: str | None,
    pdf_filename: str,
    description: str,
    satzart: str = RESULT_SATZART,
    charset: GdtCharset = GdtCharset.ISO8859_1,
) -> str:
    """References an accompanying PDF by bare filename only (field
    6305) -- VocaDox has no knowledge of the receiving practice's local
    filesystem layout; a connector that places both files together (or
    rewrites 6305 to a real absolute path) is responsible for that, see
    ADR-0041.

    Fields 6302-6305 are all required together: the one real example
    found this session shows the tested PVS software silently discards
    the whole file if any one of the four is missing, with no error
    surfaced to the user -- so this raises rather than emitting a
    partial, silently-broken record."""
    if not pdf_filename or not description:
        raise ValueError(
            "render_gdt_pdf_reference requires both pdf_filename and description -- "
            "a partial 6302-6305 file-reference block is silently discarded by at "
            "least one real PVS import, per ADR-0041"
        )
    fields = _patient_fields(
        patient_number=patient_number, patient_display_name=patient_display_name
    )
    fields.extend(
        [
            ("6302", "1"),
            ("6303", "PDF"),
            ("6304", description),
            ("6305", pdf_filename),
        ]
    )
    return encode_record(satzart, fields, charset=charset)
