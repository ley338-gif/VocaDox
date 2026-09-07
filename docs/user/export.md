# Exporting (post-GA)

## Dokumentation

From the **Dokumentation** tab, once a document has been composed, you
can download it as:

- **.txt** / **.json** — the original plain-text/structured export.
- **.docx** — a real Word document, one heading per section, one bullet
  per statement, with the approval status and revision number shown at
  the top.
- **.pdf** — the same content as a PDF.
- **FHIR** — a FHIR R4 `DocumentReference` resource (`.json`), for
  importing this document into a Praxisverwaltungssystem/Klinik­
  informationssystem that accepts FHIR files. No patient identity is
  claimed: the resource's subject is a free-text display name (from a
  participant marked "Patient", if you've added one), never a real
  patient-record reference. Nothing is sent anywhere automatically —
  this is a downloadable file, exactly like the other formats; you (or
  your practice's system administrator) import it into your target
  system yourself.

## Recap

From the **Recap** tab, once a recap has been generated and approved,
you can download it as **.txt**, **.docx**, or **.pdf** — same
status/revision visibility as the Document export. Export is only
available for an *approved* recap (unchanged from before).

### Freigabe-Links (share links, post-GA P3-2)

If you have `recap:approve` permission, an approved recap also shows a
**Freigabe-Links** section: create a link (valid 24 hours, 7 days, or 30
days) that lets anyone who has it read the recap **without a VocaDox
login** — useful for sending to a patient or a referring practice. The
link always shows the recap's current content; if you generate and
approve a new revision later, the same link starts showing that instead.
**Widerrufen** (revoke) immediately invalidates a link, and every link
expires on its own if you never revoke it. Nothing beyond the recap text
itself and its expiry date is shown on the public page — no other
conversation data, no login prompt.

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
