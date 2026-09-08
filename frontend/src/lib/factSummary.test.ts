import { describe, expect, it } from "vitest";

import { factSummary } from "./factSummary";

describe("factSummary", () => {
  it("renders a builtin general_fact as subject — attribute: value", () => {
    expect(factSummary("general_fact", { subject: "Blood pressure", attribute: "reading", value: "120/80" })).toBe(
      "Blood pressure — reading: 120/80",
    );
  });

  it("renders a Template-defined category's description field unlabeled, with other fields as unlabeled annotations", () => {
    expect(
      factSummary("symptom", { description: "Atemnot", onset: "bei Treppensteigen", severity: "besonders" }),
    ).toBe("Atemnot (bei Treppensteigen, besonders)");
  });

  it("never shows any raw field label — description/name or the secondary fields", () => {
    const symptom = factSummary("symptom", { description: "Atemnot", onset: "bei Treppensteigen" });
    expect(symptom).not.toMatch(/description:|onset:/);
    const medication = factSummary("medication", { name: "Ramipril", dose: "5mg", frequency: "1x täglich" });
    expect(medication).not.toMatch(/name:|dose:|frequency:/);
    expect(medication).toBe("Ramipril (5mg, 1x täglich)");
  });

  it("omits NOT_MENTIONED annotations instead of rendering them as noise", () => {
    expect(factSummary("finding", { description: "Atemgeräusch normal", result: "NOT_MENTIONED" })).toBe(
      "Atemgeräusch normal",
    );
  });

  it("renders a finding's result field unlabeled too", () => {
    expect(factSummary("finding", { description: "Atemgeräusch", result: "normal" })).toBe("Atemgeräusch (normal)");
  });

  it("renders a bare description/name with no annotations unlabeled", () => {
    expect(factSummary("diagnosis", { description: "Akute Bronchitis" })).toBe("Akute Bronchitis");
  });

  it("falls back to a 'field: value' dump only when there is no description/name field", () => {
    expect(factSummary("agenda_topic", { topic: "Budget", outcome: "approved" })).toBe(
      "topic: Budget; outcome: approved",
    );
  });
});
