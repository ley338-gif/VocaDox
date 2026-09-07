import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Search, ArrowRight, ListChecks } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { listTasks, type FollowUpStatus, type FollowUpTask } from "../api/longitudinal";
import { PageHeader } from "../design-system/PageHeader";
import { Card } from "../design-system/Card";
import styles from "./TasksListPage.module.css";
import { Badge } from "../design-system/Badge";
import { TextInput, Select } from "../design-system/FormControls";
import { EmptyState, ErrorState } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";

const COLUMNS: DataTableColumn<FollowUpTask>[] = [
  {
    key: "description",
    header: "Aufgabe",
    render: (row) => <span className={styles.taskTitle}><ClipboardList size={18} aria-hidden="true" />{row.description}</span>,
    sortable: true,
    sortValue: (row) => row.description,
  },
  {
    key: "source",
    header: "Quelle",
    render: (row) => (
      <Badge tone={row.source === "ai_extracted" ? "info" : "neutral"}>
        {row.source === "ai_extracted" ? "Automatisch erstellt" : "Manuell erstellt"}
      </Badge>
    ),
  },
  { key: "assignee", header: "Verantwortlich", render: (row) => row.assignee ?? "—" },
  { key: "due_date", header: "Fällig", render: (row) => row.due_date ?? "—" },
  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
];

/**
 * Org-wide "Aufgaben" nav entry (brief §10) — reads GET /tasks (added in
 * the Stage 3 redesign PR specifically to back this page with real data).
 * Rows link to their owning conversation's detail page (no per-task
 * detail view exists — the conversation's own Tasks tab is the real
 * place to act on a task).
 */
export function TasksListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<FollowUpStatus | "">("open");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["tasks", { status: statusFilter }],
    queryFn: () => listTasks(statusFilter || undefined),
  });

  return (
    <div>
      <PageHeader
        breadcrumb={[{ label: "VocaDox", to: "/app" }, { label: "Aufgaben" }]}
        title="Aufgaben"
        meta="Behalten Sie offene Prüfungen und nächste Schritte aus Ihren Gesprächen im Blick."
      />
      <div className={styles.layout}>
        <section aria-label="Aufgabenübersicht" className={styles.main}>
          <div className={styles.filters}>
            <label className={styles.search}>
              <Search size={18} aria-hidden="true" />
              <TextInput aria-label="Aufgaben suchen" placeholder="Aufgaben suchen …" value={search} onChange={(event) => setSearch(event.target.value)} />
            </label>
            <Select
              aria-label="Nach Status filtern"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as FollowUpStatus | "")}
            >
              <option value="open">Offen</option>
              <option value="done">Erledigt</option>
              <option value="dismissed">Verworfen</option>
              <option value="">Alle</option>
            </Select>
          </div>

          <DataTable
            columns={COLUMNS}
            rows={(data ?? []).filter((task) => `${task.description} ${task.assignee ?? ""}`.toLocaleLowerCase("de-DE").includes(search.toLocaleLowerCase("de-DE")))}
            keyExtractor={(row) => row.id}
            loading={isLoading}
            error={isError ? <ErrorState message="Aufgaben konnten nicht geladen werden." /> : undefined}
            onRowClick={(row) => navigate(`/app/conversations/${row.conversation_id}`, { state: { tab: "tasks" } })}
            empty={
              <EmptyState
                icon={<ClipboardList size={20} aria-hidden="true" />}
                title={search ? "Keine passenden Aufgaben" : "Keine Aufgaben"}
                description={search ? "Ändern Sie den Suchbegriff oder den Statusfilter." : "Aus Gesprächen automatisch extrahierte oder manuell erstellte Aufgaben erscheinen hier."}
              />
            }
          />
        </section>
        <aside className={styles.aside}>
          <Card title={<span className={styles.cardTitle}><ListChecks size={20} aria-hidden="true" /> Aufgaben bearbeiten</span>}>
            <p>Öffnen Sie eine Aufgabe, um direkt zum zugehörigen Gespräch zu gelangen. Dort können Sie den Status ändern und weitere Aufgaben erstellen.</p>
            <div className={styles.hint}><ArrowRight size={16} aria-hidden="true" /> Gespräch → Aufgaben</div>
          </Card>
        </aside>
      </div>
    </div>
  );
}
