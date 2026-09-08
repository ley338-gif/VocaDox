"""Low-level GDT (Gerätedatentransfer) line/record encoding — the
fixed-width text format used by German medical-practice software (PVS)
to exchange data with external systems (see ADR-0041 for why this is
being added now, and docs/architecture/adr/0039-fhir-documentreference-
over-gdt.md for why it was previously deferred).

**Confidence level, disclosed explicitly**: the length-prefix formula
below (`3 + 4 + len(content) + 2`) is verified by direct arithmetic
against four real field-level lines quoted in ADR-0041 (found in a
practice-software user forum thread demonstrating a working GDT+PDF
import), not against the primary GDT specification PDF (which could not
be rendered in this working environment — `pdftoppm`/poppler is
unavailable here). The `8000`/`8100` record-wrapper semantics in
`encode_record` are inferred by structural analogy to that same
excerpt's header lines, not independently confirmed against one
complete real record. This module must not be treated as a verified GDT
2.1/3.0 conformance implementation — see ADR-0041's Known Limitations.

Pure functions only: no DB access, no network, no filesystem I/O.
"""

from __future__ import annotations

from enum import StrEnum

_LENGTH_FIELD_WIDTH = 3
_FELDKENNUNG_WIDTH = 4
_LINE_TERMINATOR = "\r\n"
_LENGTH_OVERHEAD = _LENGTH_FIELD_WIDTH + _FELDKENNUNG_WIDTH + len(_LINE_TERMINATOR)

# Total record length (field 8100) is rendered as a fixed 5-digit
# zero-padded string, matching the one real example available (content
# "02976") -- this fixes the 8100 line's own length ahead of time, which
# is what keeps the total-length calculation non-self-referential.
_RECORD_LENGTH_WIDTH = 5


class GdtCharset(StrEnum):
    """Field 9206 values, per the field-level sources found this
    session -- GDT does not fix a single character set; the writer
    declares which one it used."""

    ASCII_7BIT = "1"
    CP437 = "2"
    ISO8859_1 = "3"


# Disclosed judgment call: one of the sources found this session
# documents field-9206 value "3" as "ISO8859-1(ANSI) CP 1252" -- a single
# combined label, treating the two as interchangeable in practice. They
# are NOT identical (Windows-1252 assigns printable characters, such as
# the em dash U+2014, to the 0x80-0x9F range that strict ISO-8859-1
# leaves as unprintable C1 control codes) -- but real German
# documentation text routinely contains exactly those Windows-1252-only
# punctuation marks, and strict ISO-8859-1 would then raise
# `UnicodeEncodeError` on ordinary prose. CP1252 is used here as the
# practical interpretation of value "3", matching the one source that
# named both together, at the cost of not being byte-identical to a
# strict ISO-8859-1 implementation on the (rare) codepoints where they
# actually differ. See ADR-0041.
_PYTHON_CODEC_NAMES: dict[GdtCharset, str] = {
    GdtCharset.ASCII_7BIT: "ascii",
    GdtCharset.CP437: "cp437",
    GdtCharset.ISO8859_1: "cp1252",
}


def python_codec_name(charset: GdtCharset) -> str:
    """The `str.encode(...)` codec name matching a declared field-9206
    charset value."""
    return _PYTHON_CODEC_NAMES[charset]


def encode_field(feldkennung: str, content: str) -> str:
    """One GDT line: a 3-digit self-inclusive total length, the 4-digit
    Feldkennung, the content, then CR/LF.

    `length = 3 (length field) + 4 (Feldkennung) + len(content) + 2 (CRLF)`
    -- verified against the four real field-level lines in ADR-0041
    (010/012/015/076 all match exactly for their respective contents)."""
    if len(feldkennung) != _FELDKENNUNG_WIDTH or not feldkennung.isdigit():
        raise ValueError(f"feldkennung must be a 4-digit string, got {feldkennung!r}")
    length = _LENGTH_OVERHEAD + len(content)
    if length > 999:
        raise ValueError(
            f"GDT field {feldkennung} content too long for a 3-digit length prefix "
            f"({length} characters)"
        )
    return f"{length:0{_LENGTH_FIELD_WIDTH}d}{feldkennung}{content}{_LINE_TERMINATOR}"


def decode_lines(raw: str) -> list[tuple[str, str]]:
    """Inverse of `encode_field`, applied across an entire record's raw
    text. Raises `ValueError` on a malformed line (wrong terminator, a
    declared length that doesn't match the actual line) rather than
    silently truncating or skipping -- a misread GDT file is a medical-
    documentation-adjacent failure mode worth failing loudly on."""
    fields: list[tuple[str, str]] = []
    pos = 0
    while pos < len(raw):
        header = raw[pos : pos + _LENGTH_FIELD_WIDTH]
        if len(header) < _LENGTH_FIELD_WIDTH or not header.isdigit():
            raise ValueError(f"malformed GDT length prefix at offset {pos}: {header!r}")
        length = int(header)
        line = raw[pos : pos + length]
        if len(line) != length or not line.endswith(_LINE_TERMINATOR):
            raise ValueError(
                f"GDT line at offset {pos} declares length {length} but is malformed: {line!r}"
            )
        feldkennung = line[_LENGTH_FIELD_WIDTH : _LENGTH_FIELD_WIDTH + _FELDKENNUNG_WIDTH]
        content = line[_LENGTH_FIELD_WIDTH + _FELDKENNUNG_WIDTH : -len(_LINE_TERMINATOR)]
        fields.append((feldkennung, content))
        pos += length
    return fields


def encode_record(
    satzart: str,
    fields: list[tuple[str, str]],
    *,
    charset: GdtCharset = GdtCharset.ISO8859_1,
    gdt_version: str = "02.10",
) -> str:
    """Wraps `fields` in the `8000` (Satzart)/`8100` (self-inclusive
    total record length)/`9218` (GDT version)/`9206` (charset) header,
    in that order -- the order observed in the one real example this
    session found. The `8100` total is computed over the ENTIRE
    resulting record (its own line included), rendered as a fixed
    5-digit zero-padded value so the calculation isn't self-referential.

    Disclosed limitation: this header structure is inferred by analogy
    to header lines seen alongside (not within) the one PDF-attachment
    example this session verified in full; it has not been checked
    against a complete real GDT record end-to-end. See ADR-0041."""
    header_8000 = encode_field("8000", satzart)
    version_line = encode_field("9218", gdt_version)
    charset_line = encode_field("9206", charset.value)
    body = version_line + charset_line + "".join(
        encode_field(feldkennung, content) for feldkennung, content in fields
    )
    # The 8100 line's own length is fixed (5-digit content), so it can be
    # included in the total before its content is known.
    length_8100_line = _LENGTH_OVERHEAD + _RECORD_LENGTH_WIDTH
    total_length = len(header_8000) + length_8100_line + len(body)
    header_8100 = encode_field("8100", f"{total_length:0{_RECORD_LENGTH_WIDTH}d}")
    return header_8000 + header_8100 + body
