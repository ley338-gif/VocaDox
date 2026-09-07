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
from xml.sax.saxutils import escape

from docx import Document as DocxDocument
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


@dataclass(frozen=True, slots=True)
class ExportSection:
    heading: str | None
    lines: list[str]


def render_docx(*, title: str, meta_lines: list[str], sections: list[ExportSection]) -> bytes:
    doc = DocxDocument()
    doc.add_heading(title, level=1)
    for line in meta_lines:
        doc.add_paragraph(line)
    for section in sections:
        if section.heading:
            doc.add_heading(section.heading, level=2)
        for line in section.lines:
            doc.add_paragraph(line, style="List Bullet" if section.heading else None)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def render_pdf(*, title: str, meta_lines: list[str], sections: list[ExportSection]) -> bytes:
    buffer = BytesIO()
    pdf_doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title), styles["Title"])]
    for line in meta_lines:
        story.append(Paragraph(escape(line), styles["Normal"]))
    story.append(Spacer(1, 12))
    for section in sections:
        if section.heading:
            story.append(Paragraph(escape(section.heading), styles["Heading2"]))
        for line in section.lines:
            # Reportlab's Paragraph interprets a small XML-like markup
            # subset -- real conversation content must be escaped, never
            # trusted as markup.
            story.append(Paragraph(escape(line), styles["Normal"]))
        story.append(Spacer(1, 8))
    pdf_doc.build(story)
    return buffer.getvalue()
