import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  listTemplateVersions,
  listTemplates,
  publishTemplateVersion,
  type TemplateVersion,
} from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";

/**
 * Phase 6's admin-facing Template Engine surface (spec §42's Template
 * lifecycle), given a proper home in the Phase 7 Admin Portal shell
 * (MANAGEMENT > Templates). Model Profiles / Processing Profiles moved to
 * their own AdminProfilesPage (AI > Processing Profiles) and Prompts to
 * AdminPromptsPage (AI > Prompts) — each nav section per spec §48.
 * Deliberately narrow — read the current state, publish a draft version.
 * Full template authoring (creating new templates/versions from the UI)
 * is not built here; use the REST API directly (app.templates.router)
 * until a richer editor is worth building.
 */
export function AdminTemplatesPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [expandedTemplateId, setExpandedTemplateId] = useState<string | null>(null);

  const templatesQuery = useQuery({ queryKey: ["admin", "templates"], queryFn: listTemplates });

  const versionsQuery = useQuery({
    queryKey: ["admin", "template-versions", expandedTemplateId],
    queryFn: () => listTemplateVersions(expandedTemplateId as string),
    enabled: expandedTemplateId !== null,
  });

  async function handlePublish(templateId: string, versionId: string) {
    if (!csrfToken) return;
    await publishTemplateVersion(templateId, versionId, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "templates"] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "template-versions", templateId] });
  }

  const canWrite = hasPermission("template:write");

  const versionColumns = (templateId: string): DataTableColumn<TemplateVersion>[] => [
    { key: "version", header: "Version", render: (v) => `v${v.version_number}` },
    { key: "status", header: "Status", render: (v) => <StatusBadge status={v.status} /> },
    { key: "categories", header: "Kategorien", render: (v) => v.extraction_categories.map((c) => c.key).join(", ") },
    {
      key: "actions",
      header: "",
      render: (v) =>
        canWrite && v.status === "draft" ? (
          <Button variant="primary" onClick={() => void handlePublish(templateId, v.id)}>
            Veröffentlichen
          </Button>
        ) : null,
    },
  ];

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Vorlagen</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        Vorlagen definieren, was aus einem Gespräch extrahiert wird und wie ein zusammengestelltes
        Dokument aufgebaut ist.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {templatesQuery.data?.map((template) => (
          <Card key={template.id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{template.name}</strong>{" "}
                <code style={{ color: "var(--text-muted)" }}>({template.key})</code>{" "}
                {template.current_published_version_id ? (
                  <Badge tone="success">veröffentlicht</Badge>
                ) : (
                  <Badge tone="neutral">nur Entwurf</Badge>
                )}
              </div>
              <Button
                variant="secondary"
                onClick={() =>
                  setExpandedTemplateId(expandedTemplateId === template.id ? null : template.id)
                }
              >
                {expandedTemplateId === template.id ? "Versionen ausblenden" : "Versionen anzeigen"}
              </Button>
            </div>
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
              {template.description}
            </p>

            {expandedTemplateId === template.id && versionsQuery.data && (
              <div style={{ marginTop: "var(--space-4)" }}>
                <DataTable
                  columns={versionColumns(template.id)}
                  rows={versionsQuery.data}
                  keyExtractor={(v) => v.id}
                />
              </div>
            )}
          </Card>
        ))}
      </div>
    </AdminLayout>
  );
}
