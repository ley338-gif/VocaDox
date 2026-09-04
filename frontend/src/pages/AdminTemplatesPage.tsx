import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listModelProfiles, listProcessingProfiles } from "../api/profiles";
import { listTemplateVersions, listTemplates, publishTemplateVersion } from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";

/**
 * Phase 6's admin-facing Template Engine / Processing Profile surface
 * (spec §42/§43's Template/Prompt lifecycle, §19's Processing Profiles).
 * Deliberately narrow — read the current state, publish a draft version —
 * matching the brief's "functional and consistent with the existing
 * design system... does not need Phase 7-grade polish" scope. Full
 * template/profile authoring (creating new templates/versions from the
 * UI) is not built here; use the REST API directly (app.templates.router /
 * app.profiles.router) until a richer editor is worth building.
 */
export function AdminTemplatesPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [expandedTemplateId, setExpandedTemplateId] = useState<string | null>(null);

  const templatesQuery = useQuery({ queryKey: ["admin", "templates"], queryFn: listTemplates });
  const processingProfilesQuery = useQuery({
    queryKey: ["admin", "processing-profiles"],
    queryFn: listProcessingProfiles,
  });
  const modelProfilesQuery = useQuery({
    queryKey: ["admin", "model-profiles"],
    queryFn: listModelProfiles,
  });

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
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Templates &amp; Processing Profiles
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Templates define what gets extracted from a conversation and how a
        composed document is organized. Processing Profiles bundle a
        template (plus model/language/retention choices) into the
        friendly, named preset a user picks when starting a conversation.
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

      <section style={{ marginTop: "var(--space-8)" }}>
        <h2 style={{ fontSize: "var(--font-h2-size)" }}>Processing Profiles</h2>
        {processingProfilesQuery.data?.map((profile) => (
          <div
            key={profile.id}
            style={{
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
              marginTop: "var(--space-3)",
            }}
          >
            <strong>{profile.name}</strong>{" "}
            <code style={{ color: "var(--text-muted)" }}>({profile.key})</code>{" "}
            {profile.is_system_default && <Badge tone="info">system default</Badge>}{" "}
            {profile.current_published_version_id ? (
              <Badge tone="success">published</Badge>
            ) : (
              <Badge tone="neutral">draft only</Badge>
            )}
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
              {profile.description}
            </p>
          </div>
        ))}
      </section>

      <section style={{ marginTop: "var(--space-8)" }}>
        <h2 style={{ fontSize: "var(--font-h2-size)" }}>Model Profiles</h2>
        {modelProfilesQuery.data?.map((mp) => (
          <div
            key={mp.id}
            style={{
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
              marginTop: "var(--space-3)",
            }}
          >
            <strong>{mp.name}</strong> — {mp.provider}/{mp.model_identifier} (v{mp.version})
            {mp.enabled ? (
              <Badge tone="success">enabled</Badge>
            ) : (
              <Badge tone="neutral">disabled</Badge>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}
