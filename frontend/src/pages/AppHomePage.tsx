import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Inbox, Mic, Plus } from "lucide-react";
import { useNavigate } from "react-router";

import { getConversationStats, listConversations } from "../api/conversations";
import { listTasks } from "../api/longitudinal";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { Card, StatCard } from "../design-system/Card";
import { EmptyState, ErrorState, Skeleton } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";
import styles from "./AppHomePage.module.css";

const IN_PROGRESS_STATUSES = ["recording", "uploaded", "normalizing"];

interface RecentConversationRow {
  id: string;
  title: string;
  status: string;
  created_at: string;
}

const RECENT_COLUMNS: DataTableColumn<RecentConversationRow>[] = [
  { key: "title", header: "Gespräch", render: (row) => row.title },
  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
  {
    key: "created_at",
    header: "Erstellt",
    render: (row) => new Date(row.created_at).toLocaleDateString(),
  },
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
  const tasksQuery = useQuery({
    queryKey: ["tasks", { status: "open" }],
    queryFn: () => listTasks("open"),
    enabled: hasPermission("task:read"),
  });

  const counts = statsQuery.data?.counts ?? {};
  const activeCount = IN_PROGRESS_STATUSES.reduce((sum, key) => sum + (counts[key] ?? 0), 0);
  const readyCount = counts.ready ?? 0;
  const failedCount = counts.failed ?? 0;

  return (
    <div>
      <div className={styles.header}>
        <h1 className={styles.title}>Willkommen, {user?.displayName}</h1>
        <div className={styles.actions}>
          <Button variant="primary" onClick={() => navigate("/app/conversations/new")}>
            <Plus size={16} aria-hidden="true" /> Neues Gespräch
          </Button>
          <Button variant="secondary" onClick={() => navigate("/app/conversations")}>
            Alle Gespräche
          </Button>
        </div>
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

        {hasPermission("task:read") && (
          <Card title="Offene Aufgaben">
            {tasksQuery.isLoading ? (
              <Skeleton height="1rem" />
            ) : tasksQuery.isError ? (
              <ErrorState message="Aufgaben konnten nicht geladen werden." />
            ) : (tasksQuery.data ?? []).length === 0 ? (
              <EmptyState title="Keine offenen Aufgaben" />
            ) : (
              <ul className={styles.taskList}>
                {(tasksQuery.data ?? []).slice(0, 6).map((task) => (
                  <li key={task.id} className={styles.taskItem}>
                    <span className={styles.taskDescription}>{task.description}</span>
                    <span className={styles.taskMeta}>
                      {task.source === "ai_extracted" ? "Automatisch erstellt" : "Manuell erstellt"}
                      {task.due_date ? ` · Fällig: ${task.due_date}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
