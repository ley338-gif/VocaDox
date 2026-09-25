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
import { useEffect, useRef, useState } from "react";

import {
  getFactEvidence,
  listFacts,
  listReviewIssues,
  redactFact,
  triggerExtraction,
  unredactFact,
  type ExtractedFact,
} from "../api/intelligence";
import { getProcessingStatus } from "../api/transcription";
import { useAuth } from "../auth/useAuth";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { EmptyState, ProcessingBanner, Skeleton, Spinner } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { factSummary } from "../lib/factSummary";
import type { AudioPlayerHandle } from "./AudioPlayer";
import styles from "./FactsPanel.module.css";

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

// error_message_safe is an exception class name — not something to show a
// user — so the failure is explained by its FailureClass instead.
function extractionFailureMessage(failureClass: string | null): string {
  switch (failureClass) {
    case "model_unavailable":
      return "Das Sprachmodell ist nicht verfügbar. Bitte die LLM-Konfiguration prüfen.";
    case "transient":
    case "resource":
      return "Das Sprachmodell war wiederholt nicht erreichbar. Bitte später erneut versuchen.";
    default:
      return "Die Extraktion konnte nicht abgeschlossen werden.";
  }
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

  // The extract endpoint only enqueues a job (202, returns immediately),
  // so `extractMutation.isPending` is over within milliseconds. "Is
  // extraction running" is answered by the job list instead, polled while
  // an extract job is queued/running — same pattern as ProtocolPanel.
  const processingQuery = useQuery({
    queryKey: ["processing-status", conversationId],
    queryFn: () => getProcessingStatus(conversationId),
    refetchInterval: (query) => {
      const jobs = query.state.data?.jobs ?? [];
      const active = jobs.some(
        (j) => j.job_type === "extract" && (j.status === "queued" || j.status === "running")
      );
      return active ? 1500 : false;
    },
  });

  // `jobs` is ordered by queued_at DESC, so the first extract entry is the
  // most recent attempt.
  const latestJob = processingQuery.data?.jobs.find((j) => j.job_type === "extract");
  const isExtracting = latestJob?.status === "queued" || latestJob?.status === "running";
  const [jobError, setJobError] = useState<string | null>(null);
  // Id of the last extract job whose completion we already reacted to, so
  // the effect fires once per job instead of on every poll tick.
  const lastHandledJobRef = useRef<string | null>(null);

  useEffect(() => {
    if (!latestJob) return;
    if (latestJob.status !== "succeeded" && latestJob.status !== "failed") return;
    if (lastHandledJobRef.current === latestJob.id) return;
    lastHandledJobRef.current = latestJob.id;
    if (latestJob.status === "succeeded") {
      setJobError(null);
      void queryClient.invalidateQueries({ queryKey: ["facts", conversationId] });
      void queryClient.invalidateQueries({ queryKey: ["review-issues", conversationId] });
    } else {
      setJobError(extractionFailureMessage(latestJob.failure_class));
    }
  }, [latestJob, conversationId, queryClient]);

  const extractMutation = useMutation({
    mutationFn: () => triggerExtraction(conversationId, csrfToken ?? ""),
    onSuccess: () => {
      setJobError(null);
      void queryClient.invalidateQueries({ queryKey: ["processing-status", conversationId] });
    },
  });
  const isBusy = extractMutation.isPending || isExtracting;

  const redactionMutation = useMutation({
    mutationFn: (fact: ExtractedFact) =>
      fact.is_redacted
        ? unredactFact(conversationId, fact.id, undefined, csrfToken ?? "")
        : redactFact(conversationId, fact.id, undefined, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["facts", conversationId] }),
  });

  return (
    <div>
      <Card
        title="Extrahierte Fakten"
        actions={
          hasPermission("fact:extract") && (
            <Button
              variant="primary"
              type="button"
              disabled={isBusy}
              onClick={() => extractMutation.mutate()}
            >
              {isBusy ? <Spinner size={16} /> : <Sparkles size={16} aria-hidden="true" />}{" "}
              {isBusy ? "Extrahiere…" : "Fakten extrahieren"}
            </Button>
          )
        }
      >
        <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-4)" }}>
          Automatisch erstellt — maschinell abgeleitete Fakten aus dem Transkript dieses Gesprächs.
          Jeder Fakt verweist auf den genauen gesprochenen Moment — auf einen Fakt klicken, um die
          Evidenz zu sehen. Dies ist kein generiertes Dokument; siehe die Review-Hinweise unten für
          Unsicheres oder möglicherweise Widersprüchliches.
        </p>

        {isBusy && (
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
        {!isBusy && jobError && (
          <p role="alert" style={{ color: "var(--color-danger)", marginBottom: "var(--space-4)" }}>
            Extraktion fehlgeschlagen: {jobError}
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
      </Card>

      <div style={{ marginTop: "var(--space-6)" }}>
        <Card title="Review-Hinweise">
          {issuesQuery.data && issuesQuery.data.length === 0 && (
            <p style={{ color: "var(--text-muted)" }}>Keine offenen Review-Hinweise.</p>
          )}
          <ul className={styles.list}>
            {issuesQuery.data?.map((issue) => (
              <li key={issue.id} className={styles.item}>
                <div className={styles.header}>
                  <AlertTriangle size={16} aria-hidden="true" />
                  <StatusBadge status={issue.severity} />
                  <Badge tone="neutral">{issue.issue_type.replace("_", " ")}</Badge>
                </div>
                <p style={{ margin: "var(--space-1) 0" }}>{issue.description}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
