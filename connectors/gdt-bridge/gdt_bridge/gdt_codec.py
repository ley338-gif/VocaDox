"""Low-level GDT line/record codec -- a deliberate, disclosed duplicate
of `backend/app/documents/gdt_line_codec.py`. This connector must never
import from the VocaDox backend package (it runs outside the backend's
trust boundary, on/near a practice PC, talking only HTTP to the
Integration API -- see docs/architecture/future-considerations.md's
connector-architecture rule and ADR-0041's Known Limitations for why
this duplication is intentional rather than an oversight).

Confidence level, disclosed explicitly: verified by arithmetic against
real field-level lines from a practice-software forum example, not
against the primary GDT specification (unavailable in the environment
this was built in). See ADR-0041.
"""

from __future__ import annotations

from enum import StrEnum

_LENGTH_FIELD_WIDTH = 3
_FELDKENNUNG_WIDTH = 4
_LINE_TERMINATOR = "\r\n"
_LENGTH_OVERHEAD = _LENGTH_FIELD_WIDTH + _FELDKENNUNG_WIDTH + len(_LINE_TERMINATOR)
_RECORD_LENGTH_WIDTH = 5


class GdtCharset(StrEnum):
    ASCII_7BIT = "1"
    CP437 = "2"
    ISO8859_1 = "3"


# See the backend twin's docstring for why value "3" maps to CP1252
# rather than strict ISO-8859-1 -- one source names them together
# ("ISO8859-1(ANSI) CP 1252"), and real German text routinely contains
# CP1252-only punctuation (e.g. the em dash) that strict ISO-8859-1
# cannot encode at all.
_PYTHON_CODEC_NAMES: dict[GdtCharset, str] = {
    GdtCharset.ASCII_7BIT: "ascii",
    GdtCharset.CP437: "cp437",
    GdtCharset.ISO8859_1: "cp1252",
}


def python_codec_name(charset: GdtCharset) -> str:
    return _PYTHON_CODEC_NAMES[charset]


def encode_field(feldkennung: str, content: str) -> str:
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
    header_8000 = encode_field("8000", satzart)
    version_line = encode_field("9218", gdt_version)
    charset_line = encode_field("9206", charset.value)
    body = version_line + charset_line + "".join(
        encode_field(feldkennung, content) for feldkennung, content in fields
    )
    length_8100_line = _LENGTH_OVERHEAD + _RECORD_LENGTH_WIDTH
    total_length = len(header_8000) + length_8100_line + len(body)
    header_8100 = encode_field("8100", f"{total_length:0{_RECORD_LENGTH_WIDTH}d}")
    return header_8000 + header_8100 + body


def rewrite_field(raw: str, feldkennung: str, new_content: str) -> str:
    """Rewrites one field's content in-place and returns the re-encoded
    record. Used by `outbound.py` to replace field 6305's bare filename
    (all VocaDox's backend can ever emit -- it has no knowledge of the
    practice's local filesystem) with the real absolute export path just
    before writing the file to disk."""
    fields = decode_lines(raw)
    satzart = next(content for fk, content in fields if fk == "8000")
    charset_value = next((content for fk, content in fields if fk == "9206"), GdtCharset.ISO8859_1.value)
    gdt_version = next((content for fk, content in fields if fk == "9218"), "02.10")
    domain_fields = [
        (fk, new_content if fk == feldkennung else content)
        for fk, content in fields
        if fk not in ("8000", "8100", "9206", "9218")
    ]
    return encode_record(
        satzart, domain_fields, charset=GdtCharset(charset_value), gdt_version=gdt_version
    )
