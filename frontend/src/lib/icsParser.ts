/**
 * Post-GA P2-2 ("Kalender-Automatik"): a minimal, local, offline parser
 * for a small subset of iCalendar (RFC 5545) VEVENT blocks — the manual-
 * import alternative to a live OAuth calendar sync, chosen specifically
 * because it needs no runtime network connection and no external
 * account/secret (see docs/architecture/adr/0037-calendar-ics-import.md).
 *
 * Deliberately narrow: extracts SUMMARY/DTSTART/DTEND/LOCATION/UID only,
 * does not expand RRULE-recurring events (each VEVENT is treated as one
 * literal occurrence — many calendar exports already expand recurrences
 * into individual VEVENTs for the exported date range, but a bare
 * recurring master event's later occurrences will not appear), and
 * treats a DTSTART with no explicit UTC/TZID marker as local time in the
 * browser's own timezone (a real, disclosed approximation — RFC 5545
 * timezone resolution is considerably more involved than this feature
 * warrants). Never sent anywhere — parsing happens entirely in the
 * browser from a File the user picks; nothing calendar-derived reaches
 * the backend until the user explicitly creates a conversation from it.
 */

export interface CalendarEvent {
  uid: string;
  summary: string;
  start: Date;
  end: Date | null;
  location: string | null;
}

function unfoldLines(text: string): string[] {
  // RFC 5545 line folding: a continuation line starts with a single
  // space or tab and must be joined onto the previous logical line.
  const rawLines = text.split(/\r\n|\n|\r/);
  const unfolded: string[] = [];
  for (const line of rawLines) {
    if ((line.startsWith(" ") || line.startsWith("\t")) && unfolded.length > 0) {
      unfolded[unfolded.length - 1] += line.slice(1);
    } else {
      unfolded.push(line);
    }
  }
  return unfolded;
}

function parseDate(value: string): Date | null {
  // DATE-TIME forms: "20260910T140000Z" (UTC) or "20260910T140000" (floating
  // local) or bare DATE "20260910" (all-day). No TZID resolution.
  const utcMatch = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(value);
  if (utcMatch) {
    const [, y, mo, d, h, mi, s] = utcMatch;
    return new Date(
      Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s))
    );
  }
  const localMatch = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/.exec(value);
  if (localMatch) {
    const [, y, mo, d, h, mi, s] = localMatch;
    return new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s));
  }
  const dateOnlyMatch = /^(\d{4})(\d{2})(\d{2})$/.exec(value);
  if (dateOnlyMatch) {
    const [, y, mo, d] = dateOnlyMatch;
    return new Date(Number(y), Number(mo) - 1, Number(d));
  }
  return null;
}

function parsePropertyLine(line: string): { name: string; value: string } | null {
  // "SUMMARY;LANGUAGE=de:Team-Meeting" -> name "SUMMARY", value after the
  // FIRST unparenthesized colon (params, if any, are ignored — we only
  // need the small property set above, none of which needs param
  // handling beyond TZID, which is deliberately out of scope here).
  const colonIndex = line.indexOf(":");
  if (colonIndex === -1) return null;
  const rawName = line.slice(0, colonIndex);
  const name = rawName.split(";")[0]?.toUpperCase() ?? "";
  const value = line.slice(colonIndex + 1);
  return { name, value };
}

export function parseIcs(text: string): CalendarEvent[] {
  const lines = unfoldLines(text);
  const events: CalendarEvent[] = [];
  let current: Partial<CalendarEvent> & { _hasStart?: boolean } = {};
  let inEvent = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "BEGIN:VEVENT") {
      inEvent = true;
      current = {};
      continue;
    }
    if (trimmed === "END:VEVENT") {
      if (inEvent && current.summary && current.start) {
        events.push({
          uid: current.uid ?? crypto.randomUUID(),
          summary: current.summary,
          start: current.start,
          end: current.end ?? null,
          location: current.location ?? null,
        });
      }
      inEvent = false;
      continue;
    }
    if (!inEvent) continue;

    const property = parsePropertyLine(line);
    if (!property) continue;
    switch (property.name) {
      case "SUMMARY":
        current.summary = property.value.replace(/\\,/g, ",").replace(/\\n/gi, " ").trim();
        break;
      case "DTSTART": {
        const date = parseDate(property.value);
        if (date) current.start = date;
        break;
      }
      case "DTEND": {
        const date = parseDate(property.value);
        if (date) current.end = date;
        break;
      }
      case "LOCATION":
        current.location = property.value.replace(/\\,/g, ",").trim() || null;
        break;
      case "UID":
        current.uid = property.value.trim();
        break;
      default:
        break;
    }
  }

  return events;
}

/** Events starting from `now` minus a small grace window (an already-
 * started meeting is still worth importing) through `daysAhead` days
 * out, nearest first. */
export function upcomingEvents(
  events: CalendarEvent[],
  { now = new Date(), daysAhead = 30 }: { now?: Date; daysAhead?: number } = {}
): CalendarEvent[] {
  const graceMs = 60 * 60 * 1000;
  const horizonMs = daysAhead * 24 * 60 * 60 * 1000;
  return events
    .filter((event) => {
      const delta = event.start.getTime() - now.getTime();
      return delta >= -graceMs && delta <= horizonMs;
    })
    .sort((a, b) => a.start.getTime() - b.start.getTime());
}
