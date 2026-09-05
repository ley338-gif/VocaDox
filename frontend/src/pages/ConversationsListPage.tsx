import { useQuery } from "@tanstack/react-query";
import { Inbox, Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import type { Conversation } from "../api/conversations";
import { listConversations } from "../api/conversations";
import { Button } from "../design-system/Button";
import { Select, TextInput } from "../design-system/FormControls";
import { EmptyState, ErrorState } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";
import { Pagination } from "../design-system/Pagination";
import styles from "./ConversationsListPage.module.css";

const PAGE_SIZE = 20;

const COLUMNS: DataTableColumn<Conversation>[] = [
  { key: "title", header: "Titel", render: (row) => row.title, sortable: true, sortValue: (row) => row.title },
  { key: "type", header: "Typ", render: (row) => row.conversation_type },
  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
  {
    key: "privacy",
    header: "Datenschutz",
    render: (row) => (row.privacy_mode === "restricted" ? "Eingeschränkt" : "Standard"),
  },
  {
    key: "duration",
    header: "Dauer",
    render: (row) => (row.duration_ms ? `${Math.round(row.duration_ms / 1000)}s` : "—"),
  },
  {
    key: "created",
    header: "Erstellt",
    render: (row) => new Date(row.created_at).toLocaleDateString(),
    sortable: true,
    sortValue: (row) => row.created_at,
  },
];

export function ConversationsListPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => searchParams.get("q") ?? "");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["conversations", { search, statusFilter, typeFilter, offset }],
    queryFn: () =>
      listConversations({
        search: search || undefined,
        status: statusFilter || undefined,
        type: typeFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
  });

  return (
    <div>
      <div className={styles.header}>
        <h1 style={{ fontSize: "var(--font-h1-size)" }}>Gespräche</h1>
        <Button variant="primary" type="button" onClick={() => navigate("/app/conversations/new")}>
          <Plus size={16} aria-hidden="true" /> Neues Gespräch
        </Button>
      </div>

      <div className={styles.filters}>
        <TextInput
          placeholder="Nach Titel suchen…"
          aria-label="Gespräche durchsuchen"
          value={search}
          onChange={(event) => {
            setOffset(0);
            setSearch(event.target.value);
          }}
        />
        <Select
          aria-label="Nach Status filtern"
          value={statusFilter}
          onChange={(event) => {
            setOffset(0);
            setStatusFilter(event.target.value);
          }}
        >
          <option value="">Alle Status</option>
          <option value="created">Erstellt</option>
          <option value="recording">Aufnahme läuft</option>
          <option value="uploaded">Hochgeladen</option>
          <option value="normalizing">Verarbeitung</option>
          <option value="ready">Bereit</option>
          <option value="failed">Fehler</option>
        </Select>
        <Select
          aria-label="Nach Typ filtern"
          value={typeFilter}
          onChange={(event) => {
            setOffset(0);
            setTypeFilter(event.target.value);
          }}
        >
          <option value="">Alle Typen</option>
          <option value="general">Allgemein</option>
          <option value="medical">Medizinisch</option>
          <option value="therapy">Therapie</option>
          <option value="meeting">Meeting</option>
          <option value="interview">Interview</option>
          <option value="other">Sonstiges</option>
        </Select>
      </div>

      <DataTable
        columns={COLUMNS}
        rows={data?.items ?? []}
        keyExtractor={(row) => row.id}
        loading={isLoading}
        error={isError ? <ErrorState message="Gespräche konnten nicht geladen werden." /> : undefined}
        onRowClick={(row) => navigate(`/app/conversations/${row.id}`)}
        empty={
          <EmptyState
            icon={<Inbox size={20} aria-hidden="true" />}
            title="Noch keine Gespräche"
            description="Starten Sie ein neues Gespräch, um loszulegen."
            action={
              <Button variant="primary" type="button" onClick={() => navigate("/app/conversations/new")}>
                Gespräch starten
              </Button>
            }
          />
        }
      />

      {data && data.total > 0 && (
        <Pagination offset={offset} limit={PAGE_SIZE} total={data.total} onOffsetChange={setOffset} />
      )}
    </div>
  );
}
