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
 *
 * Redesign note: the brief's "split view: transcript left, document
 * right" is genuinely implemented at the Review tab (ReviewWizard already
 * shows per-issue evidence with jump-to-audio); this panel's revision
 * text has no per-statement evidence links to click today, so a literal
 * transcript/document split here would be cosmetic, not real evidence
 * tracing — kept single-column, restyled with the shared design system
 * instead of a hollow split view.
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
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { EmptyState, ErrorState, Skeleton } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { DocumentContent } from "./DocumentContent";
import panelStyles from "./FactsPanel.module.css";

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
      setApproveError(error instanceof ApiError ? error.message : "Freigabe fehlgeschlagen.");
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
        <h4 style={{ margin: 0 }}>Dokumentation</h4>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          {hasPermission("document:edit") && (
            <Button
              variant="secondary"
              type="button"
              disabled={composeMutation.isPending}
              onClick={() => composeMutation.mutate()}
            >
              <RefreshCw size={16} aria-hidden="true" />{" "}
              {revision ? "Neu zusammenstellen" : composeMutation.isPending ? "Wird erstellt…" : "Dokument erstellen"}
            </Button>
          )}
          {revision && (
            <>
              <Button variant="tertiary" type="button" onClick={() => void handleExport("text")}>
                <Download size={16} aria-hidden="true" /> .txt
              </Button>
              <Button variant="tertiary" type="button" onClick={() => void handleExport("json")}>
                <Download size={16} aria-hidden="true" /> .json
              </Button>
            </>
          )}
        </div>
      </div>

      {documentQuery.isLoading && <Skeleton height="8rem" />}

      {documentQuery.isError && (
        <EmptyState
          icon={<FileText size={20} aria-hidden="true" />}
          title="Noch kein Dokument erstellt"
          description="Automatisch erstellt — eine deterministische Darstellung der aktuellen Fakten dieses Gesprächs, nie ein KI-generierter Bericht."
        />
      )}

      {revision && (
        <Card
          title={`Revision ${revision.revision_number}`}
          actions={
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <StatusBadge status={revision.status} />
              {revision.status === "approved" && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--color-success)" }}>
                  <CheckCircle2 size={14} aria-hidden="true" />
                </span>
              )}
            </div>
          }
        >
          {revision.status === "review_required" && (
            <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-3)" }}>
              {revision.blocking_issue_ids.length} ungelöste(r) Review-Hinweis(e) mit hoher/kritischer
              Priorität blockieren die Freigabe — im Review-Tab lösen, dann neu zusammenstellen.
            </p>
          )}

          <DocumentContent sections={revision.structured_content} />

          {hasPermission("document:approve") && revision.status !== "approved" && (
            <div style={{ marginTop: "var(--space-4)" }}>
              <Button
                variant="primary"
                type="button"
                disabled={revision.status !== "ready_for_approval" || approveMutation.isPending}
                onClick={() => approveMutation.mutate()}
              >
                <CheckCircle2 size={16} aria-hidden="true" />{" "}
                {approveMutation.isPending ? "Wird freigegeben…" : "Dokument freigeben"}
              </Button>
              {revision.status !== "ready_for_approval" && (
                <p style={{ color: "var(--text-muted)", margin: "var(--space-1) 0 0" }}>
                  Noch nicht freigabebereit — offene Review-Hinweise lösen und neu zusammenstellen.
                </p>
              )}
              {approveError && <ErrorState message={approveError} />}
            </div>
          )}
        </Card>
      )}

      {revisionsQuery.data && revisionsQuery.data.length > 0 && (
        <>
          <h4 style={{ marginTop: "var(--space-6)" }}>Revisionsverlauf</h4>
          <ul className={panelStyles.list}>
            {revisionsQuery.data.map((r) => (
              <li key={r.id} className={panelStyles.item}>
                <div className={panelStyles.header}>
                  <span>Revision {r.revision_number}</span>
                  <StatusBadge status={r.status} />
                  <span style={{ color: "var(--text-muted)" }}>
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                  {r.approved_at && (
                    <span style={{ color: "var(--text-muted)" }}>
                      freigegeben {new Date(r.approved_at).toLocaleString()}
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
