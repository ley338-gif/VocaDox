import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { listTasks, type FollowUpStatus, type FollowUpTask } from "../api/longitudinal";
import { Badge } from "../design-system/Badge";
import { Select } from "../design-system/FormControls";
import { EmptyState, ErrorState } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";

const COLUMNS: DataTableColumn<FollowUpTask>[] = [
  {
    key: "description",
    header: "Aufgabe",
    render: (row) => row.description,
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
  const [statusFilter, setStatusFilter] = useState<FollowUpStatus | "">("open");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["tasks", { status: statusFilter }],
    queryFn: () => listTasks(statusFilter || undefined),
  });

  return (
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", marginBottom: "var(--space-4)" }}>Aufgaben</h1>

      <div style={{ marginBottom: "var(--space-4)" }}>
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
        rows={data ?? []}
        keyExtractor={(row) => row.id}
        loading={isLoading}
        error={isError ? <ErrorState message="Aufgaben konnten nicht geladen werden." /> : undefined}
        onRowClick={(row) => navigate(`/app/conversations/${row.conversation_id}`)}
        empty={
          <EmptyState
            icon={<ClipboardList size={20} aria-hidden="true" />}
            title="Keine Aufgaben"
            description="Aus Gesprächen automatisch extrahierte oder manuell erstellte Aufgaben erscheinen hier."
          />
        }
      />
    </div>
  );
}
