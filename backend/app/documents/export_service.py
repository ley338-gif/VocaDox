"""Shared document-export rendering, used by both the human-facing
`app.documents.router` export endpoint and the service-account-
authenticated `app.integrations.router` Integration API export route.
Extracted (post-GA, alongside ADR-0041's GDT formats) so a new export
format is implemented once, not duplicated per router.

This module does the "build the response body" half of exporting a
document; each caller keeps its own "authorize, capture ORM primitives
before commit, record the audit event, commit" sequence, since that
sequencing is tied to each router's own request lifecycle (see the
lazy-load-after-expire warning in `app.documents.router`).
"""

from __future__ import annotations

import io
import json as _json
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import ConversationParticipant, ParticipantType
from app.documents.export_formats import ExportSection, render_docx, render_pdf
from app.documents.fhir_export import render_fhir_document_reference
from app.documents.gdt_export import render_gdt_pdf_reference, render_gdt_text
from app.documents.gdt_line_codec import GdtCharset, python_codec_name
from app.providers.storage import StorageProvider
from app.templates.letterhead import load_letterhead_logo
from app.templates.models import TemplateVersion

_LETTER_SALUTATION = "Sehr geehrte Kolleginnen und Kollegen,"
_LETTER_CLOSING = "Mit freundlichen kollegialen Grüßen"


@dataclass(frozen=True, slots=True)
class ExportPayload:
    content: bytes
    media_type: str
    # None => an inline body (today: text/json), matching the pre-refactor
    # behavior exactly; any other value => `Content-Disposition: attachment`.
    filename: str | None


def _letter_chrome(
    *, conversation_title: str, generated_at: datetime
) -> tuple[list[str], list[str]]:
    subject = f"Betreff: {conversation_title} vom {generated_at.strftime('%d.%m.%Y')}"
    return [subject, "", _LETTER_SALUTATION], [_LETTER_CLOSING]


def _section_lines(statements: list[dict], *, is_freeform: bool) -> list[str]:
    if is_freeform:
        text = statements[0]["text"] if statements else ""
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        return paragraphs or [text]
    return [st["text"] for st in statements]


async def _patient_participant_display_name(
    db: AsyncSession, conversation_id: uuid.UUID
) -> str | None:
    result = await db.execute(
        select(ConversationParticipant.display_name).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.participant_type == ParticipantType.PATIENT.value,
        )
    )
    return result.scalars().first()


async def render_document_export(
    db: AsyncSession,
    storage: StorageProvider,
    *,
    format: str,  # noqa: A002 - matches the query param name intentionally
    conversation_id: uuid.UUID,
    document_id: uuid.UUID,
    conversation_title: str,
    conversation_started_at: datetime | None,
    conversation_ended_at: datetime | None,
    conversation_external_reference: str | None,
    conversation_external_reference_type: str | None,
    revision_number: int,
    revision_status: str,
    revision_content: list[dict[str, Any]],
    revision_text: str,
    revision_created_at: datetime,
    revision_document_layout: str,
    revision_template_version_id: uuid.UUID | None,
) -> ExportPayload:
    if format == "json":
        payload = {
            "document_id": str(document_id),
            "conversation_id": str(conversation_id),
            "revision_number": revision_number,
            "status": revision_status,
            "sections": revision_content,
        }
        return ExportPayload(
            content=_json.dumps(payload, indent=2).encode("utf-8"),
            media_type="application/json",
            filename=None,
        )

    meta_lines = [f"Status: {revision_status} (revision {revision_number})"]

    if format in ("docx", "pdf", "gdt-pdf"):
        is_letter = revision_document_layout == "letter"
        is_freeform = revision_document_layout == "freeform"
        sections = [
            ExportSection(
                heading=s["title"],
                lines=_section_lines(s["statements"], is_freeform=is_freeform),
            )
            for s in revision_content
        ]
        export_title = "Arztbrief" if is_letter else "Dokumentation"
        intro_lines, closing_lines = (
            _letter_chrome(conversation_title=conversation_title, generated_at=revision_created_at)
            if is_letter
            else (None, None)
        )
        letterhead_logo_bytes: bytes | None = None
        if revision_template_version_id is not None:
            template_version = await db.get(TemplateVersion, revision_template_version_id)
            if template_version is not None and template_version.letterhead_logo_asset_key:
                loaded = await load_letterhead_logo(
                    storage, template_version.letterhead_logo_asset_key
                )
                if loaded is not None:
                    letterhead_logo_bytes, _content_type = loaded

        if format == "docx":
            content = render_docx(
                title=export_title,
                meta_lines=meta_lines,
                sections=sections,
                intro_lines=intro_lines,
                closing_lines=closing_lines,
                bullet=not (is_letter or is_freeform),
                letterhead_logo_bytes=letterhead_logo_bytes,
            )
            return ExportPayload(
                content=content,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=f"document-{document_id}-r{revision_number}.docx",
            )

        pdf_bytes = render_pdf(
            title=export_title,
            meta_lines=meta_lines,
            sections=sections,
            intro_lines=intro_lines,
            closing_lines=closing_lines,
            letterhead_logo_bytes=letterhead_logo_bytes,
        )
        if format == "pdf":
            return ExportPayload(
                content=pdf_bytes,
                media_type="application/pdf",
                filename=f"document-{document_id}-r{revision_number}.pdf",
            )

        # gdt-pdf: bundle the same PDF plus a .gdt file referencing it by
        # bare filename (field 6305) into one ZIP -- see gdt_export.py's
        # docstring for why the backend can't emit a real filesystem path.
        patient_display_name = await _patient_participant_display_name(db, conversation_id)
        pdf_filename = f"document-{document_id}-r{revision_number}.pdf"
        gdt_filename = f"document-{document_id}-r{revision_number}.gdt"
        gdt_text = render_gdt_pdf_reference(
            patient_number=conversation_external_reference,
            patient_display_name=patient_display_name,
            pdf_filename=pdf_filename,
            description=conversation_title,
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(pdf_filename, pdf_bytes)
            archive.writestr(gdt_filename, gdt_text.encode(python_codec_name(GdtCharset.ISO8859_1)))
        return ExportPayload(
            content=buffer.getvalue(),
            media_type="application/zip",
            filename=f"document-{document_id}-r{revision_number}.gdt.zip",
        )

    if format == "gdt-text":
        patient_display_name = await _patient_participant_display_name(db, conversation_id)
        gdt_text = render_gdt_text(
            patient_number=conversation_external_reference,
            patient_display_name=patient_display_name,
            rendered_text=revision_text,
        )
        return ExportPayload(
            # GDT has no registered IANA media type -- application/octet-stream
            # is a disclosed judgment call, not a standard (see ADR-0041).
            content=gdt_text.encode(python_codec_name(GdtCharset.ISO8859_1)),
            media_type="application/octet-stream",
            filename=f"document-{document_id}-r{revision_number}.gdt",
        )

    if format == "fhir":
        subject_display = await _patient_participant_display_name(db, conversation_id)
        resource = render_fhir_document_reference(
            document_id=document_id,
            conversation_title=conversation_title,
            subject_display=subject_display,
            revision_number=revision_number,
            revision_status=revision_status,
            rendered_text=revision_text,
            generated_at=revision_created_at,
            started_at=conversation_started_at,
            ended_at=conversation_ended_at,
            external_reference=conversation_external_reference,
            external_reference_type=conversation_external_reference_type,
        )
        return ExportPayload(
            content=_json.dumps(resource, indent=2).encode("utf-8"),
            media_type="application/fhir+json",
            filename=f"document-{document_id}-r{revision_number}.fhir.json",
        )

    body = "\n\n".join(meta_lines) + "\n\n" + revision_text
    return ExportPayload(content=body.encode("utf-8"), media_type="text/plain", filename=None)
