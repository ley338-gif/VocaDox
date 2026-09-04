/**
 * Phase 9 "Related" tab: Timeline (every conversation sharing this
 * conversation's `external_reference`, scoped to its organization — see
 * app.longitudinal.service's cross-organization isolation rule) and
 * Comparison (deterministic NEW/CHANGED/NOT_MENTIONED/CONTRADICTED facts,
 * each linked to both underlying evidence points where both exist).
 * Deliberately minimal — no LLM-generated "what changed" narrative, per
 * spec §40's "Keine unbelegte Interpretation von Aenderungen".
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import {
  getExternalReferenceComparison,
  getExternalReferenceTimeline,
  type ComparisonStatus,
} from "../api/longitudinal";
import { Badge } from "../design-system/Badge";
import styles from "./LongitudinalPanel.module.css";

function comparisonTone(status: ComparisonStatus): "info" | "warning" | "danger" | "success" {
  switch (status) {
    case "new":
      return "success";
    case "changed":
      return "info";
    case "contradicted":
      return "danger";
    case "not_mentioned":
    default:
      return "warning";
  }
}

export function LongitudinalPanel({
  conversationId,
  organizationId,
  externalReference,
}: {
  conversationId: string;
  organizationId: string;
  externalReference: string | null;
}) {
  const timelineQuery = useQuery({
    queryKey: ["longitudinal-timeline", organizationId, externalReference],
    queryFn: () => getExternalReferenceTimeline(externalReference ?? "", organizationId),
    enabled: Boolean(externalReference),
  });
  const comparisonQuery = useQuery({
    queryKey: ["longitudinal-comparison", organizationId, externalReference],
    queryFn: () => getExternalReferenceComparison(externalReference ?? "", organizationId),
    enabled: Boolean(externalReference),
  });

  if (!externalReference) {
    return (
      <p style={{ color: "var(--text-muted)" }}>
        This conversation has no external reference set, so it cannot be grouped with any other
        conversation. Set one (e.g. a case/patient/client ID) in the conversation&apos;s details to
        enable Timeline/Comparison.
      </p>
    );
  }

  return (
    <div>
      <h4>Timeline — reference &quot;{externalReference}&quot;</h4>
      {timelineQuery.isLoading && <p>Loading timeline…</p>}
      <ul className={styles.list}>
        {timelineQuery.data?.conversations.map((entry) => (
          <li
            key={entry.conversation_id}
            className={`${styles.item} ${entry.conversation_id === conversationId ? styles.itemActive : ""}`}
          >
            <Link to={`/app/conversations/${entry.conversation_id}`}>{entry.title}</Link>
            <span style={{ color: "var(--text-muted)" }}>
              {new Date(entry.occurred_at).toLocaleDateString()} · {entry.fact_count} facts
            </span>
          </li>
        ))}
      </ul>

      <h4 style={{ marginTop: "var(--space-5)" }}>Comparison</h4>
      <p style={{ color: "var(--text-muted)" }}>
        Deterministic, structural comparison over extracted facts only — never an AI-generated
        summary of "what changed."
      </p>
      {comparisonQuery.isLoading && <p>Loading comparison…</p>}
      {comparisonQuery.data && comparisonQuery.data.items.length === 0 && (
        <p>No differences detected across {comparisonQuery.data.conversation_count} conversation(s).</p>
      )}
      <ul className={styles.list}>
        {comparisonQuery.data?.items.map((item, idx) => (
          <li key={idx} className={styles.comparisonRow}>
            <div className={styles.comparisonHeader}>
              <Badge tone={comparisonTone(item.status)}>{item.status.replace("_", " ")}</Badge>
              <strong>
                {item.subject} — {item.attribute}
              </strong>
              <span style={{ color: "var(--text-muted)" }}>in {item.conversation_title}</span>
            </div>
            <div className={styles.comparisonValues}>
              {item.prior_value !== null && <span>previous: {item.prior_value}</span>}
              {item.prior_value !== null && item.current_value !== null && <span> → </span>}
              {item.current_value !== null && <span>current: {item.current_value}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
