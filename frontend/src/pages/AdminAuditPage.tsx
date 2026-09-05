import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAuditEvents, listAuditEventTypes, type AuditEvent } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Drawer } from "../design-system/Drawer";
import { Select, TextInput } from "../design-system/FormControls";
import { DataTable, type DataTableColumn } from "../design-system/Table";

/**
 * Phase 7 Admin Portal Audit page: list/filter the real `audit_events`
 * accumulated since Phase 1 across every domain. Read-only — a viewer,
 * not a change to what gets audited. Hard rule (unchanged): events never
 * carry conversation/fact/transcript/document content, only ids/metadata
 * — nothing here renders any field capable of holding that.
 */
export function AdminAuditPage() {
  const [eventType, setEventType] = useState("");
  const [username, setUsername] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);

  const typesQuery = useQuery({
    queryKey: ["admin", "audit-event-types"],
    queryFn: listAuditEventTypes,
  });
  const eventsQuery = useQuery({
    queryKey: ["admin", "audit-events", eventType, username],
    queryFn: () =>
      listAuditEvents({ event_type: eventType || undefined, username: username || undefined, limit: 100 }),
  });

  const columns: DataTableColumn<AuditEvent>[] = [
    { key: "when", header: "Zeitpunkt", render: (e) => new Date(e.created_at).toLocaleString(), sortable: true, sortValue: (e) => e.created_at },
    { key: "event", header: "Ereignis", render: (e) => e.event_type },
    { key: "user", header: "Benutzer", render: (e) => e.username ?? "—" },
    { key: "ip", header: "IP", render: (e) => e.ip_address ?? "—" },
  ];

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Audit</h1>

      <div style={{ display: "flex", gap: "var(--space-3)", margin: "var(--space-4) 0" }}>
        <Select value={eventType} onChange={(e) => setEventType(e.target.value)}>
          <option value="">Alle Ereignistypen</option>
          {typesQuery.data?.event_types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <TextInput
          placeholder="Nach Benutzername filtern"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </div>

      <DataTable
        columns={columns}
        rows={eventsQuery.data?.items ?? []}
        keyExtractor={(e) => e.id}
        loading={eventsQuery.isLoading}
        onRowClick={(e) => setSelectedEvent(e)}
      />
      {eventsQuery.data && (
        <p style={{ marginTop: "var(--space-3)", color: "var(--text-muted)" }}>
          {eventsQuery.data.total} Ereignis(se) insgesamt
        </p>
      )}

      <Drawer open={selectedEvent !== null} onClose={() => setSelectedEvent(null)} title="Audit-Ereignis">
        {selectedEvent && (
          <dl style={{ display: "grid", gap: "var(--space-3)", margin: 0 }}>
            <div>
              <dt style={{ fontWeight: 600 }}>Zeitpunkt</dt>
              <dd style={{ margin: 0 }}>{new Date(selectedEvent.created_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>Ereignistyp</dt>
              <dd style={{ margin: 0 }}>{selectedEvent.event_type}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>Benutzer</dt>
              <dd style={{ margin: 0 }}>{selectedEvent.username ?? "—"}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>IP-Adresse</dt>
              <dd style={{ margin: 0 }}>{selectedEvent.ip_address ?? "—"}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>User-Agent</dt>
              <dd style={{ margin: 0, wordBreak: "break-word" }}>{selectedEvent.user_agent ?? "—"}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>Metadaten</dt>
              <dd style={{ margin: 0 }}>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    fontSize: "var(--font-caption-size)",
                    background: "var(--surface-sunken)",
                    padding: "var(--space-3)",
                    borderRadius: "var(--radius-md)",
                  }}
                >
                  {selectedEvent.event_metadata ? JSON.stringify(selectedEvent.event_metadata, null, 2) : "—"}
                </pre>
              </dd>
            </div>
          </dl>
        )}
      </Drawer>
    </AdminLayout>
  );
}
