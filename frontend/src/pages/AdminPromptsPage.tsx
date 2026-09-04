import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listPromptVersions, listPrompts, publishPromptVersion } from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";

/**
 * Phase 7 Admin Portal Prompts page: the Prompt/PromptVersion lifecycle
 * (DRAFT -> TEST -> PUBLISHED -> RETIRED, spec §43) — the backend API for
 * this has existed since Phase 6 (app.templates.router's prompts_router)
 * but had no dedicated admin page until now. Publish auto-retires the
 * previously-published version (never edits it in place) — the same
 * non-destructive-versioning rule Templates already use.
 */
export function AdminPromptsPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [expandedPromptId, setExpandedPromptId] = useState<string | null>(null);

  const promptsQuery = useQuery({ queryKey: ["admin", "prompts"], queryFn: listPrompts });
  const versionsQuery = useQuery({
    queryKey: ["admin", "prompt-versions", expandedPromptId],
    queryFn: () => listPromptVersions(expandedPromptId as string),
    enabled: expandedPromptId !== null,
  });

  const canWrite = hasPermission("template:write");

  async function handlePublish(promptId: string, versionId: string) {
    if (!csrfToken) return;
    await publishPromptVersion(promptId, versionId, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "prompts"] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "prompt-versions", promptId] });
  }

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Prompts</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Prompts carry the system prompt / category instructions a Processing
        Profile can reference for LLM extraction. Publishing a new version
        retires (never overwrites) the previously published one.
      </p>

      {promptsQuery.data?.map((prompt) => (
        <div
          key={prompt.id}
          style={{
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginTop: "var(--space-4)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>{prompt.name}</strong>{" "}
              <code style={{ color: "var(--text-muted)" }}>({prompt.key})</code>{" "}
              {prompt.current_published_version_id ? (
                <Badge tone="success">published</Badge>
              ) : (
                <Badge tone="neutral">draft only</Badge>
              )}
            </div>
            <Button
              variant="secondary"
              onClick={() =>
                setExpandedPromptId(expandedPromptId === prompt.id ? null : prompt.id)
              }
            >
              {expandedPromptId === prompt.id ? "Hide versions" : "Show versions"}
            </Button>
          </div>

          {expandedPromptId === prompt.id && versionsQuery.data && (
            <table style={{ width: "100%", marginTop: "var(--space-4)" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Version</th>
                  <th style={{ textAlign: "left" }}>Status</th>
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
                      {canWrite && version.status !== "published" && version.status !== "retired" && (
                        <Button
                          variant="primary"
                          onClick={() => void handlePublish(prompt.id, version.id)}
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
    </AdminLayout>
  );
}
