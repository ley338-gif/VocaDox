import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listPromptVersions, listPrompts, publishPromptVersion, type PromptVersion } from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";

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

  const versionColumns = (promptId: string): DataTableColumn<PromptVersion>[] => [
    { key: "version", header: "Version", render: (v) => `v${v.version_number}` },
    { key: "status", header: "Status", render: (v) => <StatusBadge status={v.status} /> },
    {
      key: "actions",
      header: "",
      render: (v) =>
        canWrite && v.status !== "published" && v.status !== "retired" ? (
          <Button variant="primary" onClick={() => void handlePublish(promptId, v.id)}>
            Veröffentlichen
          </Button>
        ) : null,
    },
  ];

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Prompts</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        Prompts enthalten den System-Prompt / die Kategorie-Anweisungen, die ein Verarbeitungsprofil
        für die LLM-Extraktion referenzieren kann. Das Veröffentlichen einer neuen Version zieht die
        zuvor veröffentlichte zurück (überschreibt sie nie).
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {promptsQuery.data?.map((prompt) => (
          <Card key={prompt.id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{prompt.name}</strong>{" "}
                <code style={{ color: "var(--text-muted)" }}>({prompt.key})</code>{" "}
                {prompt.current_published_version_id ? (
                  <Badge tone="success">veröffentlicht</Badge>
                ) : (
                  <Badge tone="neutral">nur Entwurf</Badge>
                )}
              </div>
              <Button
                variant="secondary"
                onClick={() =>
                  setExpandedPromptId(expandedPromptId === prompt.id ? null : prompt.id)
                }
              >
                {expandedPromptId === prompt.id ? "Versionen ausblenden" : "Versionen anzeigen"}
              </Button>
            </div>

            {expandedPromptId === prompt.id && versionsQuery.data && (
              <div style={{ marginTop: "var(--space-4)" }}>
                <DataTable
                  columns={versionColumns(prompt.id)}
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
