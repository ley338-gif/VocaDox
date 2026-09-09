"""Golden-fixture + round-trip tests for the connector's own GDT codec.
The golden fixture reproduces four real field lines from a practice-
software forum thread quoted in ADR-0041, byte-for-byte."""

from __future__ import annotations

import pytest

from gdt_bridge.gdt_codec import GdtCharset, decode_lines, encode_field, encode_record, rewrite_field


def test_encode_field_matches_real_forum_example() -> None:
    assert encode_field("6302", "1") == "01063021\r\n"
    assert encode_field("6303", "PDF") == "0126303PDF\r\n"
    assert encode_field("6304", "Report") == "0156304Report\r\n"


def test_decode_lines_round_trips_encode_field() -> None:
    line = encode_field("3101", "Herr M.")
    assert decode_lines(line) == [("3101", "Herr M.")]


def test_encode_record_round_trips_and_is_self_consistent() -> None:
    record = encode_record(
        "6310",
        [("3000", "PVS-4711"), ("3101", "Herr M."), ("6302", "1"), ("6303", "PDF")],
    )
    fields = dict(decode_lines(record))
    assert fields["8000"] == "6310"
    assert fields["3000"] == "PVS-4711"
    assert fields["6303"] == "PDF"
    # 8100's declared total must equal the record's actual character count.
    assert int(fields["8100"]) == len(record)


def test_encode_record_rejects_field_too_long_for_length_prefix() -> None:
    with pytest.raises(ValueError):
        encode_field("6304", "x" * 1000)


def test_rewrite_field_replaces_filename_and_stays_valid() -> None:
    original = encode_record(
        "6310",
        [("6302", "1"), ("6303", "PDF"), ("6304", "Report"), ("6305", "document-1-r1.pdf")],
        charset=GdtCharset.ISO8859_1,
    )
    rewritten = rewrite_field(original, "6305", r"C:\gdt\export\document-1-r1.pdf")
    fields = dict(decode_lines(rewritten))
    assert fields["6305"] == r"C:\gdt\export\document-1-r1.pdf"
    assert fields["6303"] == "PDF"  # untouched fields survive the rewrite
    assert int(fields["8100"]) == len(rewritten)
