"""Format sniffing + filename sanitization tests. All byte samples below
are either minimal synthetic container headers (not real media) or, for
WAV, a full synthetically generated tone (see
tests/conversations/conftest.py::make_wav_bytes)."""

from __future__ import annotations

from app.media.validation import (
    content_disposition_filename,
    sanitize_display_filename,
    sniff_audio_format,
)

from tests.conversations.conftest import make_wav_bytes


def test_sniff_wav() -> None:
    fmt = sniff_audio_format(make_wav_bytes()[:64])
    assert fmt is not None
    assert fmt.container == "wav"


def test_sniff_webm() -> None:
    fmt = sniff_audio_format(b"\x1a\x45\xdf\xa3" + b"\x00" * 60)
    assert fmt is not None
    assert fmt.container == "webm"


def test_sniff_mp3_with_id3() -> None:
    fmt = sniff_audio_format(b"ID3" + b"\x00" * 61)
    assert fmt is not None
    assert fmt.container == "mp3"


def test_sniff_mp3_bare_frame_sync() -> None:
    fmt = sniff_audio_format(bytes([0xFF, 0xFB]) + b"\x00" * 62)
    assert fmt is not None
    assert fmt.container == "mp3"


def test_sniff_m4a() -> None:
    head = b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00" + b"\x00" * 48
    fmt = sniff_audio_format(head)
    assert fmt is not None
    assert fmt.container == "m4a"


def test_sniff_rejects_unrecognized_bytes() -> None:
    assert sniff_audio_format(b"not audio at all" + b"\x00" * 48) is None


def test_sniff_rejects_html_masquerading_as_audio() -> None:
    # Malformed-media / content-sniffing mismatch: never accept HTML/SVG
    # dressed up with an audio-sounding filename or Content-Type.
    assert sniff_audio_format(b"<html><script>alert(1)</script></html>") is None


def test_sniff_rejects_empty_bytes() -> None:
    assert sniff_audio_format(b"") is None


def test_sanitize_filename_strips_path_components() -> None:
    assert sanitize_display_filename("../../etc/passwd") == "passwd"
    assert sanitize_display_filename("C:\\Windows\\evil.wav") == "evil.wav"


def test_sanitize_filename_strips_crlf_header_injection() -> None:
    malicious = 'recording.wav"\r\nX-Injected: evil'
    cleaned = sanitize_display_filename(malicious)
    assert cleaned is not None
    assert "\r" not in cleaned
    assert "\n" not in cleaned


def test_sanitize_filename_handles_none_and_empty() -> None:
    assert sanitize_display_filename(None) is None
    assert sanitize_display_filename("") is None
    assert sanitize_display_filename("   ") is None


def test_content_disposition_filename_is_ascii_and_quote_safe() -> None:
    result = content_disposition_filename('evil".wav')
    assert '"' not in result
    result_unicode = content_disposition_filename("üñïçödé.wav")
    assert all(ord(c) < 128 for c in result_unicode)


def test_content_disposition_filename_falls_back_when_empty() -> None:
    assert content_disposition_filename(None) == "audio"
    assert content_disposition_filename("") == "audio"
