"""Inbound field-extraction must work regardless of the (unresolved,
per ADR-0041) request-side Satzart number, and must degrade gracefully
-- never crash, never fabricate -- when fields are missing."""

from __future__ import annotations

from gdt_bridge.gdt_codec import GdtCharset, decode_lines, encode_record
from gdt_bridge.inbound import decode_gdt_file, extract_patient_fields


def test_extract_patient_fields_from_a_full_record() -> None:
    record = encode_record(
        "6301",  # one of the two candidate request Satzart values
        [("3000", "PVS-4711"), ("3101", "Mustermann"), ("3102", "Erika")],
    )
    patient = extract_patient_fields(decode_lines(record))
    assert patient.patient_number == "PVS-4711"
    assert patient.display_name == "Erika Mustermann"


def test_extract_patient_fields_is_satzart_agnostic() -> None:
    """The exact same domain fields under a different (also plausible)
    Satzart value must extract identically -- the parser never checks
    the 8000 field's value."""
    record_a = encode_record("6301", [("3000", "PVS-1")])
    record_b = encode_record("6302", [("3000", "PVS-1")])
    assert extract_patient_fields(decode_lines(record_a)) == extract_patient_fields(
        decode_lines(record_b)
    )


def test_extract_patient_fields_degrades_gracefully_when_fields_missing() -> None:
    record = encode_record("6301", [])  # no domain fields at all
    patient = extract_patient_fields(decode_lines(record))
    assert patient.patient_number is None
    assert patient.display_name is None


def test_extract_patient_fields_never_fabricates_a_missing_name_part() -> None:
    record = encode_record("6301", [("3101", "Mustermann")])  # no Vorname
    patient = extract_patient_fields(decode_lines(record))
    assert patient.display_name == "Mustermann"  # only what was actually given


def test_decode_gdt_file_reads_declared_charset() -> None:
    record = encode_record("6301", [("3101", "Muller")], charset=GdtCharset.ISO8859_1)
    fields = decode_gdt_file(record.encode("cp1252"))
    assert dict(fields)["3101"] == "Muller"
