"""Upload validation: size limits, content-type allow-list, and magic-byte
sniffing so a renamed/relabeled file can't slip past a Content-Type check
alone. Deliberately hand-rolled (stdlib only, no new dependency) — the
signature set is small and stable enough that a parsing library would be
overkill and would itself need a license/CVE review for something this
narrow.

Supported audio formats (Phase 2, deliberately small and exactly what is
tested — see docs/architecture/media-storage.md):
  - WebM/Opus (browser MediaRecorder default)
  - WAV (PCM)
  - MP3
  - M4A/AAC (ISO-BMFF "ftyp" container)

Nothing else is accepted. Never execute, render, or interpret uploaded
bytes as anything other than opaque audio content.
"""

from __future__ import annotations

from dataclasses import dataclass


class UploadValidationError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class DetectedFormat:
    container: str
    content_type: str


# Ordered checks: (magic-byte predicate, DetectedFormat). Only the first
# few hundred bytes are ever inspected.
def _is_webm(head: bytes) -> bool:
    return head.startswith(b"\x1a\x45\xdf\xa3")  # EBML magic (WebM/Matroska)


def _is_wav(head: bytes) -> bool:
    return head[:4] == b"RIFF" and head[8:12] == b"WAVE"


def _is_mp3(head: bytes) -> bool:
    if head[:3] == b"ID3":
        return True
    # Bare MPEG frame sync (no ID3 tag): 0xFFEx / 0xFFFx family.
    return len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0


def _is_m4a(head: bytes) -> bool:
    # ISO-BMFF: bytes 4-8 are "ftyp"; brand at 8-12 identifies M4A/MP4 family.
    if len(head) < 12 or head[4:8] != b"ftyp":
        return False
    brand = head[8:12]
    return brand in {b"M4A ", b"isom", b"mp42", b"mp41", b"M4B "}


_DETECTORS: list[tuple[object, DetectedFormat]] = [
    (_is_webm, DetectedFormat(container="webm", content_type="audio/webm")),
    (_is_wav, DetectedFormat(container="wav", content_type="audio/wav")),
    (_is_mp3, DetectedFormat(container="mp3", content_type="audio/mpeg")),
    (_is_m4a, DetectedFormat(container="m4a", content_type="audio/mp4")),
]


def sniff_audio_format(head: bytes) -> DetectedFormat | None:
    """Inspect the first bytes of a file and return the detected format, or
    None if it doesn't match any supported signature."""
    for predicate, fmt in _DETECTORS:
        if predicate(head):  # type: ignore[operator]
            return fmt
    return None


def sanitize_display_filename(filename: str | None) -> str | None:
    """Strip anything that could enable header injection (CRLF) or path
    traversal when the filename is later echoed back in a
    Content-Disposition header or shown in the UI. The original filename is
    ALWAYS metadata only — it is never used to build a storage path."""
    if not filename:
        return None
    # Drop any path components a browser/client might have included.
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1]
    # Strip control characters (CR, LF, NUL, etc.) that could inject headers.
    cleaned = "".join(ch for ch in cleaned if ch.isprintable())
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    return cleaned[:255]


def content_disposition_filename(filename: str | None) -> str:
    """Build a safe `filename` parameter value for a Content-Disposition
    header: ASCII-only, quotes/backslashes escaped, no CR/LF possible
    (already stripped by sanitize_display_filename)."""
    safe = sanitize_display_filename(filename) or "audio"
    ascii_safe = safe.encode("ascii", "ignore").decode("ascii") or "audio"
    escaped = ascii_safe.replace("\\", "").replace('"', "")
    return escaped
