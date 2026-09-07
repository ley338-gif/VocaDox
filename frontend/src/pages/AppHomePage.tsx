import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Inbox, Lightbulb, MessagesSquare, Mic, Sparkles, Upload } from "lucide-react";
import { useNavigate } from "react-router";

import type { Conversation } from "../api/conversations";
import { getConversationStats, listConversations } from "../api/conversations";
import { useAuth } from "../auth/useAuth";
import { OpenTasksCard } from "../components/OpenTasksCard";
import { QuickActionCard } from "../components/QuickActionCard";
import { Button } from "../design-system/Button";
import { Card, StatCard } from "../design-system/Card";
import { PageHeader } from "../design-system/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";
import { CONVERSATION_TYPE_LABELS } from "../lib/conversationLabels";
import { formatDuration } from "../lib/formatDuration";
import styles from "./AppHomePage.module.css";

const IN_PROGRESS_STATUSES = ["recording", "uploaded", "normalizing"];

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Guten Morgen";
  if (hour < 18) return "Guten Tag";
  return "Guten Abend";
}

const RECENT_COLUMNS: DataTableColumn<Conversation>[] = [
  {
    key: "title",
    header: "Gespräch",
    render: (row) => (
      <div>
        <div className={styles.rowTitle}>{row.title}</div>
        <div className={styles.rowSubtitle}>
          {row.description || CONVERSATION_TYPE_LABELS[row.conversation_type]}
        </div>
      </div>
    ),
  },
  {
    key: "created_at",
    header: "Datum",
    render: (row) => new Date(row.created_at).toLocaleDateString("de-DE"),
  },
  {
    key: "duration",
    header: "Dauer",
    render: (row) => (row.duration_ms ? formatDuration(row.duration_ms) : "—"),
  },
  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
];

/**
 * `/app` dashboard. Every number here comes from a real aggregate endpoint
 * (GET /conversations/stats, GET /tasks) — never fabricated, matching this
 * project's established no-fake-status discipline (see the admin dashboard,
 * which set the precedent of real-only health/queue numbers).
 */
export function AppHomePage() {
  const { user, hasPermission } = useAuth();
  const navigate = useNavigate();

  const statsQuery = useQuery({ queryKey: ["conversation-stats"], queryFn: getConversationStats });
  const recentQuery = useQuery({
    queryKey: ["conversations", "recent"],
    queryFn: () => listConversations({ limit: 5 }),
  });

  const counts = statsQuery.data?.counts ?? {};
  const activeCount = IN_PROGRESS_STATUSES.reduce((sum, key) => sum + (counts[key] ?? 0), 0);
  const readyCount = counts.ready ?? 0;
  const failedCount = counts.failed ?? 0;

  return (
    <div>
      <PageHeader
        title={`${greeting()}, ${user?.displayName ?? ""}`}
        meta="Hier finden Sie Ihre aktuellen Gespräche und Aufgaben."
      />

      <div className={styles.quickActions}>
        <QuickActionCard
          icon={<Mic size={20} aria-hidden="true" />}
          title="Neues Gespräch"
          description="Direkt aufnehmen"
          onClick={() => navigate("/app/conversations/new?mode=record")}
        />
        <QuickActionCard
          icon={<Upload size={20} aria-hidden="true" />}
          title="Datei hochladen"
          description="Audio- oder Videodatei"
          onClick={() => navigate("/app/conversations/new?mode=upload")}
        />
        <QuickActionCard
          icon={<MessagesSquare size={20} aria-hidden="true" />}
          title="Alle Gespräche"
          description="Übersicht und Suche"
          onClick={() => navigate("/app/conversations")}
        />
        {hasPermission("ask:query") && (
          <QuickActionCard
            icon={<Sparkles size={20} aria-hidden="true" />}
            title="Ask VocaDox"
            description="Fragen zu Ihren Gesprächen"
            onClick={() => navigate("/app/ask")}
          />
        )}
      </div>

      <div className={styles.statGrid}>
        {statsQuery.isLoading ? (
          <>
            <Skeleton height="4rem" />
            <Skeleton height="4rem" />
            <Skeleton height="4rem" />
          </>
        ) : statsQuery.isError ? (
          <ErrorState message="Kennzahlen konnten nicht geladen werden." />
        ) : (
          <>
            <StatCard label="In Bearbeitung" value={activeCount} icon={<Mic size={18} aria-hidden="true" />} />
            <StatCard label="Bereit" value={readyCount} icon={<CheckCircle2 size={18} aria-hidden="true" />} />
            <StatCard label="Fehlgeschlagen" value={failedCount} icon={<AlertCircle size={18} aria-hidden="true" />} />
          </>
        )}
      </div>

      <div className={styles.columns}>
        <Card title="Letzte Gespräche">
          <DataTable
            columns={RECENT_COLUMNS}
            rows={recentQuery.data?.items ?? []}
            keyExtractor={(row) => row.id}
            loading={recentQuery.isLoading}
            error={recentQuery.isError ? <ErrorState message="Gespräche konnten nicht geladen werden." /> : undefined}
            onRowClick={(row) => navigate(`/app/conversations/${row.id}`)}
            empty={
              <EmptyState
                icon={<Inbox size={20} aria-hidden="true" />}
                title="Noch keine Gespräche"
                description="Starten Sie ein neues Gespräch, um loszulegen."
                action={
                  <Button variant="primary" onClick={() => navigate("/app/conversations/new")}>
                    Gespräch starten
                  </Button>
                }
              />
            }
          />
        </Card>

        <OpenTasksCard limit={6} />
      </div>
      <section className={styles.guidance} aria-labelledby="workflow-help">
        <Lightbulb size={24} aria-hidden="true" />
        <div>
          <h2 id="workflow-help">Vom Gespräch zur Dokumentation</h2>
          <p>Nehmen Sie ein Gespräch auf oder laden Sie eine Datei hoch. Öffnen Sie anschließend das Gespräch, um Transkript, Sprecherzuordnung und Dokumentation zu prüfen.</p>
        </div>
      </section>
    </div>
  );
}
