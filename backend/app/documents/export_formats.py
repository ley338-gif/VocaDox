"""DOCX/PDF rendering shared by Document export (`app.documents.router`)
and Recap export (`app.recap.router`) — post-GA P0-2. Both need the same
"title + status/revision meta line(s) + body sections" shape, so it
lives once here rather than duplicated per exporter.

Deliberately minimal formatting (heading, meta paragraph, section
headings, plain paragraphs) — this produces a document a human opens,
reads, and files/prints/attaches to an email; it is not a themed
template engine. No network calls, no external tool invocation
(`python-docx`/`reportlab` are both pure-Python-or-bundled-native-free
libraries — see compliance/dependency-inventory.yml).
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from docx import Document as DocxDocument
from docx.shared import Inches
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


@dataclass(frozen=True, slots=True)
class ExportSection:
    heading: str | None
    lines: list[str]


def render_docx(
    *,
    title: str,
    meta_lines: list[str],
    sections: list[ExportSection],
    intro_lines: list[str] | None = None,
    closing_lines: list[str] | None = None,
    bullet: bool = True,
    letterhead_logo_bytes: bytes | None = None,
) -> bytes:
    """`intro_lines`/`closing_lines` (both default to none, matching every
    existing caller exactly) let a "letter" `document_layout` (post-GA —
    see app.documents.service) add a subject line + salutation before the
    sections and a closing/signature line after, without a second render
    function. `bullet=False` renders each section's lines as plain
    paragraphs instead of a bulleted list -- prose, for the same layout.
    `letterhead_logo_bytes` (post-GA — an org-uploaded
    `TemplateVersion.letterhead_logo_asset_key`, see app.templates.letterhead)
    inserts the image into the document's page header, once, on every page —
    python-docx's native header mechanism, not a body paragraph."""
    doc = DocxDocument()
    if letterhead_logo_bytes is not None:
        header = doc.sections[0].header
        header_para = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        header_para.add_run().add_picture(BytesIO(letterhead_logo_bytes), width=Inches(1.5))
    doc.add_heading(title, level=1)
    for line in meta_lines:
        doc.add_paragraph(line)
    for line in intro_lines or []:
        doc.add_paragraph(line)
    for section in sections:
        if section.heading:
            doc.add_heading(section.heading, level=2)
        for line in section.lines:
            doc.add_paragraph(line, style="List Bullet" if (section.heading and bullet) else None)
    for line in closing_lines or []:
        doc.add_paragraph(line)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def render_pdf(
    *,
    title: str,
    meta_lines: list[str],
    sections: list[ExportSection],
    intro_lines: list[str] | None = None,
    closing_lines: list[str] | None = None,
    letterhead_logo_bytes: bytes | None = None,
) -> bytes:
    """See `render_docx`'s docstring for `intro_lines`/`closing_lines` --
    same purpose here. PDF paragraphs are never bulleted list items to
    begin with (reportlab's plain `Paragraph` flow), so there is no
    `bullet` parameter to mirror. `letterhead_logo_bytes` draws the image
    at the top of every page via reportlab's `onFirstPage`/`onLaterPages`
    canvas callback -- the only mechanism reportlab offers for page-header
    content, since `SimpleDocTemplate`'s `story` flowables have no header
    concept of their own. `topMargin` is only widened when a logo is
    present, so an export with no letterhead is laid out exactly as
    before."""
    buffer = BytesIO()
    top_margin = 100 if letterhead_logo_bytes is not None else 72

    def _draw_letterhead(canvas: Any, _doc_template: Any) -> None:
        if letterhead_logo_bytes is None:
            return
        image = ImageReader(BytesIO(letterhead_logo_bytes))
        canvas.drawImage(
            image,
            x=A4[0] - 108,
            y=A4[1] - 60,
            width=72,
            height=40,
            preserveAspectRatio=True,
            mask="auto",
        )

    pdf_doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=top_margin)
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title), styles["Title"])]
    for line in meta_lines:
        story.append(Paragraph(escape(line), styles["Normal"]))
    story.append(Spacer(1, 12))
    for line in intro_lines or []:
        story.append(Paragraph(escape(line), styles["Normal"]))
    if intro_lines:
        story.append(Spacer(1, 8))
    for section in sections:
        if section.heading:
            story.append(Paragraph(escape(section.heading), styles["Heading2"]))
        for line in section.lines:
            # Reportlab's Paragraph interprets a small XML-like markup
            # subset -- real conversation content must be escaped, never
            # trusted as markup.
            story.append(Paragraph(escape(line), styles["Normal"]))
        story.append(Spacer(1, 8))
    for line in closing_lines or []:
        story.append(Paragraph(escape(line), styles["Normal"]))
    pdf_doc.build(story, onFirstPage=_draw_letterhead, onLaterPages=_draw_letterhead)
    return buffer.getvalue()
