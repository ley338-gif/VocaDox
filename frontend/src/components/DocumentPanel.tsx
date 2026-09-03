/**
 * Phase 5 Document tab: compose a document from the conversation's current
 * facts, show the current revision (every statement traces back to the
 * fact id(s) it came from — click one to jump to its evidence in the
 * Review tab's mental model), list revision history, approve (visibly
 * blocked with the real reason when unresolved HIGH/CRITICAL review
 * issues remain), and export (text/JSON).
 *
 * Composition is deterministic — see backend app.documents.service's
 * docstring — never an LLM "write a report" call. This panel never
 * fabricates an explanation for why a statement is in the document; the
 * "why" is exactly its fact_ids, cross-referenced against the Review tab.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, FileText, RefreshCw } from "lucide-react";
import { useState } from "react";

import {
  approveDocument,
  composeDocument,
  fetchDocumentExport,
  getDocument,
  listDocumentRevisions,
} from "../api/documents";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import styles from "./FactsPanel.module.css";

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "approved") return "success";
  if (status === "ready_for_approval") return "info";
  if (status === "review_required") return "warning";
  return "neutral";
}

export function DocumentPanel({ conversationId }: { conversationId: string }) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [approveError, setApproveError] = useState<string | null>(null);

  const documentQuery = useQuery({
    queryKey: ["document", conversationId],
    queryFn: () => getDocument(conversationId),
    retry: false,
  });
  const revisionsQuery = useQuery({
    queryKey: ["document-revisions", conversationId],
    queryFn: () => listDocumentRevisions(conversationId),
    enabled: documentQuery.isSuccess,
  });

  const composeMutation = useMutation({
    mutationFn: () => composeDocument(conversationId, csrfToken ?? ""),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["document", conversationId] });
      void queryClient.invalidateQueries({ queryKey: ["document-revisions", conversationId] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => approveDocument(conversationId, csrfToken ?? ""),
    onSuccess: () => {
      setApproveError(null);
      void queryClient.invalidateQueries({ queryKey: ["document", conversationId] });
      void queryClient.invalidateQueries({ queryKey: ["document-revisions", conversationId] });
    },
    onError: (error: unknown) => {
      setApproveError(error instanceof ApiError ? error.message : "Approval failed.");
    },
  });

  const handleExport = async (format: "text" | "json") => {
    const content = await fetchDocumentExport(conversationId, format);
    const blob = new Blob([content], { type: format === "json" ? "application/json" : "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = window.document.createElement("a");
    a.href = url;
    a.download = `document-${conversationId}.${format === "json" ? "json" : "txt"}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const document = documentQuery.data;
  const revision = document?.current_revision ?? null;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-4)" }}>
        <h4 style={{ margin: 0 }}>Document</h4>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          {hasPermission("document:edit") && (
            <Button
              variant="secondary"
              type="button"
              disabled={composeMutation.isPending}
              onClick={() => composeMutation.mutate()}
            >
              <RefreshCw size={16} aria-hidden="true" />{" "}
              {revision ? "Recompose" : composeMutation.isPending ? "Composing…" : "Compose document"}
            </Button>
          )}
          {revision && (
            <>
              <Button variant="tertiary" type="button" onClick={() => void handleExport("text")}>
                <Download size={16} aria-hidden="true" /> Export .txt
              </Button>
              <Button variant="tertiary" type="button" onClick={() => void handleExport("json")}>
                <Download size={16} aria-hidden="true" /> Export .json
              </Button>
            </>
          )}
        </div>
      </div>

      {documentQuery.isError && (
        <p style={{ color: "var(--text-muted)" }}>
          No document composed yet. This is a deterministic rendering of the conversation&apos;s
          current facts — never an AI-generated report.
        </p>
      )}

      {revision && (
        <div className={styles.item} style={{ marginBottom: "var(--space-4)" }}>
          <div className={styles.header}>
            <FileText size={16} aria-hidden="true" />
            <Badge tone={statusTone(revision.status)}>{revision.status.replace(/_/g, " ")}</Badge>
            <span style={{ color: "var(--text-muted)" }}>Revision {revision.revision_number}</span>
            {revision.status === "approved" && (
              <Badge tone="success">
                <CheckCircle2 size={12} aria-hidden="true" /> Approved
              </Badge>
            )}
          </div>

          {revision.status === "review_required" && (
            <p style={{ color: "var(--text-muted)" }}>
              {revision.blocking_issue_ids.length} unresolved high/critical review issue(s) block
              approval — resolve them in the Review tab, then recompose.
            </p>
          )}

          <pre
            style={{
              whiteSpace: "pre-wrap",
              fontFamily: "inherit",
              background: "var(--surface-muted, #f8fafc)",
              padding: "var(--space-3)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            {revision.rendered_text}
          </pre>

          {hasPermission("document:approve") && revision.status !== "approved" && (
            <div style={{ marginTop: "var(--space-3)" }}>
              <Button
                variant="primary"
                type="button"
                disabled={revision.status !== "ready_for_approval" || approveMutation.isPending}
                onClick={() => approveMutation.mutate()}
              >
                <CheckCircle2 size={16} aria-hidden="true" />{" "}
                {approveMutation.isPending ? "Approving…" : "Approve document"}
              </Button>
              {revision.status !== "ready_for_approval" && (
                <p style={{ color: "var(--text-muted)", margin: "var(--space-1) 0 0" }}>
                  Not ready for approval yet — resolve open review issues and recompose first.
                </p>
              )}
              {approveError && (
                <p role="alert" style={{ color: "var(--color-danger, #b91c1c)" }}>
                  {approveError}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {revisionsQuery.data && revisionsQuery.data.length > 0 && (
        <>
          <h4>Revision history</h4>
          <ul className={styles.list}>
            {revisionsQuery.data.map((r) => (
              <li key={r.id} className={styles.item}>
                <div className={styles.header}>
                  <span>Revision {r.revision_number}</span>
                  <Badge tone={statusTone(r.status)}>{r.status.replace(/_/g, " ")}</Badge>
                  <span style={{ color: "var(--text-muted)" }}>
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                  {r.approved_at && (
                    <span style={{ color: "var(--text-muted)" }}>
                      approved {new Date(r.approved_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
