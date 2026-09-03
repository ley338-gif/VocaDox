/**
 * Phase 5 Review Wizard (spec §28): works through open review issues one
 * at a time — "N found, i/N — [category] — AI: [value] — Evidence:
 * [segment] — [Audio] [Transcript] — [Confirm] [Correct] [Remove]".
 *
 * Each decision is a real HTTP call (app.documents.router
 * .resolve_review_issue_endpoint) recorded against the targeted fact —
 * never a purely cosmetic UI state. "Warum steht das hier?" (spec §30) is
 * answered ONLY with the real evidence shown below (source segment,
 * evidence type, jump-to-audio) — this component never asks an LLM to
 * explain or justify anything.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Pencil, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { resolveReviewIssue } from "../api/documents";
import { getFactEvidence, listFacts, listReviewIssues, type ExtractedFact } from "../api/intelligence";
import { useAuth } from "../auth/useAuth";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import type { AudioPlayerHandle } from "./AudioPlayer";
import styles from "./FactsPanel.module.css";

function severityTone(severity: string): "neutral" | "warning" | "danger" {
  if (severity === "critical" || severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "neutral";
}

function factValueSummary(fact: ExtractedFact | undefined): string {
  if (!fact) return "?";
  const value = fact.corrected_structured_value ?? fact.structured_value;
  if (fact.category === "general_fact") {
    return `${String(value.subject ?? "?")} — ${String(value.attribute ?? "?")}: ${String(value.value ?? "?")}`;
  }
  if (fact.category === "decision") return String(value.description ?? "?");
  return String(value.description ?? "?");
}

export function ReviewWizard({
  conversationId,
  audioPlayerRef,
}: {
  conversationId: string;
  audioPlayerRef: React.RefObject<AudioPlayerHandle | null>;
}) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [index, setIndex] = useState(0);
  const [targetFactId, setTargetFactId] = useState<string | null>(null);
  const [correctionDraft, setCorrectionDraft] = useState<string>("");
  const [showCorrection, setShowCorrection] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const issuesQuery = useQuery({
    queryKey: ["review-issues", conversationId],
    queryFn: () => listReviewIssues(conversationId),
  });
  const factsQuery = useQuery({
    queryKey: ["facts", conversationId],
    queryFn: () => listFacts(conversationId),
  });

  const openIssues = (issuesQuery.data ?? []).filter((i) => i.status === "open");
  const currentIssue = openIssues[index];
  const factsById = new Map((factsQuery.data ?? []).map((f) => [f.id, f]));

  useEffect(() => {
    if (currentIssue && !targetFactId) {
      setTargetFactId(currentIssue.related_fact_ids[0] ?? null);
    }
    if (currentIssue) {
      const fact = factsById.get(targetFactId ?? currentIssue.related_fact_ids[0]);
      setCorrectionDraft(JSON.stringify(fact?.structured_value ?? {}, null, 2));
    }
    setShowCorrection(false);
    setFormError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIssue?.id]);

  const evidenceQuery = useQuery({
    queryKey: ["fact-evidence", conversationId, targetFactId],
    queryFn: () => getFactEvidence(conversationId, targetFactId ?? ""),
    enabled: Boolean(targetFactId),
  });

  const resolveMutation = useMutation({
    mutationFn: (input: { action: "confirm" | "correct" | "remove"; corrected_value?: Record<string, unknown> }) =>
      resolveReviewIssue(
        conversationId,
        currentIssue.id,
        { fact_id: targetFactId ?? currentIssue.related_fact_ids[0], action: input.action, corrected_value: input.corrected_value },
        csrfToken ?? ""
      ),
    onSuccess: () => {
      setTargetFactId(null);
      setIndex(0); // the resolved issue drops out of the open list — restart at the new top
      void queryClient.invalidateQueries({ queryKey: ["review-issues", conversationId] });
      void queryClient.invalidateQueries({ queryKey: ["facts", conversationId] });
    },
  });

  if (issuesQuery.isLoading || factsQuery.isLoading) return <p>Loading review items…</p>;

  if (openIssues.length === 0) {
    return (
      <div>
        <h4>Review</h4>
        <p style={{ color: "var(--text-muted)" }}>
          <CheckCircle2 size={16} aria-hidden="true" /> No open review items. The document can be
          composed/approved once ready.
        </p>
      </div>
    );
  }

  const fact = factsById.get(targetFactId ?? currentIssue.related_fact_ids[0]);
  const canResolve = hasPermission("review-issue:resolve");

  return (
    <div>
      <h4>
        Review — {openIssues.length} found, {index + 1}/{openIssues.length}
      </h4>
      <div className={styles.item}>
        <div className={styles.header}>
          <AlertTriangle size={14} aria-hidden="true" />
          <Badge tone={severityTone(currentIssue.severity)}>{currentIssue.severity}</Badge>
          <Badge tone="neutral">{currentIssue.issue_type.replace(/_/g, " ")}</Badge>
          {currentIssue.uncertainty_category && (
            <Badge tone="purple">{currentIssue.uncertainty_category.replace(/_/g, " ")}</Badge>
          )}
        </div>
        <p>{currentIssue.description}</p>

        {currentIssue.related_fact_ids.length > 1 && (
          <div style={{ marginBottom: "var(--space-2)" }}>
            <span style={{ color: "var(--text-muted)" }}>Act on fact: </span>
            {currentIssue.related_fact_ids.map((fid) => (
              <button
                key={fid}
                type="button"
                onClick={() => setTargetFactId(fid)}
                style={{
                  marginRight: "var(--space-2)",
                  fontWeight: fid === targetFactId ? 700 : 400,
                  background: "none",
                  border: "1px solid var(--border-subtle, #e5e7eb)",
                  borderRadius: "var(--radius-sm)",
                  padding: "2px 8px",
                  cursor: "pointer",
                }}
              >
                {factValueSummary(factsById.get(fid))}
              </button>
            ))}
          </div>
        )}

        <p>
          <strong>AI:</strong> {factValueSummary(fact)}
        </p>

        {/* "Warum steht das hier?" (spec §30) — real evidence only, never an
            LLM explanation. */}
        <div className={styles.evidence}>
          <strong>Evidence:</strong>
          {evidenceQuery.data && evidenceQuery.data.length === 0 && (
            <p style={{ color: "var(--text-muted)" }}>
              No linked evidence — this fact could not be traced to a spoken segment.
            </p>
          )}
          {evidenceQuery.data?.map((ev) => (
            <button
              key={ev.id}
              type="button"
              className={styles.evidenceItem}
              onClick={() => ev.segment_start_ms !== null && audioPlayerRef.current?.seekToMs(ev.segment_start_ms)}
            >
              [{ev.evidence_type.replace("evidence_", "")}
              {ev.segment_start_ms !== null ? ` · ${Math.round(ev.segment_start_ms / 1000)}s` : ""}] &ldquo;
              {ev.segment_text}&rdquo; (Audio)
            </button>
          ))}
        </div>

        {canResolve && (
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)", flexWrap: "wrap" }}>
            <Button
              variant="primary"
              type="button"
              disabled={resolveMutation.isPending}
              onClick={() => resolveMutation.mutate({ action: "confirm" })}
            >
              <CheckCircle2 size={16} aria-hidden="true" /> Richtig
            </Button>
            <Button
              variant="secondary"
              type="button"
              disabled={resolveMutation.isPending}
              onClick={() => setShowCorrection((s) => !s)}
            >
              <Pencil size={16} aria-hidden="true" /> Korrigieren
            </Button>
            <Button
              variant="destructive"
              type="button"
              disabled={resolveMutation.isPending}
              onClick={() => resolveMutation.mutate({ action: "remove" })}
            >
              <XCircle size={16} aria-hidden="true" /> Entfernen
            </Button>
          </div>
        )}

        {showCorrection && (
          <div style={{ marginTop: "var(--space-3)" }}>
            <textarea
              value={correctionDraft}
              onChange={(event) => setCorrectionDraft(event.target.value)}
              rows={6}
              style={{ width: "100%", fontFamily: "monospace" }}
              aria-label="Corrected value (JSON)"
            />
            {formError && (
              <p role="alert" style={{ color: "var(--color-danger, #b91c1c)" }}>
                {formError}
              </p>
            )}
            <Button
              variant="primary"
              type="button"
              disabled={resolveMutation.isPending}
              onClick={() => {
                try {
                  const parsed = JSON.parse(correctionDraft) as Record<string, unknown>;
                  setFormError(null);
                  resolveMutation.mutate({ action: "correct", corrected_value: parsed });
                } catch {
                  setFormError("Invalid JSON — fix the corrected value before saving.");
                }
              }}
            >
              Save correction
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
