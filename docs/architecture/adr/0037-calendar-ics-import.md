# 0037 — Calendar automation: local .ics import, not live OAuth sync

## Status
Accepted (2026-09-07). Post-GA, roadmap item P2-2 (calendar half), after
explicit user confirmation (this ADR was escalated per the standing
directive's own ESKALATION criteria before being implemented).

## Context

The roadmap asks for "Kalender-Automatik" alongside P2-2's audio-capture
half. Every design that gives genuinely automatic, live upcoming-meeting
detection (polling Google Calendar/Microsoft Graph/CalDAV) needs both a
runtime network connection to an external service and an OAuth client
secret/account — both explicit ESKALATION triggers in the standing
directive ("Etwas verlangt eine Laufzeit-Netzwerkverbindung oder externe
Dienste", "Du brauchst ein Geheimnis oder Konto") and both in direct
tension with ADR-0007's air-gapped, no-new-runtime-network-dependency
posture. This was escalated to the user rather than decided silently;
the answer was: local `.ics` file import, no live sync.

## Decision

**Calendar events are imported from a user-supplied `.ics` file, parsed
entirely client-side, with no server involvement until the user
explicitly creates a conversation.** The user exports/downloads a
calendar file from whatever calendar application they already use (every
mainstream calendar app supports `.ics` export) and picks it via a plain
`<input type="file">` on the New Conversation page. `frontend/src/lib/
icsParser.ts` parses it with a small, dependency-free RFC 5545 subset
parser (SUMMARY/DTSTART/DTEND/LOCATION/UID) and lists upcoming events;
clicking one pre-fills the conversation title and defaults the
conversation type to "Meeting" — the user still explicitly reviews and
submits the form exactly as before. Nothing from the calendar file is
sent to the backend unless and until that submit happens, and even then
only the fields the user would have typed manually anyway (title) — the
event's UID, other attendees, or the raw `.ics` content are never
transmitted.

**No recurrence expansion, no timezone database.** A recurring event's
`RRULE` is not expanded — each `VEVENT` block is treated as one literal
occurrence, matching what many calendar exports already produce for a
bounded date range, but a bare recurring master event's future
occurrences beyond what the file literally lists will not appear. A
`DTSTART` without a `Z` UTC suffix is treated as floating local time in
the browser's own timezone, not resolved via `TZID`. Both are disclosed,
real limitations — implementing full RFC 5545 recurrence/timezone
semantics is a meaningfully larger undertaking than this feature
warrants, and the fallback for a user who hits either limitation is
simply typing the title manually, exactly like today.

**This is manual, repeatable, and explicitly not "automatic" in the live
sense the word can imply.** A user must re-export and re-import their
calendar file periodically to see newly added events — there is no
background sync, no notification, no auto-creation of conversations.
This is a deliberate, disclosed trade-off: it trades genuine automation
for staying entirely inside the air-gapped, no-new-secret posture every
other measure in this roadmap has also respected.

## Consequences

- No new runtime dependency (the parser is hand-written, no `ical.js`/
  `node-ical`/similar package), no new backend endpoint, no new
  migration, no new permission, no OAuth client to register or secret to
  store.
- If a future need for genuinely live calendar sync arises, it is a
  distinct, larger decision (which provider(s), where secrets live, what
  the air-gapped deployment story becomes) that deserves its own
  dedicated design and explicit sign-off — not a quiet extension of this
  feature.
- The parser's narrow RFC 5545 subset should be revisited if real usage
  shows the recurrence/timezone gaps are actually painful in practice;
  today that is unverified (no user feedback yet exists on this measure).
