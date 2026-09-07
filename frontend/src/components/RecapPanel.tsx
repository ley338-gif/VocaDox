/**
 * Post-GA: the shareable, participant-facing Recap tab. Explicitly
 * labeled as AI-generated everywhere it's shown — this is a real LLM
 * narrative (unlike the deterministic Dokumentation tab) and must be
 * human-approved before export/sharing.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, Download, Link2, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";

import {
  approveRecap,
  createShareLink,
  generateRecap,
  getRecap,
  listShareLinks,
  recapExportUrl,
  revokeShareLink,
} from "../api/recap";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { Select } from "../design-system/FormControls";
import { EmptyState, ErrorState, Skeleton, Spinner } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import styles from "./RecapPanel.module.css";

const TTL_OPTIONS = [
  { label: "24 Stunden", hours: 24 },
  { label: "7 Tage", hours: 24 * 7 },
  { label: "30 Tage", hours: 24 * 30 },
];

function formatExpiry(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ShareLinksSection({ conversationId }: { conversationId: string }) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [ttlHours, setTtlHours] = useState(TTL_OPTIONS[1].hours);

  const linksQuery = useQuery({
    queryKey: ["recap-share-links", conversationId],
    queryFn: () => listShareLinks(conversationId),
  });

  const createMutation = useMutation({
    mutationFn: () => createShareLink(conversationId, ttlHours, csrfToken ?? ""),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["recap-share-links", conversationId] }),
  });

  const revokeMutation = useMutation({
    mutationFn: (linkId: string) => revokeShareLink(conversationId, linkId, csrfToken ?? ""),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["recap-share-links", conversationId] }),
  });

  const activeLinks = (linksQuery.data ?? []).filter(
    (link) => !link.revoked_at && new Date(link.expires_at) > new Date()
  );

  if (!hasPermission("recap:approve")) return null;

  return (
    <div className={styles.shareLinks}>
      <p className={styles.shareLinksHeading}>
        <Link2 size={16} aria-hidden="true" /> Freigabe-Links (zeitlich begrenzt, kein Login
        erforderlich)
      </p>
      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
        <Select
          aria-label="Gültigkeitsdauer"
          value={ttlHours}
          onChange={(event) => setTtlHours(Number(event.target.value))}
        >
          {TTL_OPTIONS.map((option) => (
            <option key={option.hours} value={option.hours}>
              {option.label}
            </option>
          ))}
        </Select>
        <Button
          variant="secondary"
          type="button"
          disabled={createMutation.isPending}
          onClick={() => createMutation.mutate()}
        >
          Link erstellen
        </Button>
      </div>

      {activeLinks.length > 0 && (
        <ul className={styles.shareLinkList}>
          {activeLinks.map((link) => {
            const url = `${window.location.origin}/share/recap/${link.token}`;
            return (
              <li key={link.id} className={styles.shareLinkItem}>
                <span className={styles.shareLinkUrl}>{url}</span>
                <span className={styles.shareLinkMeta}>
                  läuft ab am {formatExpiry(link.expires_at)} · {link.access_count}× abgerufen
                </span>
                <Button
                  variant="tertiary"
                  type="button"
                  aria-label="Link kopieren"
                  onClick={() => void navigator.clipboard.writeText(url)}
                >
                  <Copy size={16} aria-hidden="true" />
                </Button>
                <Button
                  variant="tertiary"
                  type="button"
                  aria-label="Link widerrufen"
                  onClick={() => revokeMutation.mutate(link.id)}
                >
                  <Trash2 size={16} aria-hidden="true" />
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

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
      <Card
        title="Recap für Teilnehmer"
        actions={
          hasPermission("recap:generate") && (
            <Button
              variant="secondary"
              type="button"
              disabled={generateMutation.isPending}
              onClick={() => generateMutation.mutate()}
            >
              {generateMutation.isPending ? <Spinner size={16} /> : <RefreshCw size={16} aria-hidden="true" />}{" "}
              {generateMutation.isPending ? "Wird erstellt…" : revision ? "Neu erstellen" : "Recap erstellen"}
            </Button>
          )
        }
      >
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
      </Card>

      {revision && (
        <Card
          className={styles.revisionCard}
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
                {approveMutation.isPending ? <Spinner size={16} /> : <CheckCircle2 size={16} aria-hidden="true" />}{" "}
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

          {revision.status === "approved" && <ShareLinksSection conversationId={conversationId} />}
        </Card>
      )}
    </div>
  );
}
