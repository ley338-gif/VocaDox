/**
 * Mirrors app.intelligence.rendering.render_fact_statement's category
 * rendering exactly, including its generic fallback for any non-builtin
 * category (e.g. the Meeting template's action_item, or Medical's
 * symptom/finding) — a fact's shape depends on the template that
 * produced it, so a renderer that only knows the 3 Phase-4 builtin
 * categories' fields renders "?" / "(?, due ?)" for anything else.
 *
 * Shared between FactsPanel (raw structured_value) and ReviewWizard
 * (corrected_structured_value ?? structured_value) — that was the only
 * real difference between two near-identical implementations that had
 * drifted apart and gone stale independently.
 */
import type { FactCategory } from "../api/intelligence";

const GENERAL_FACT_KEYS = ["subject", "attribute", "value", "certainty", "evidence_segment_sequences"];
const DECISION_KEYS = ["description", "decided_by", "certainty", "evidence_segment_sequences"];
const TASK_KEYS = ["description", "assignee", "due_date", "certainty", "evidence_segment_sequences"];

function isSubsetOf(value: Record<string, unknown>, allowed: string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key));
}

export function factSummary(category: FactCategory | string, value: Record<string, unknown>): string {
  if (category === "general_fact" && isSubsetOf(value, GENERAL_FACT_KEYS)) {
    return `${String(value.subject ?? "?")} — ${String(value.attribute ?? "?")}: ${String(value.value ?? "?")}`;
  }
  if (category === "decision" && isSubsetOf(value, DECISION_KEYS)) {
    return String(value.description ?? "?");
  }
  if (category === "task" && isSubsetOf(value, TASK_KEYS)) {
    return (
      `${String(value.description ?? "?")} ` +
      `(assignee: ${String(value.assignee ?? "not mentioned")}, ` +
      `due: ${String(value.due_date ?? "not mentioned")})`
    );
  }
  // Generic fallback for any category a Template defines that isn't one
  // of the 3 builtin ones above (Post-GA medical/meeting/psychotherapy
  // categories included). Every current Template schema puts the fact's
  // actual content in a field named "description" or "name" — that field
  // renders unlabeled, like prose; only the remaining fields (e.g.
  // onset/severity/dose) get an explicit "label: value" annotation, and
  // only once the extractor actually found a value ('NOT_MENTIONED' is
  // deliberately omitted rather than rendered as noise). Never render a
  // raw field name — "description"/"name" included — as a visible label.
  const excluded = ["certainty", "evidence_segment_sequences"];
  const isUsable = (v: unknown) => v !== null && v !== "" && v !== "NOT_MENTIONED";
  const primaryKey = "description" in value ? "description" : "name" in value ? "name" : null;
  if (primaryKey !== null) {
    const primary = value[primaryKey];
    const annotations = Object.entries(value)
      .filter(([key, v]) => !excluded.includes(key) && key !== primaryKey && isUsable(v))
      .map(([key, v]) => `${key}: ${String(v)}`);
    if (primary === null || primary === undefined || primary === "") {
      return annotations.length > 0 ? annotations.join("; ") : "(no details)";
    }
    return annotations.length > 0 ? `${String(primary)} (${annotations.join(", ")})` : String(primary);
  }
  const parts = Object.entries(value)
    .filter(([key, v]) => !excluded.includes(key) && isUsable(v))
    .map(([key, v]) => `${key}: ${String(v)}`);
  return parts.length > 0 ? parts.join("; ") : "(no details)";
}
