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
import { GitCompare } from "lucide-react";
import { useNavigate } from "react-router";

import {
  getExternalReferenceComparison,
  getExternalReferenceTimeline,
  type ComparisonStatus,
  type TimelineEntry,
} from "../api/longitudinal";
import { Badge } from "../design-system/Badge";
import { EmptyState, Skeleton } from "../design-system/States";
import { DataTable, type DataTableColumn } from "../design-system/Table";
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

const TIMELINE_COLUMNS = (conversationId: string): DataTableColumn<TimelineEntry>[] => [
  {
    key: "title",
    header: "Gespräch",
    render: (row) => (
      <>
        {row.title}
        {row.conversation_id === conversationId && (
          <Badge tone="info"> aktuell</Badge>
        )}
      </>
    ),
  },
  {
    key: "occurred_at",
    header: "Datum",
    render: (row) => new Date(row.occurred_at).toLocaleDateString(),
    sortable: true,
    sortValue: (row) => row.occurred_at,
  },
  { key: "fact_count", header: "Fakten", render: (row) => row.fact_count, align: "right" },
];

export function LongitudinalPanel({
  conversationId,
  organizationId,
  externalReference,
}: {
  conversationId: string;
  organizationId: string;
  externalReference: string | null;
}) {
  const navigate = useNavigate();
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
      <EmptyState
        icon={<GitCompare size={20} aria-hidden="true" />}
        title="Keine externe Referenz gesetzt"
        description="Dieses Gespräch hat keine externe Referenz und kann daher nicht mit anderen Gesprächen gruppiert werden. Eine Referenz (z. B. Fall-/Patienten-/Kunden-ID) in den Details setzen, um Verlauf/Vergleich zu aktivieren."
      />
    );
  }

  return (
    <div>
      <h4>Verlauf — Referenz „{externalReference}“</h4>
      {timelineQuery.isLoading ? (
        <Skeleton height="4rem" />
      ) : (
        <DataTable
          columns={TIMELINE_COLUMNS(conversationId)}
          rows={timelineQuery.data?.conversations ?? []}
          keyExtractor={(row) => row.conversation_id}
          onRowClick={(row) => navigate(`/app/conversations/${row.conversation_id}`)}
          empty={<EmptyState title="Keine weiteren Gespräche mit dieser Referenz" />}
        />
      )}

      <h4 style={{ marginTop: "var(--space-6)" }}>Vergleich</h4>
      <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-3)" }}>
        Deterministischer, struktureller Vergleich ausschließlich über extrahierte Fakten — nie eine
        KI-generierte Zusammenfassung von „was sich geändert hat“.
      </p>
      {comparisonQuery.isLoading && <Skeleton height="4rem" />}
      {comparisonQuery.data && comparisonQuery.data.items.length === 0 && (
        <EmptyState
          title="Keine Unterschiede festgestellt"
          description={`Über ${comparisonQuery.data.conversation_count} Gespräch(e) hinweg.`}
        />
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
              {item.prior_value !== null && <span>vorher: {item.prior_value}</span>}
              {item.prior_value !== null && item.current_value !== null && <span> → </span>}
              {item.current_value !== null && <span>aktuell: {item.current_value}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
