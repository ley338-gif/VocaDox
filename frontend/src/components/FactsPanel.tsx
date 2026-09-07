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
  redactFact,
  triggerExtraction,
  unredactFact,
  type ExtractedFact,
  type ReviewIssueSeverity,
} from "../api/intelligence";
import { useAuth } from "../auth/useAuth";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { EmptyState, ProcessingBanner, Skeleton, Spinner } from "../design-system/States";
import { factSummary } from "../lib/factSummary";
import type { AudioPlayerHandle } from "./AudioPlayer";
import styles from "./FactsPanel.module.css";

function severityTone(severity: ReviewIssueSeverity): "neutral" | "warning" | "danger" {
  if (severity === "critical" || severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "neutral";
}

function FactRow({
  fact,
  conversationId,
  audioPlayerRef,
  canRedact,
  onToggleRedaction,
}: {
  fact: ExtractedFact;
  conversationId: string;
  audioPlayerRef: React.RefObject<AudioPlayerHandle | null>;
  canRedact: boolean;
  onToggleRedaction: (fact: ExtractedFact) => void;
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
          {fact.is_redacted && <Badge tone="danger">geschwärzt</Badge>}
        </button>
        {canRedact && (
          <Button variant="tertiary" type="button" onClick={() => onToggleRedaction(fact)}>
            {fact.is_redacted ? "Schwärzung aufheben" : "Schwärzen"}
          </Button>
        )}
      </div>
      <p style={{ margin: "var(--space-1) 0" }}>{factSummary(fact.category, fact.structured_value)}</p>
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

  const redactionMutation = useMutation({
    mutationFn: (fact: ExtractedFact) =>
      fact.is_redacted
        ? unredactFact(conversationId, fact.id, undefined, csrfToken ?? "")
        : redactFact(conversationId, fact.id, undefined, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["facts", conversationId] }),
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
            {extractMutation.isPending ? <Spinner size={16} /> : <Sparkles size={16} aria-hidden="true" />}{" "}
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

      {extractMutation.isPending && (
        <ProcessingBanner
          title="Fakten werden extrahiert…"
          description="Das Sprachmodell analysiert das Transkript — das kann bis zu einer Minute dauern."
        />
      )}
      {extractMutation.isError && (
        <p role="alert" style={{ color: "var(--color-danger)", marginBottom: "var(--space-4)" }}>
          Extraktion fehlgeschlagen:{" "}
          {extractMutation.error instanceof Error ? extractMutation.error.message : "Unbekannter Fehler"}
        </p>
      )}

      {factsQuery.isLoading && <Skeleton height="4rem" />}
      {factsQuery.data && factsQuery.data.length === 0 && <EmptyState title="Noch keine Fakten extrahiert" />}
      <ul className={styles.list}>
        {factsQuery.data?.map((fact) => (
          <FactRow
            key={fact.id}
            fact={fact}
            conversationId={conversationId}
            audioPlayerRef={audioPlayerRef}
            canRedact={hasPermission("fact:redact")}
            onToggleRedaction={(f) => redactionMutation.mutate(f)}
          />
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
