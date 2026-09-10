import { describe, expect, it } from "vitest";

import { parseIcs, upcomingEvents } from "./icsParser";

const SAMPLE_ICS = [
  "BEGIN:VCALENDAR",
  "VERSION:2.0",
  "BEGIN:VEVENT",
  "UID:event-1@example.com",
  "DTSTART:20260910T140000Z",
  "DTEND:20260910T150000Z",
  "SUMMARY:Team-Meeting",
  "LOCATION:Konferenzraum A",
  "END:VEVENT",
  "BEGIN:VEVENT",
  "UID:event-2@example.com",
  "DTSTART:20260101T090000Z",
  "SUMMARY:Vergangener Termin",
  "END:VEVENT",
  "END:VCALENDAR",
].join("\r\n");

describe("parseIcs", () => {
  it("extracts summary/start/end/location/uid from VEVENT blocks", () => {
    const events = parseIcs(SAMPLE_ICS);
    expect(events).toHaveLength(2);
    const first = events[0];
    expect(first.uid).toBe("event-1@example.com");
    expect(first.summary).toBe("Team-Meeting");
    expect(first.location).toBe("Konferenzraum A");
    expect(first.start.toISOString()).toBe("2026-09-10T14:00:00.000Z");
    expect(first.end?.toISOString()).toBe("2026-09-10T15:00:00.000Z");
  });

  it("unfolds continuation lines per RFC 5545", () => {
    const folded = [
      "BEGIN:VEVENT",
      "UID:folded-1",
      "DTSTART:20260910T140000Z",
      "SUMMARY:A very long meeting title that got f",
      " olded across two lines",
      "END:VEVENT",
    ].join("\r\n");
    const events = parseIcs(folded);
    expect(events[0].summary).toBe(
      "A very long meeting title that got folded across two lines"
    );
  });

  it("skips a VEVENT missing a required field (summary or start)", () => {
    const incomplete = [
      "BEGIN:VEVENT",
      "UID:no-start",
      "SUMMARY:Missing DTSTART",
      "END:VEVENT",
    ].join("\r\n");
    expect(parseIcs(incomplete)).toHaveLength(0);
  });

  it("ignores oversized physical lines", () => {
    const oversized = [
      "BEGIN:VEVENT",
      "UID:oversized-line",
      "DTSTART:20260910T140000Z",
      `SUMMARY:${"x".repeat(16_385)}`,
      "END:VEVENT",
    ].join("\r\n");
    expect(parseIcs(oversized)).toHaveLength(0);
  });

  it("caps the number of parsed events", () => {
    const events = Array.from({ length: 5_001 }, (_, index) =>
      [
        "BEGIN:VEVENT",
        `UID:event-${index}`,
        "DTSTART:20260910T140000Z",
        `SUMMARY:Event ${index}`,
        "END:VEVENT",
      ].join("\r\n")
    ).join("\r\n");
    expect(parseIcs(events)).toHaveLength(5_000);
  });
});

describe("upcomingEvents", () => {
  it("filters to events within the grace window through the horizon, nearest first", () => {
    const now = new Date("2026-09-10T13:00:00Z");
    const events = parseIcs(SAMPLE_ICS);
    const result = upcomingEvents(events, { now, daysAhead: 30 });
    expect(result).toHaveLength(1);
    expect(result[0].uid).toBe("event-1@example.com");
  });

  it("still includes an event that started within the last hour", () => {
    const now = new Date("2026-09-10T14:30:00Z");
    const events = parseIcs(SAMPLE_ICS);
    const result = upcomingEvents(events, { now, daysAhead: 30 });
    expect(result.map((e) => e.uid)).toContain("event-1@example.com");
  });
});
