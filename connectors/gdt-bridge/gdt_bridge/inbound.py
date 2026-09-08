"""Inbound half: watch a local folder for GDT request files, extract
whatever patient data they actually contain, and create a VocaDox
conversation + PATIENT participant for it.

The pure parsing logic (`extract_patient_fields`) is satzart-agnostic by
design (ADR-0041: the request-side Satzart number is genuinely
unresolved) -- it reads the domain fields (3000/3101/3102) wherever they
appear, rather than validating against one assumed Satzart value, and
degrades gracefully (returns partial/`None` data, never raises) when
fields are missing, since a real PVS export is not guaranteed to be
complete."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gdt_bridge.gdt_codec import GdtCharset, decode_lines, python_codec_name

logger = logging.getLogger("gdt_bridge.inbound")


@dataclass(frozen=True, slots=True)
class PatientData:
    patient_number: str | None
    display_name: str | None


def extract_patient_fields(fields: list[tuple[str, str]]) -> PatientData:
    """Never fabricates data: `display_name` is built only from whatever
    of 3101 (Name)/3102 (Vorname) is actually present, joined in that
    order -- mirroring the backend export's own "never invent a name
    VocaDox wasn't given" discipline (ADR-0041), just in the opposite
    direction (reading rather than writing)."""
    field_dict: dict[str, str] = {}
    for feldkennung, content in fields:
        field_dict.setdefault(feldkennung, content)

    patient_number = field_dict.get("3000") or None
    name_parts = [field_dict[fk] for fk in ("3102", "3101") if field_dict.get(fk)]
    display_name = " ".join(name_parts) if name_parts else None
    return PatientData(patient_number=patient_number, display_name=display_name)


def decode_gdt_file(raw_bytes: bytes) -> list[tuple[str, str]]:
    """Decodes with the charset the file itself declares (field 9206),
    defaulting to this connector's own default charset if the field is
    absent or the byte sequence can't be decoded as ASCII first (needed
    just to read field 9206's own line, which is always plain digits)."""
    charset = GdtCharset.ISO8859_1
    try:
        ascii_preview = raw_bytes.decode("ascii", errors="ignore")
        for feldkennung, content in decode_lines(ascii_preview):
            if feldkennung == "9206" and content in {c.value for c in GdtCharset}:
                charset = GdtCharset(content)
                break
    except ValueError:
        pass  # fall through to the default charset
    text = raw_bytes.decode(python_codec_name(charset))
    return decode_lines(text)


def wait_until_stable(path: Path, *, checks: int = 3, interval_seconds: float = 0.5) -> bool:
    """A PVS writing a GDT file is not guaranteed to do so atomically --
    reading mid-write would decode garbage. Polls the file size until it
    stops changing across `checks` consecutive samples. Returns False if
    the file disappeared while waiting (e.g. the PVS itself moved it)."""
    last_size = -1
    stable_count = 0
    while stable_count < checks:
        if not path.exists():
            return False
        size = path.stat().st_size
        if size == last_size:
            stable_count += 1
        else:
            stable_count = 0
            last_size = size
        time.sleep(interval_seconds)
    return True


async def process_inbound_file(
    path: Path,
    *,
    create_conversation: Callable,
    create_participant: Callable,
    record_state: Callable,
) -> None:
    """Orchestrates one inbound file: decode -> extract -> create
    conversation (+ participant, if a display name was found) -> record
    in-flight state. Callbacks are injected (rather than importing
    `api_client`/`state` directly) so this function stays unit-testable
    without a real HTTP client or SQLite file."""
    raw = path.read_bytes()
    fields = decode_gdt_file(raw)
    patient = extract_patient_fields(fields)

    conversation_id = await create_conversation(
        title=f"GDT-Import {path.name}",
        external_reference=patient.patient_number,
        external_reference_type="patient-number" if patient.patient_number else None,
    )
    if patient.display_name:
        await create_participant(conversation_id, display_name=patient.display_name)
    else:
        logger.warning("no patient display name found in %s -- proceeding without one", path.name)

    record_state(
        source_gdt_filename=path.name,
        patient_number=patient.patient_number,
        conversation_id=conversation_id,
    )
