# Exporting (post-GA)

## Dokumentation

From the **Dokumentation** tab, once a document has been composed, you
can download it as:

- **.txt** / **.json** — the original plain-text/structured export.
- **.docx** — a real Word document, one heading per section, one bullet
  per statement, with the approval status and revision number shown at
  the top.
- **.pdf** — the same content as a PDF.

## Recap

From the **Recap** tab, once a recap has been generated and approved,
you can download it as **.txt**, **.docx**, or **.pdf** — same
status/revision visibility as the Document export. Export is only
available for an *approved* recap (unchanged from before).

## Transcript

From the **Transkript** tab you can download the transcript as **.txt**,
**.json**, **.md** (Markdown), **.srt**, or **.vtt** — the last two are
standard subtitle formats built from the same segment timestamps you see
in the tab, importable into any video editor or media player that
supports subtitles.

## What's audited

Every export (any format) records a `document.exported` /
`recap.exported` audit event, same as before — only the format name
changed to include the new options; no content is ever logged.
