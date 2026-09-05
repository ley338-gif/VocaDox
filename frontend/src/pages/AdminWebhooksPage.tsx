import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type WebhookCreated,
  type WebhookDelivery,
  createWebhook,
  deleteWebhook,
  listOrganizations,
  listWebhookDeliveries,
  listWebhookEventTypes,
  listWebhooks,
  rotateWebhookSecret,
  updateWebhook,
} from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { FormField } from "../design-system/FormField";
import { Checkbox, TextInput, Select } from "../design-system/FormControls";
import { Modal } from "../design-system/Modal";
import { ErrorState } from "../design-system/States";
import { DataTable, type DataTableColumn } from "../design-system/Table";

/**
 * Phase 10 Admin Portal: Webhooks (spec §55). Follows AdminAuditPage's
 * read-only log-viewer pattern for the Delivery Log, and
 * AdminServiceAccountsPage's show-once-secret pattern for the signing
 * secret. Target URLs are validated server-side (SSRF-adjacent policy:
 * https only, no loopback/private/link-local) — this page surfaces the
 * server's rejection reason rather than duplicating the policy client-side.
 */
export function AdminWebhooksPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const canWrite = hasPermission("webhook:write");

  const [showCreate, setShowCreate] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [revealedSecret, setRevealedSecret] = useState<WebhookCreated | null>(null);
  const [expandedWebhookId, setExpandedWebhookId] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    organization_id: "",
    target_url: "",
    event_types: [] as string[],
  });

  const webhooksQuery = useQuery({ queryKey: ["admin", "webhooks"], queryFn: listWebhooks });
  const orgsQuery = useQuery({ queryKey: ["admin", "organizations"], queryFn: listOrganizations });
  const eventTypesQuery = useQuery({ queryKey: ["admin", "webhook-event-types"], queryFn: listWebhookEventTypes });
  const deliveriesQuery = useQuery({
    queryKey: ["admin", "webhook-deliveries", expandedWebhookId],
    queryFn: () => listWebhookDeliveries(expandedWebhookId as string, { limit: 50 }),
    enabled: expandedWebhookId !== null,
  });

  function toggleEventType(eventType: string) {
    setForm((f) => ({
      ...f,
      event_types: f.event_types.includes(eventType)
        ? f.event_types.filter((e) => e !== eventType)
        : [...f.event_types, eventType],
    }));
  }

  async function handleCreate() {
    if (!csrfToken || !form.name.trim() || !form.organization_id || !form.target_url) return;
    setCreateError(null);
    try {
      const created = await createWebhook(
        {
          name: form.name,
          organization_id: form.organization_id,
          target_url: form.target_url,
          event_types: form.event_types,
        },
        csrfToken
      );
      setRevealedSecret(created);
      setForm({ name: "", organization_id: "", target_url: "", event_types: [] });
      setShowCreate(false);
      await queryClient.invalidateQueries({ queryKey: ["admin", "webhooks"] });
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Webhook konnte nicht erstellt werden.");
    }
  }

  async function handleToggleActive(webhookId: string, isActive: boolean) {
    if (!csrfToken) return;
    await updateWebhook(webhookId, { is_active: !isActive }, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "webhooks"] });
  }

  async function handleRotateSecret(webhookId: string) {
    if (!csrfToken) return;
    if (!confirm("Signaturschlüssel dieses Webhooks rotieren? Empfänger vorher aktualisieren.")) return;
    const rotated = await rotateWebhookSecret(webhookId, csrfToken);
    setRevealedSecret(rotated);
  }

  async function handleDelete(webhookId: string) {
    if (!csrfToken) return;
    if (!confirm("Diesen Webhook dauerhaft löschen?")) return;
    await deleteWebhook(webhookId, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "webhooks"] });
  }

  const orgName = (id: string) => orgsQuery.data?.find((o) => o.id === id)?.name ?? id;

  const deliveryColumns: DataTableColumn<WebhookDelivery>[] = [
    { key: "when", header: "Zeitpunkt", render: (d) => new Date(d.created_at).toLocaleString() },
    { key: "event", header: "Ereignis", render: (d) => d.event_type },
    { key: "attempt", header: "Versuch", render: (d) => d.attempt_number },
    {
      key: "status",
      header: "Status",
      render: (d) => (
        <Badge tone={d.status === "success" ? "success" : d.status === "exhausted" ? "danger" : "warning"}>
          {d.status}
        </Badge>
      ),
    },
    { key: "response", header: "Antwort", render: (d) => d.response_status_code ?? "—" },
    { key: "error", header: "Fehler", render: (d) => <span style={{ fontSize: "var(--font-caption-size)" }}>{d.error_message ?? "—"}</span> },
  ];

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Webhooks</h1>
        {canWrite && (
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            Neuer Webhook
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)", marginBottom: "var(--space-4)" }}>
        Zustellungen sind HMAC-SHA256-signiert (X-VocaDox-Signature) und enthalten standardmäßig nie
        Gesprächs-/Transkript-/Fakten-/Dokumentinhalte — nur Ereignis-IDs und Metadaten. Ziele müssen
        https sein und dürfen nicht auf eine Loopback-/private/link-lokale Adresse auflösen.
      </p>

      {revealedSecret && (
        <div
          style={{
            border: "1px solid var(--color-warning)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginBottom: "var(--space-4)",
            background: "color-mix(in srgb, var(--color-warning) 10%, var(--surface-raised))",
          }}
        >
          <strong>Signaturschlüssel für "{revealedSecret.name}" — jetzt kopieren, er wird nicht erneut angezeigt:</strong>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
            <code
              style={{
                flex: 1,
                padding: "var(--space-2)",
                background: "var(--surface-sunken)",
                borderRadius: "var(--radius-sm)",
                overflowWrap: "anywhere",
              }}
            >
              {revealedSecret.secret}
            </code>
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(revealedSecret.secret)}>
              Kopieren
            </Button>
            <Button variant="secondary" onClick={() => setRevealedSecret(null)}>
              Schließen
            </Button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {webhooksQuery.data?.map((webhook) => (
          <Card key={webhook.id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)" }}>
              <div>
                <strong>{webhook.name}</strong>{" "}
                <Badge tone={webhook.is_active ? "success" : "neutral"}>
                  {webhook.is_active ? "aktiv" : "deaktiviert"}
                </Badge>
                <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)", overflowWrap: "anywhere", marginTop: "var(--space-1)" }}>
                  {orgName(webhook.organization_id)} · {webhook.target_url}
                </p>
                <p style={{ color: "var(--text-secondary)", fontSize: "var(--font-caption-size)" }}>
                  {webhook.event_types.join(", ")}
                </p>
              </div>
              <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
                <Button
                  variant="secondary"
                  onClick={() => setExpandedWebhookId(expandedWebhookId === webhook.id ? null : webhook.id)}
                >
                  {expandedWebhookId === webhook.id ? "Log ausblenden" : "Zustellungsprotokoll"}
                </Button>
                {canWrite && (
                  <>
                    <Button variant="secondary" onClick={() => void handleToggleActive(webhook.id, webhook.is_active)}>
                      {webhook.is_active ? "Deaktivieren" : "Aktivieren"}
                    </Button>
                    <Button variant="secondary" onClick={() => void handleRotateSecret(webhook.id)}>
                      Schlüssel rotieren
                    </Button>
                    <Button variant="destructive" onClick={() => void handleDelete(webhook.id)}>
                      Löschen
                    </Button>
                  </>
                )}
              </div>
            </div>

            {expandedWebhookId === webhook.id && (
              <div style={{ marginTop: "var(--space-4)" }}>
                <strong>Zustellungsprotokoll ({deliveriesQuery.data?.total ?? 0} insgesamt)</strong>
                <div style={{ marginTop: "var(--space-2)" }}>
                  <DataTable
                    columns={deliveryColumns}
                    rows={deliveriesQuery.data?.items ?? []}
                    keyExtractor={(d) => d.id}
                  />
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Neuer Webhook">
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <FormField label="Name" required>
            <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </FormField>
          <FormField label="Organisation" required>
            <Select value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: e.target.value })}>
              <option value="">Organisation wählen…</option>
              {orgsQuery.data?.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Ziel-URL" required>
            <TextInput
              placeholder="https://ihr-empfaenger.example.com/webhook"
              value={form.target_url}
              onChange={(e) => setForm({ ...form, target_url: e.target.value })}
            />
          </FormField>
          <Card title="Ereignistypen" padded>
            {eventTypesQuery.data?.event_types.map((eventType) => (
              <label key={eventType} style={{ display: "block" }}>
                <Checkbox
                  checked={form.event_types.includes(eventType)}
                  onChange={() => toggleEventType(eventType)}
                />{" "}
                {eventType}
              </label>
            ))}
          </Card>
          {createError && <ErrorState message={createError} />}
          <Button variant="primary" onClick={() => void handleCreate()}>
            Erstellen
          </Button>
        </div>
      </Modal>
    </AdminLayout>
  );
}
