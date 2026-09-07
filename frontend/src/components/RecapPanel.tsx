/**
 * Post-GA: the shareable, participant-facing Recap tab. Explicitly
 * labeled as AI-generated everywhere it's shown — this is a real LLM
 * narrative (unlike the deterministic Dokumentation tab) and must be
 * human-approved before export/sharing.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, RefreshCw, Sparkles } from "lucide-react";

import { approveRecap, generateRecap, getRecap, recapExportUrl } from "../api/recap";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { EmptyState, ErrorState, Skeleton } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import styles from "./RecapPanel.module.css";

export function RecapPanel({ conversationId }: { conversationId: string }) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();

  const recapQuery = useQuery({
    queryKey: ["recap", conversationId],
    queryFn: () => getRecap(conversationId),
    retry: false,
  });

  const generateMutation = useMutation({
    mutationFn: () => generateRecap(conversationId, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["recap", conversationId] }),
  });

  const approveMutation = useMutation({
    mutationFn: () => approveRecap(conversationId, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["recap", conversationId] }),
  });

  const revision = recapQuery.data?.current_revision ?? null;
  const notComposable =
    generateMutation.error instanceof ApiError && generateMutation.error.status === 409;

  return (
    <div>
      <div className={styles.header}>
        <h4 style={{ margin: 0 }}>Recap für Teilnehmer</h4>
        {hasPermission("recap:generate") && (
          <Button
            variant="secondary"
            type="button"
            disabled={generateMutation.isPending}
            onClick={() => generateMutation.mutate()}
          >
            <RefreshCw size={16} aria-hidden="true" />{" "}
            {revision ? "Neu erstellen" : generateMutation.isPending ? "Wird erstellt…" : "Recap erstellen"}
          </Button>
        )}
      </div>

      <p className={styles.disclosure}>
        <Sparkles size={13} aria-hidden="true" /> KI-generiert aus der Dokumentation dieses
        Gesprächs — vor dem Teilen prüfen. Kein Ersatz für die Dokumentation, sondern ein
        kurzer, leicht verständlicher Text zum Weitergeben an die Gesprächspartner:in.
      </p>

      {recapQuery.isLoading && <Skeleton height="6rem" />}

      {recapQuery.isError && !notComposable && (
        <EmptyState
          icon={<Sparkles size={20} aria-hidden="true" />}
          title="Noch kein Recap erstellt"
          description="Erstellt einen KI-Entwurf auf Basis der aktuellen Dokumentation."
        />
      )}

      {notComposable && (
        <ErrorState
          title="Dokumentation fehlt noch"
          message="Das Recap wird aus der Dokumentation erstellt — zuerst im Dokumentation-Tab zusammenstellen."
        />
      )}

      {revision && (
        <Card
          title={`Revision ${revision.revision_number}`}
          actions={<StatusBadge status={revision.status} />}
        >
          <p className={styles.content}>{revision.content}</p>

          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
            {hasPermission("recap:approve") && revision.status !== "approved" && (
              <Button
                variant="primary"
                type="button"
                disabled={approveMutation.isPending}
                onClick={() => approveMutation.mutate()}
              >
                <CheckCircle2 size={16} aria-hidden="true" />{" "}
                {approveMutation.isPending ? "Wird freigegeben…" : "Freigeben"}
              </Button>
            )}
            {revision.status === "approved" && (
              <>
                <a
                  className={styles.exportLink}
                  href={recapExportUrl(conversationId, "text")}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Download size={16} aria-hidden="true" /> Als Text exportieren
                </a>
                <a className={styles.exportLink} href={recapExportUrl(conversationId, "docx")}>
                  <Download size={16} aria-hidden="true" /> .docx
                </a>
                <a className={styles.exportLink} href={recapExportUrl(conversationId, "pdf")}>
                  <Download size={16} aria-hidden="true" /> .pdf
                </a>
              </>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
