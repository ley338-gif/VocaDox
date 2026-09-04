import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listTemplateVersions, listTemplates, publishTemplateVersion } from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";

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

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Templates
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Templates define what gets extracted from a conversation and how a
        composed document is organized.
      </p>

      <section style={{ marginTop: "var(--space-8)" }}>
        <h2 style={{ fontSize: "var(--font-h2-size)" }}>Templates</h2>
        {templatesQuery.data?.map((template) => (
          <div
            key={template.id}
            style={{
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
              marginTop: "var(--space-3)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{template.name}</strong>{" "}
                <code style={{ color: "var(--text-muted)" }}>({template.key})</code>{" "}
                {template.current_published_version_id ? (
                  <Badge tone="success">published</Badge>
                ) : (
                  <Badge tone="neutral">draft only</Badge>
                )}
              </div>
              <Button
                variant="secondary"
                onClick={() =>
                  setExpandedTemplateId(expandedTemplateId === template.id ? null : template.id)
                }
              >
                {expandedTemplateId === template.id ? "Hide versions" : "Show versions"}
              </Button>
            </div>
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
              {template.description}
            </p>

            {expandedTemplateId === template.id && versionsQuery.data && (
              <table style={{ width: "100%", marginTop: "var(--space-4)" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Version</th>
                    <th style={{ textAlign: "left" }}>Status</th>
                    <th style={{ textAlign: "left" }}>Categories</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {versionsQuery.data.map((version) => (
                    <tr key={version.id}>
                      <td>v{version.version_number}</td>
                      <td>
                        <Badge tone={version.status === "published" ? "success" : "neutral"}>
                          {version.status}
                        </Badge>
                      </td>
                      <td>
                        {version.extraction_categories.map((c) => c.key).join(", ")}
                      </td>
                      <td>
                        {canWrite && version.status === "draft" && (
                          <Button
                            variant="primary"
                            onClick={() => void handlePublish(template.id, version.id)}
                          >
                            Publish
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </section>
    </AdminLayout>
  );
}
