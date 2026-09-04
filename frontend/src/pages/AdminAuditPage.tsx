import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAuditEvents, listAuditEventTypes } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Select, TextInput } from "../design-system/FormControls";

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

  const typesQuery = useQuery({
    queryKey: ["admin", "audit-event-types"],
    queryFn: listAuditEventTypes,
  });
  const eventsQuery = useQuery({
    queryKey: ["admin", "audit-events", eventType, username],
    queryFn: () =>
      listAuditEvents({ event_type: eventType || undefined, username: username || undefined, limit: 100 }),
  });

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Audit</h1>

      <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
        <Select value={eventType} onChange={(e) => setEventType(e.target.value)}>
          <option value="">All event types</option>
          {typesQuery.data?.event_types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <TextInput
          placeholder="Filter by username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </div>

      <table style={{ width: "100%", marginTop: "var(--space-4)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>When</th>
            <th>Event</th>
            <th>User</th>
            <th>IP</th>
            <th>Metadata</th>
          </tr>
        </thead>
        <tbody>
          {eventsQuery.data?.items.map((event) => (
            <tr key={event.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>{new Date(event.created_at).toLocaleString()}</td>
              <td>{event.event_type}</td>
              <td>{event.username ?? "—"}</td>
              <td>{event.ip_address ?? "—"}</td>
              <td style={{ color: "var(--text-secondary)", fontSize: "var(--font-caption-size)" }}>
                {event.event_metadata ? JSON.stringify(event.event_metadata) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {eventsQuery.data && (
        <p style={{ marginTop: "var(--space-3)", color: "var(--text-muted)" }}>
          {eventsQuery.data.total} total event(s)
        </p>
      )}
    </AdminLayout>
  );
}
