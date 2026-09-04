import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type WebhookCreated,
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
import { Checkbox, TextInput, Select } from "../design-system/FormControls";

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
      setCreateError(err instanceof Error ? err.message : "failed to create webhook");
    }
  }

  async function handleToggleActive(webhookId: string, isActive: boolean) {
    if (!csrfToken) return;
    await updateWebhook(webhookId, { is_active: !isActive }, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "webhooks"] });
  }

  async function handleRotateSecret(webhookId: string) {
    if (!csrfToken) return;
    if (!confirm("Rotate this webhook's signing secret? Update your receiver before rotating.")) return;
    const rotated = await rotateWebhookSecret(webhookId, csrfToken);
    setRevealedSecret(rotated);
  }

  async function handleDelete(webhookId: string) {
    if (!csrfToken) return;
    if (!confirm("Delete this webhook permanently?")) return;
    await deleteWebhook(webhookId, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "webhooks"] });
  }

  const orgName = (id: string) => orgsQuery.data?.find((o) => o.id === id)?.name ?? id;

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Webhooks</h1>
        {canWrite && (
          <Button variant="primary" onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? "Cancel" : "New webhook"}
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Deliveries are HMAC-SHA256 signed (X-VocaDox-Signature) and never
        include conversation/transcript/fact/document content by default —
        only event ids and metadata. Targets must be https and may not
        resolve to a loopback/private/link-local address.
      </p>

      {revealedSecret && (
        <div
          style={{
            border: "1px solid var(--color-warning-border, orange)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginTop: "var(--space-4)",
            background: "var(--surface-warning, rgba(255,180,0,0.08))",
          }}
        >
          <strong>Signing secret for "{revealedSecret.name}" — copy it now, it will not be shown again:</strong>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
            <code
              style={{
                flex: 1,
                padding: "var(--space-2)",
                background: "var(--surface-secondary)",
                borderRadius: "var(--radius-sm)",
                overflowWrap: "anywhere",
              }}
            >
              {revealedSecret.secret}
            </code>
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(revealedSecret.secret)}>
              Copy
            </Button>
            <Button variant="secondary" onClick={() => setRevealedSecret(null)}>
              Dismiss
            </Button>
          </div>
        </div>
      )}

      {showCreate && (
        <div
          style={{
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginTop: "var(--space-4)",
            display: "grid",
            gap: "var(--space-3)",
            maxWidth: "480px",
          }}
        >
          <TextInput
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Select
            value={form.organization_id}
            onChange={(e) => setForm({ ...form, organization_id: e.target.value })}
          >
            <option value="">Select organization…</option>
            {orgsQuery.data?.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
          <TextInput
            placeholder="https://your-receiver.example.com/webhook"
            value={form.target_url}
            onChange={(e) => setForm({ ...form, target_url: e.target.value })}
          />
          <div>
            {eventTypesQuery.data?.event_types.map((eventType) => (
              <label key={eventType} style={{ display: "block" }}>
                <Checkbox
                  checked={form.event_types.includes(eventType)}
                  onChange={() => toggleEventType(eventType)}
                />{" "}
                {eventType}
              </label>
            ))}
          </div>
          {createError && <p style={{ color: "var(--color-danger, red)" }}>{createError}</p>}
          <Button variant="primary" onClick={() => void handleCreate()}>
            Create
          </Button>
        </div>
      )}

      <table style={{ width: "100%", marginTop: "var(--space-6)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>Name</th>
            <th>Organization</th>
            <th>Target</th>
            <th>Events</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {webhooksQuery.data?.map((webhook) => (
            <>
              <tr key={webhook.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
                <td>{webhook.name}</td>
                <td>{orgName(webhook.organization_id)}</td>
                <td style={{ maxWidth: 240, overflowWrap: "anywhere" }}>{webhook.target_url}</td>
                <td style={{ fontSize: "var(--font-caption-size)" }}>{webhook.event_types.join(", ")}</td>
                <td>
                  <Badge tone={webhook.is_active ? "success" : "neutral"}>
                    {webhook.is_active ? "active" : "disabled"}
                  </Badge>
                </td>
                <td style={{ display: "flex", gap: "var(--space-2)" }}>
                  <Button
                    variant="secondary"
                    onClick={() => setExpandedWebhookId(expandedWebhookId === webhook.id ? null : webhook.id)}
                  >
                    {expandedWebhookId === webhook.id ? "Hide log" : "Delivery log"}
                  </Button>
                  {canWrite && (
                    <>
                      <Button variant="secondary" onClick={() => void handleToggleActive(webhook.id, webhook.is_active)}>
                        {webhook.is_active ? "Disable" : "Enable"}
                      </Button>
                      <Button variant="secondary" onClick={() => void handleRotateSecret(webhook.id)}>
                        Rotate secret
                      </Button>
                      <Button variant="destructive" onClick={() => void handleDelete(webhook.id)}>
                        Delete
                      </Button>
                    </>
                  )}
                </td>
              </tr>
              {expandedWebhookId === webhook.id && (
                <tr key={`${webhook.id}-deliveries`}>
                  <td colSpan={6} style={{ padding: "var(--space-3)", background: "var(--surface-secondary)" }}>
                    <strong>Delivery log ({deliveriesQuery.data?.total ?? 0} total)</strong>
                    <table style={{ width: "100%", marginTop: "var(--space-2)", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ textAlign: "left" }}>
                          <th>When</th>
                          <th>Event</th>
                          <th>Attempt</th>
                          <th>Status</th>
                          <th>Response</th>
                          <th>Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {deliveriesQuery.data?.items.map((delivery) => (
                          <tr key={delivery.id}>
                            <td>{new Date(delivery.created_at).toLocaleString()}</td>
                            <td>{delivery.event_type}</td>
                            <td>{delivery.attempt_number}</td>
                            <td>
                              <Badge
                                tone={
                                  delivery.status === "success"
                                    ? "success"
                                    : delivery.status === "exhausted"
                                      ? "danger"
                                      : "warning"
                                }
                              >
                                {delivery.status}
                              </Badge>
                            </td>
                            <td>{delivery.response_status_code ?? "—"}</td>
                            <td style={{ fontSize: "var(--font-caption-size)" }}>{delivery.error_message ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </AdminLayout>
  );
}
