from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from gdt_bridge import outbound
from gdt_bridge.api_client import ExportedFile
from gdt_bridge.outbound import _write_gdt_pdf_bundle, _write_gdt_text_file


def _bundle(pdf_name: str, gdt_name: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(pdf_name, b"%PDF-test")
        archive.writestr(gdt_name, "0126303PDF\r\n".encode("cp1252"))
    return buffer.getvalue()


@pytest.mark.parametrize("malicious", ["../escape.pdf", "sub/escape.pdf", "..\\escape.pdf"])
def test_pdf_bundle_rejects_path_traversal(tmp_path: Path, malicious: str) -> None:
    exported = ExportedFile(
        content=_bundle(malicious, "result.gdt"),
        media_type="application/zip",
        filename="bundle.zip",
    )
    with pytest.raises(ValueError, match="unsafe export filename"):
        _write_gdt_pdf_bundle(exported, tmp_path)


def test_text_export_rejects_header_supplied_path(tmp_path: Path) -> None:
    exported = ExportedFile(
        content=b"gdt", media_type="text/plain", filename="../outside.gdt"
    )
    with pytest.raises(ValueError, match="unsafe export filename"):
        _write_gdt_text_file(exported, tmp_path)
    assert not (tmp_path.parent / "outside.gdt").exists()


def test_pdf_bundle_rejects_unexpected_extra_member(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("result.pdf", b"%PDF-test")
        archive.writestr("result.gdt", b"0126303PDF\r\n")
        archive.writestr("extra.txt", b"unexpected")
    exported = ExportedFile(buffer.getvalue(), "application/zip", "bundle.zip")
    with pytest.raises(ValueError, match="exactly one PDF and one GDT"):
        _write_gdt_pdf_bundle(exported, tmp_path)


def test_pdf_bundle_rejects_compression_bomb_ratio(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("result.pdf", b"0" * 1_000_000)
        archive.writestr("result.gdt", b"0126303PDF\r\n")
    exported = ExportedFile(buffer.getvalue(), "application/zip", "bundle.zip")
    with pytest.raises(ValueError, match="compression-ratio"):
        _write_gdt_pdf_bundle(exported, tmp_path)


def test_text_export_rejects_oversized_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbound, "MAX_ARCHIVE_MEMBER_BYTES", 2)
    exported = ExportedFile(content=b"gdt", media_type="text/plain", filename="result.gdt")
    with pytest.raises(ValueError, match="exceeds size limit"):
        _write_gdt_text_file(exported, tmp_path)
