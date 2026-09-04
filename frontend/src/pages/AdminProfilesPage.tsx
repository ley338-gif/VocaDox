import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getModelLifecycle,
  LIFECYCLE_CHECKLIST_KEYS,
  transitionModelLifecycle,
} from "../api/analytics";
import {
  createProcessingProfileVersion,
  listModelProfiles,
  listProcessingProfileVersions,
  listProcessingProfiles,
  publishProcessingProfileVersion,
} from "../api/profiles";
import { listTemplateVersions, listTemplates } from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Select, TextInput } from "../design-system/FormControls";

/**
 * Phase 7 Admin Portal Processing Profiles page (AI > Processing
 * Profiles). Extends Phase 6's narrow read-only surface with the
 * Known-Limitation gap it explicitly flagged: Speech/Diarization Profile
 * selection/editing was not yet exposed the same way Extraction
 * Model/Template selection was. `speech_provider_config`/
 * `diarization_provider_config` have existed on `ProcessingProfileVersion`
 * since Phase 6's migration — this page is the first UI to actually
 * create a new draft version with them set, via the existing
 * `POST /processing-profiles/{id}/versions` endpoint (no backend change
 * needed). Still Settings-driven at the provider-selection level (a real
 * `SpeechProfile`/`DiarizationProfile` DB entity remains out of scope per
 * `docs/architecture/model-management-foundation.md`) — this closes the
 * "no UI to edit these per-profile hints" gap, not that larger one.
 */
export function AdminProfilesPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [expandedProfileId, setExpandedProfileId] = useState<string | null>(null);
  const [showNewVersion, setShowNewVersion] = useState<string | null>(null);

  const processingProfilesQuery = useQuery({
    queryKey: ["admin", "processing-profiles"],
    queryFn: listProcessingProfiles,
  });
  const modelProfilesQuery = useQuery({
    queryKey: ["admin", "model-profiles"],
    queryFn: listModelProfiles,
  });
  const templatesQuery = useQuery({ queryKey: ["admin", "templates"], queryFn: listTemplates });
  const versionsQuery = useQuery({
    queryKey: ["admin", "processing-profile-versions", expandedProfileId],
    queryFn: () => listProcessingProfileVersions(expandedProfileId as string),
    enabled: expandedProfileId !== null,
  });

  const canWrite = hasPermission("processing-profile:write");
  const [expandedLifecycleId, setExpandedLifecycleId] = useState<string | null>(null);

  async function handlePublish(profileId: string, versionId: string) {
    if (!csrfToken) return;
    await publishProcessingProfileVersion(profileId, versionId, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "processing-profiles"] });
    await queryClient.invalidateQueries({
      queryKey: ["admin", "processing-profile-versions", profileId],
    });
  }

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Processing Profiles
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Processing Profiles bundle a template, extraction model, language,
        retention policy, and speech/diarization provider hints into the
        friendly, named preset a user picks when starting a conversation.
      </p>

      {processingProfilesQuery.data?.map((profile) => (
        <div
          key={profile.id}
          style={{
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginTop: "var(--space-4)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>{profile.name}</strong>{" "}
              <code style={{ color: "var(--text-muted)" }}>({profile.key})</code>{" "}
              {profile.is_system_default && <Badge tone="info">system default</Badge>}{" "}
              {profile.current_published_version_id ? (
                <Badge tone="success">published</Badge>
              ) : (
                <Badge tone="neutral">draft only</Badge>
              )}
            </div>
            <Button
              variant="secondary"
              onClick={() =>
                setExpandedProfileId(expandedProfileId === profile.id ? null : profile.id)
              }
            >
              {expandedProfileId === profile.id ? "Hide versions" : "Show versions"}
            </Button>
          </div>
          <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
            {profile.description}
          </p>

          {expandedProfileId === profile.id && (
            <>
              {versionsQuery.data && (
                <table style={{ width: "100%", marginTop: "var(--space-4)" }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>Version</th>
                      <th style={{ textAlign: "left" }}>Status</th>
                      <th style={{ textAlign: "left" }}>Speech config</th>
                      <th style={{ textAlign: "left" }}>Diarization config</th>
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
                        <td style={{ fontSize: "var(--font-caption-size)" }}>
                          {version.speech_provider_config
                            ? JSON.stringify(version.speech_provider_config)
                            : "—"}
                        </td>
                        <td style={{ fontSize: "var(--font-caption-size)" }}>
                          {version.diarization_provider_config
                            ? JSON.stringify(version.diarization_provider_config)
                            : "—"}
                        </td>
                        <td>
                          {canWrite && version.status === "draft" && (
                            <Button
                              variant="primary"
                              onClick={() => void handlePublish(profile.id, version.id)}
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

              {canWrite && (
                <div style={{ marginTop: "var(--space-4)" }}>
                  <Button
                    variant="secondary"
                    onClick={() =>
                      setShowNewVersion(showNewVersion === profile.id ? null : profile.id)
                    }
                  >
                    {showNewVersion === profile.id ? "Cancel" : "New draft version"}
                  </Button>
                  {showNewVersion === profile.id && (
                    <NewVersionForm
                      processingProfileId={profile.id}
                      templates={templatesQuery.data ?? []}
                      modelProfiles={modelProfilesQuery.data ?? []}
                      onCreated={() => {
                        setShowNewVersion(null);
                        void queryClient.invalidateQueries({
                          queryKey: ["admin", "processing-profile-versions", profile.id],
                        });
                      }}
                    />
                  )}
                </div>
              )}
            </>
          )}
        </div>
      ))}

      <section style={{ marginTop: "var(--space-8)" }}>
        <h2 style={{ fontSize: "var(--font-h2-size)" }}>Model Profiles</h2>
        <p style={{ color: "var(--text-secondary)" }}>
          Lifecycle: AVAILABLE → TESTING → PILOT → PRODUCTION → RETIRED, with rollback to any
          earlier status. Every transition is an explicit admin action — nothing here ever
          changes automatically.
        </p>
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
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{mp.name}</strong> — {mp.provider}/{mp.model_identifier} (v{mp.version}){" "}
                {mp.enabled ? (
                  <Badge tone="success">enabled</Badge>
                ) : (
                  <Badge tone="neutral">disabled</Badge>
                )}{" "}
                <Badge tone={LIFECYCLE_TONE[mp.lifecycle_status] ?? "neutral"}>
                  {mp.lifecycle_status}
                </Badge>
              </div>
              <Button
                variant="secondary"
                onClick={() =>
                  setExpandedLifecycleId(expandedLifecycleId === mp.id ? null : mp.id)
                }
              >
                {expandedLifecycleId === mp.id ? "Hide lifecycle" : "Lifecycle"}
              </Button>
            </div>
            {expandedLifecycleId === mp.id && <ModelLifecyclePanel modelProfileId={mp.id} />}
          </div>
        ))}
      </section>
    </AdminLayout>
  );
}

const LIFECYCLE_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  available: "neutral",
  testing: "info",
  pilot: "warning",
  production: "success",
  retired: "danger",
};

const LIFECYCLE_ORDER = ["available", "testing", "pilot", "production", "retired"];

function ModelLifecyclePanel({ modelProfileId }: { modelProfileId: string }) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const canPromote = hasPermission("model-profile:promote");
  const [checklist, setChecklist] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const lifecycleQuery = useQuery({
    queryKey: ["admin", "model-profile-lifecycle", modelProfileId],
    queryFn: () => getModelLifecycle(modelProfileId),
  });

  const currentStatus = lifecycleQuery.data?.lifecycle_status ?? "available";
  const currentIndex = LIFECYCLE_ORDER.indexOf(currentStatus);
  const nextStatus = LIFECYCLE_ORDER[currentIndex + 1];

  async function refresh() {
    await queryClient.invalidateQueries({
      queryKey: ["admin", "model-profile-lifecycle", modelProfileId],
    });
    await queryClient.invalidateQueries({ queryKey: ["admin", "model-profiles"] });
  }

  async function handlePromote() {
    if (!csrfToken || !nextStatus) return;
    setError(null);
    try {
      await transitionModelLifecycle(
        modelProfileId,
        { to_status: nextStatus, is_rollback: false, checklist, note: note || null },
        csrfToken
      );
      setNote("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "transition failed");
    }
  }

  async function handleRollback(toStatus: string) {
    if (!csrfToken) return;
    setError(null);
    try {
      await transitionModelLifecycle(
        modelProfileId,
        { to_status: toStatus, is_rollback: true, note: note || null },
        csrfToken
      );
      setNote("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "rollback failed");
    }
  }

  return (
    <div style={{ marginTop: "var(--space-4)", paddingTop: "var(--space-3)", borderTop: "1px solid var(--border-default)" }}>
      {canPromote && (
        <div style={{ display: "grid", gap: "var(--space-2)", maxWidth: "480px" }}>
          {nextStatus && (
            <>
              <div style={{ fontWeight: 600 }}>Promote to {nextStatus}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
                {LIFECYCLE_CHECKLIST_KEYS.map((key) => (
                  <label key={key} style={{ display: "flex", gap: "var(--space-1)" }}>
                    <input
                      type="checkbox"
                      checked={Boolean(checklist[key])}
                      onChange={(e) => setChecklist({ ...checklist, [key]: e.target.checked })}
                    />
                    {key.replace(/_/g, " ")}
                  </label>
                ))}
              </div>
              <TextInput
                placeholder="Note (optional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <Button variant="primary" onClick={() => void handlePromote()}>
                Promote to {nextStatus}
              </Button>
            </>
          )}
          {currentIndex > 0 && (
            <div>
              <div style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Rollback</div>
              <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
                {LIFECYCLE_ORDER.slice(0, currentIndex).map((status) => (
                  <Button
                    key={status}
                    variant="secondary"
                    onClick={() => void handleRollback(status)}
                  >
                    → {status}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {currentStatus === "retired" && (
            <div>
              <div style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Reactivate</div>
              <Button variant="secondary" onClick={() => void handleRollback("available")}>
                → available
              </Button>
            </div>
          )}
          {error && <p style={{ color: "var(--color-danger)" }}>{error}</p>}
        </div>
      )}

      <h4 style={{ marginTop: "var(--space-4)" }}>History</h4>
      <ul>
        {lifecycleQuery.data?.events.map((event) => (
          <li key={event.id}>
            {new Date(event.created_at).toLocaleString()} —{" "}
            {event.from_status ? `${event.from_status} → ` : ""}
            {event.to_status}
            {event.is_rollback ? " (rollback)" : ""}
            {event.note ? `: ${event.note}` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}

function NewVersionForm({
  processingProfileId,
  templates,
  modelProfiles,
  onCreated,
}: {
  processingProfileId: string;
  templates: { id: string; key: string; current_published_version_id: string | null }[];
  modelProfiles: { id: string; name: string; purpose: string }[];
  onCreated: () => void;
}) {
  const { csrfToken } = useAuth();
  const [templateId, setTemplateId] = useState("");
  const [extractionModelProfileId, setExtractionModelProfileId] = useState("");
  const [language, setLanguage] = useState("auto");
  const [speechConfigText, setSpeechConfigText] = useState("{}");
  const [diarizationConfigText, setDiarizationConfigText] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const templateVersionsQuery = useQuery({
    queryKey: ["admin", "template-versions-for-profile", templateId],
    queryFn: () => listTemplateVersions(templateId),
    enabled: templateId !== "",
  });
  const publishedVersion = templateVersionsQuery.data?.find((v) => v.status === "published");

  async function handleSubmit() {
    if (!csrfToken || !templateId || !publishedVersion) {
      setError("Choose a template with a published version.");
      return;
    }
    let speechConfig: Record<string, unknown> | null = null;
    let diarizationConfig: Record<string, unknown> | null = null;
    try {
      speechConfig = speechConfigText.trim() ? JSON.parse(speechConfigText) : null;
      diarizationConfig = diarizationConfigText.trim() ? JSON.parse(diarizationConfigText) : null;
    } catch {
      setError("Speech/diarization config must be valid JSON.");
      return;
    }
    setError(null);
    try {
      await createProcessingProfileVersion(
        processingProfileId,
        {
          template_id: templateId,
          template_version_id: publishedVersion.id,
          extraction_model_profile_id: extractionModelProfileId || null,
          language,
          speech_provider_config: speechConfig,
          diarization_provider_config: diarizationConfig,
        },
        csrfToken
      );
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to create draft version");
    }
  }

  return (
    <div
      style={{
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-4)",
        marginTop: "var(--space-3)",
        display: "grid",
        gap: "var(--space-3)",
        maxWidth: "480px",
      }}
    >
      <label>
        Template
        <Select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
          <option value="">Choose a template…</option>
          {templates
            .filter((t) => t.current_published_version_id)
            .map((t) => (
              <option key={t.id} value={t.id}>
                {t.key}
              </option>
            ))}
        </Select>
      </label>
      <label>
        Extraction model
        <Select
          value={extractionModelProfileId}
          onChange={(e) => setExtractionModelProfileId(e.target.value)}
        >
          <option value="">(inherit)</option>
          {modelProfiles
            .filter((m) => m.purpose === "extraction")
            .map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
        </Select>
      </label>
      <label>
        Language
        <TextInput value={language} onChange={(e) => setLanguage(e.target.value)} />
      </label>
      <label>
        Speech provider config (JSON)
        <textarea
          value={speechConfigText}
          onChange={(e) => setSpeechConfigText(e.target.value)}
          rows={3}
          style={{ width: "100%", fontFamily: "monospace" }}
        />
      </label>
      <label>
        Diarization provider config (JSON)
        <textarea
          value={diarizationConfigText}
          onChange={(e) => setDiarizationConfigText(e.target.value)}
          rows={3}
          style={{ width: "100%", fontFamily: "monospace" }}
        />
      </label>
      {error && <p style={{ color: "var(--color-danger)" }}>{error}</p>}
      <Button variant="primary" onClick={() => void handleSubmit()}>
        Create draft version
      </Button>
    </div>
  );
}
