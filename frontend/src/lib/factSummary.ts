/**
 * Mirrors app.documents.service._render_statement's category rendering
 * exactly, including its generic "field: value" fallback for any
 * non-builtin category (e.g. the Meeting template's agenda_topic/
 * action_item) — a fact's shape depends on the template that produced
 * it, so a renderer that only knows the 3 Phase-4 builtin categories'
 * fields renders "?" / "(?, due ?)" for anything else.
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
  const parts = Object.entries(value)
    .filter(([key, v]) => !["certainty", "evidence_segment_sequences"].includes(key) && v !== null && v !== "")
    .map(([key, v]) => `${key}: ${String(v)}`);
  return parts.length > 0 ? parts.join("; ") : "(no details)";
}
