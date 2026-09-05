/**
 * Phase 4 Facts tab: trigger extraction, list extracted facts with their
 * evidence (jump-to-segment reuses the same audio-seek mechanism as
 * TranscriptPanel), and list review issues (uncertainty/contradiction
 * flags). Deliberately minimal — this is NOT the Phase 5 Evidence UX
 * (no two-column DOCUMENT/EVIDENCE layout, no "Warum steht das hier?"
 * panel, no correction/approval workflow) — see
 * docs/architecture/future-considerations.md.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronRight, Sparkles } from "lucide-react";
import { useState } from "react";

import {
  getFactEvidence,
  listFacts,
  listReviewIssues,
  triggerExtraction,
  type ExtractedFact,
  type ReviewIssueSeverity,
} from "../api/intelligence";
import { useAuth } from "../auth/useAuth";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { EmptyState, Skeleton } from "../design-system/States";
import type { AudioPlayerHandle } from "./AudioPlayer";
import styles from "./FactsPanel.module.css";

function severityTone(severity: ReviewIssueSeverity): "neutral" | "warning" | "danger" {
  if (severity === "critical" || severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "neutral";
}

function factSummary(fact: ExtractedFact): string {
  const v = fact.structured_value;
  if (fact.category === "general_fact") {
    return `${String(v.subject ?? "?")} — ${String(v.attribute ?? "?")}: ${String(v.value ?? "?")}`;
  }
  if (fact.category === "decision") {
    return String(v.description ?? "?");
  }
  return `${String(v.description ?? "?")} (${String(v.assignee ?? "?")}, due ${String(v.due_date ?? "?")})`;
}

function FactRow({
  fact,
  conversationId,
  audioPlayerRef,
}: {
  fact: ExtractedFact;
  conversationId: string;
  audioPlayerRef: React.RefObject<AudioPlayerHandle | null>;
}) {
  const [expanded, setExpanded] = useState(false);
  const evidenceQuery = useQuery({
    queryKey: ["fact-evidence", conversationId, fact.id],
    queryFn: () => getFactEvidence(conversationId, fact.id),
    enabled: expanded,
  });

  return (
    <li className={styles.item}>
      <div className={styles.header}>
        <button
          type="button"
          className={styles.headerButton}
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
        >
          {expanded ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
          <Badge tone="purple">{fact.category.replace("_", " ")}</Badge>
          <Badge tone={fact.status === "verified" ? "success" : "warning"}>{fact.status}</Badge>
          {fact.certainty !== "stated" && <Badge tone="neutral">{fact.certainty.replace("_", " ")}</Badge>}
        </button>
      </div>
      <p style={{ margin: "var(--space-1) 0" }}>{factSummary(fact)}</p>
      {expanded && (
        <div className={styles.evidence}>
          {evidenceQuery.isLoading && <Skeleton height="1rem" />}
          {evidenceQuery.data && evidenceQuery.data.length === 0 && (
            <p style={{ color: "var(--text-muted)" }}>Keine verknüpfte Evidenz — dieser Fakt ist unverifiziert.</p>
          )}
          {evidenceQuery.data?.map((ev) => (
            <button
              key={ev.id}
              type="button"
              className={styles.evidenceItem}
              onClick={() => ev.segment_start_ms !== null && audioPlayerRef.current?.seekToMs(ev.segment_start_ms)}
            >
              &ldquo;{ev.segment_text}&rdquo;
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

export function FactsPanel({
  conversationId,
  audioPlayerRef,
}: {
  conversationId: string;
  audioPlayerRef: React.RefObject<AudioPlayerHandle | null>;
}) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();

  const factsQuery = useQuery({
    queryKey: ["facts", conversationId],
    queryFn: () => listFacts(conversationId),
  });
  const issuesQuery = useQuery({
    queryKey: ["review-issues", conversationId],
    queryFn: () => listReviewIssues(conversationId),
  });

  const extractMutation = useMutation({
    mutationFn: () => triggerExtraction(conversationId, csrfToken ?? ""),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["facts", conversationId] });
      void queryClient.invalidateQueries({ queryKey: ["review-issues", conversationId] });
    },
  });

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-4)" }}>
        <h4 style={{ margin: 0 }}>Extrahierte Fakten</h4>
        {hasPermission("fact:extract") && (
          <Button
            variant="primary"
            type="button"
            disabled={extractMutation.isPending}
            onClick={() => extractMutation.mutate()}
          >
            <Sparkles size={16} aria-hidden="true" />{" "}
            {extractMutation.isPending ? "Extrahiere…" : "Fakten extrahieren"}
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-4)" }}>
        Automatisch erstellt — maschinell abgeleitete Fakten aus dem Transkript dieses Gesprächs.
        Jeder Fakt verweist auf den genauen gesprochenen Moment — auf einen Fakt klicken, um die
        Evidenz zu sehen. Dies ist kein generiertes Dokument; siehe die Review-Hinweise unten für
        Unsicheres oder möglicherweise Widersprüchliches.
      </p>

      {factsQuery.isLoading && <Skeleton height="4rem" />}
      {factsQuery.data && factsQuery.data.length === 0 && <EmptyState title="Noch keine Fakten extrahiert" />}
      <ul className={styles.list}>
        {factsQuery.data?.map((fact) => (
          <FactRow key={fact.id} fact={fact} conversationId={conversationId} audioPlayerRef={audioPlayerRef} />
        ))}
      </ul>

      <h4 style={{ marginTop: "var(--space-6)" }}>Review-Hinweise</h4>
      {issuesQuery.data && issuesQuery.data.length === 0 && (
        <p style={{ color: "var(--text-muted)" }}>Keine offenen Review-Hinweise.</p>
      )}
      <ul className={styles.list}>
        {issuesQuery.data?.map((issue) => (
          <li key={issue.id} className={styles.item}>
            <div className={styles.header}>
              <AlertTriangle size={14} aria-hidden="true" />
              <Badge tone={severityTone(issue.severity)}>{issue.severity}</Badge>
              <Badge tone="neutral">{issue.issue_type.replace("_", " ")}</Badge>
            </div>
            <p style={{ margin: "var(--space-1) 0" }}>{issue.description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
