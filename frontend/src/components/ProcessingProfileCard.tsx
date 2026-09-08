import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type EffectiveConfig,
  getEffectiveConfig,
  listProcessingProfiles,
  listProcessingProfileVersions,
  setConfigOverride,
} from "../api/profiles";
import { useAuth } from "../auth/useAuth";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Select } from "../design-system/FormControls";
import { ErrorState, Skeleton } from "../design-system/States";

const SOURCE_LABELS: Record<NonNullable<EffectiveConfig["fields"][number]["source"]>, string> = {
  system_default: "Systemstandard",
  processing_profile: "über Verarbeitungsprofil",
  conversation_override: "manuell überschrieben",
};

/**
 * Post-GA: gives the spec §20 CONVERSATION OVERRIDE layer a UI, for the
 * one field that matters day-to-day -- which Template this conversation
 * uses. `getEffectiveConfig`/`setConfigOverride` (app.conversations.
 * router) already existed and were already tested, but nothing in the
 * frontend ever called them -- a conversation auto-assigned the wrong
 * profile at creation had no fix short of a raw API call.
 *
 * Deliberately profile-level, not template-level, matching
 * NewConversationPage's "user sees friendly names, never the underlying
 * template/model/prompt composition" principle: picking a Processing
 * Profile here submits that profile's *current published version*'s
 * template_id/template_version_id as a per-field override -- never a
 * wholesale profile swap, since the backend endpoint deliberately
 * doesn't support that (spec: "never a wholesale profile replacement").
 *
 * `config_overrides` has no "processing_profile_id" field -- only the
 * individual resolved fields (template_id, template_version_id, ...) can
 * be overridden -- so `effective-config`'s own `processing_profile_id`
 * stays the conversation's originally *linked* profile even after a
 * template override is applied; it would silently show the wrong name
 * once overridden. The displayed profile is instead resolved by matching
 * the effective (template_id, template_version_id) pair against every
 * selectable profile's own published-version pair, which stays correct
 * in every case (no override, applied override, or an override set some
 * other way entirely, e.g. directly via the API).
 */
export function ProcessingProfileCard({ conversationId }: { conversationId: string }) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const effectiveConfigKey = ["conversation", conversationId, "effective-config"];
  const effectiveConfigQuery = useQuery({
    queryKey: effectiveConfigKey,
    queryFn: () => getEffectiveConfig(conversationId),
  });
  const profilesQuery = useQuery({
    queryKey: ["processing-profiles"],
    queryFn: listProcessingProfiles,
  });

  const canEdit = hasPermission("conversation:update");
  const selectableProfiles = (profilesQuery.data ?? []).filter(
    (p) => p.enabled && p.current_published_version_id !== null
  );

  const profileVersionQueries = useQueries({
    queries: selectableProfiles.map((p) => ({
      queryKey: ["processing-profile-versions", p.id],
      queryFn: () => listProcessingProfileVersions(p.id),
    })),
  });

  const templateField = effectiveConfigQuery.data?.fields.find((f) => f.field === "template_id");
  const templateVersionField = effectiveConfigQuery.data?.fields.find(
    (f) => f.field === "template_version_id"
  );
  const isOverridden = templateField?.source === "conversation_override";

  const currentProfile = selectableProfiles.find((p, index) => {
    const publishedVersion = profileVersionQueries[index]?.data?.find(
      (v) => v.id === p.current_published_version_id
    );
    return (
      publishedVersion !== undefined &&
      publishedVersion.template_id === templateField?.value &&
      publishedVersion.template_version_id === templateVersionField?.value
    );
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: effectiveConfigKey });
  }

  const applyMutation = useMutation({
    mutationFn: async (profileId: string) => {
      if (!csrfToken) throw new Error("Fehlendes CSRF-Token.");
      const profile = selectableProfiles.find((p) => p.id === profileId);
      const versions = await listProcessingProfileVersions(profileId);
      const version = versions.find((v) => v.id === profile?.current_published_version_id);
      if (!version) throw new Error("Veröffentlichte Version des Profils nicht gefunden.");
      await setConfigOverride(
        conversationId,
        { template_id: version.template_id, template_version_id: version.template_version_id },
        csrfToken
      );
    },
    onSuccess: () => {
      setError(null);
      setSelectedProfileId("");
      invalidate();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Profil konnte nicht übernommen werden."),
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      if (!csrfToken) throw new Error("Fehlendes CSRF-Token.");
      await setConfigOverride(
        conversationId,
        { template_id: null, template_version_id: null },
        csrfToken
      );
    },
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Zurücksetzen fehlgeschlagen."),
  });

  if (effectiveConfigQuery.isLoading) return <Skeleton height="3rem" />;
  if (!effectiveConfigQuery.data) return null;

  return (
    <div style={{ display: "grid", gap: "var(--space-2)" }}>
      <div>
        <Badge tone={isOverridden ? "warning" : "neutral"}>
          {currentProfile ? currentProfile.name : "Benutzerdefiniert"}
        </Badge>{" "}
        {templateField?.source && (
          <span style={{ fontSize: "var(--font-caption-size)", color: "var(--text-muted)" }}>
            {SOURCE_LABELS[templateField.source]}
          </span>
        )}
      </div>

      {canEdit && (
        <>
          <Select
            aria-label="Verarbeitungsprofil für diese Konversation ändern"
            value={selectedProfileId}
            onChange={(event) => setSelectedProfileId(event.target.value)}
          >
            <option value="">Profil wählen…</option>
            {selectableProfiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button
              variant="secondary"
              type="button"
              disabled={!selectedProfileId || applyMutation.isPending}
              onClick={() => applyMutation.mutate(selectedProfileId)}
            >
              Übernehmen
            </Button>
            {isOverridden && (
              <Button
                variant="tertiary"
                type="button"
                disabled={resetMutation.isPending}
                onClick={() => resetMutation.mutate()}
              >
                Zurücksetzen
              </Button>
            )}
          </div>
          {error && <ErrorState message={error} />}
        </>
      )}
    </div>
  );
}
