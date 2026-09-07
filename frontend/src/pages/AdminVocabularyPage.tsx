import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { listOrganizations } from "../api/admin";
import { listTemplates } from "../api/templates";
import {
  createVocabulary,
  deleteVocabulary,
  listVocabulary,
  type VocabularyEntry,
} from "../api/vocabulary";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { FormField } from "../design-system/FormField";
import { Select, TextInput } from "../design-system/FormControls";
import { Modal } from "../design-system/Modal";
import { ErrorState } from "../design-system/States";

/**
 * Post-GA P0-3 Admin Portal page: custom transcription vocabulary
 * (hotwords/initial_prompt), organization-wide or narrowed to a single
 * Template — see backend app.vocabulary for the resolution rule
 * (per-template entry wins, otherwise the org-wide entry, otherwise
 * nothing applies).
 */
export function AdminVocabularyPage() {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [expandedOrgId, setExpandedOrgId] = useState<string | null>(null);
  const [showCreateFor, setShowCreateFor] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", templateId: "", terms: "", initialPrompt: "" });
  const [error, setError] = useState<string | null>(null);

  const orgsQuery = useQuery({ queryKey: ["admin", "organizations"], queryFn: listOrganizations });
  const templatesQuery = useQuery({ queryKey: ["templates"], queryFn: listTemplates });

  async function handleCreate(orgId: string) {
    if (!csrfToken || !form.name.trim()) return;
    setError(null);
    try {
      await createVocabulary(
        orgId,
        {
          name: form.name.trim(),
          template_id: form.templateId || null,
          terms: form.terms
            .split(/[,\n]/)
            .map((t) => t.trim())
            .filter(Boolean),
          initial_prompt: form.initialPrompt.trim() || null,
        },
        csrfToken
      );
      setForm({ name: "", templateId: "", terms: "", initialPrompt: "" });
      setShowCreateFor(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "vocabulary", orgId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Eintrag konnte nicht erstellt werden.");
    }
  }

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)", marginBottom: "var(--space-4)" }}>
        Fachwortschatz
      </h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: "var(--space-4)" }}>
        Organisationsweite oder pro Vorlage geltende Fachbegriffe, die der Spracherkennung als
        Hinweis mitgegeben werden — höchstens ein Eintrag pro Organisation ohne Vorlage, und
        höchstens einer pro (Organisation, Vorlage)-Kombination.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {orgsQuery.data?.map((org) => (
          <Card key={org.id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>{org.name}</strong>
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <Button variant="tertiary" onClick={() => setShowCreateFor(org.id)}>
                  <Plus size={16} aria-hidden="true" /> Eintrag hinzufügen
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setExpandedOrgId(expandedOrgId === org.id ? null : org.id)}
                >
                  {expandedOrgId === org.id ? "Ausblenden" : "Einträge anzeigen"}
                </Button>
              </div>
            </div>
            {expandedOrgId === org.id && (
              <VocabularyList orgId={org.id} templates={templatesQuery.data ?? []} />
            )}
          </Card>
        ))}
      </div>

      <Modal
        open={showCreateFor !== null}
        onClose={() => setShowCreateFor(null)}
        title="Neuer Fachwortschatz-Eintrag"
      >
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <FormField label="Name" required>
            <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </FormField>
          <FormField label="Vorlage (optional)" hint="Leer lassen für organisationsweit">
            <Select
              value={form.templateId}
              onChange={(e) => setForm({ ...form, templateId: e.target.value })}
            >
              <option value="">Organisationsweit</option>
              {templatesQuery.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Fachbegriffe" hint="Kommagetrennt oder eine Zeile pro Begriff">
            <TextInput
              value={form.terms}
              onChange={(e) => setForm({ ...form, terms: e.target.value })}
              placeholder="Ramipril, Metoprolol, Simvastatin"
            />
          </FormField>
          <FormField label="Kontext-Hinweis (optional)" hint="Ein Beispielsatz zur Stilprägung">
            <TextInput
              value={form.initialPrompt}
              onChange={(e) => setForm({ ...form, initialPrompt: e.target.value })}
              placeholder="Ärztliches Gespräch über Medikation."
            />
          </FormField>
          {error && <ErrorState message={error} />}
          <Button variant="primary" onClick={() => showCreateFor && void handleCreate(showCreateFor)}>
            Erstellen
          </Button>
        </div>
      </Modal>
    </AdminLayout>
  );
}

function VocabularyList({
  orgId,
  templates,
}: {
  orgId: string;
  templates: { id: string; name: string }[];
}) {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const entriesQuery = useQuery({
    queryKey: ["admin", "vocabulary", orgId],
    queryFn: () => listVocabulary(orgId),
  });
  const templateNameById = new Map(templates.map((t) => [t.id, t.name]));

  async function handleDelete(entry: VocabularyEntry) {
    if (!csrfToken) return;
    await deleteVocabulary(orgId, entry.id, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "vocabulary", orgId] });
  }

  return (
    <div style={{ marginTop: "var(--space-3)", display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      {(entriesQuery.data ?? []).length === 0 && (
        <p style={{ color: "var(--text-muted)" }}>Noch kein Fachwortschatz konfiguriert.</p>
      )}
      {entriesQuery.data?.map((entry) => (
        <div
          key={entry.id}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            padding: "var(--space-3)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <div>
            <strong>{entry.name}</strong>{" "}
            <span style={{ color: "var(--text-muted)" }}>
              ({entry.template_id ? (templateNameById.get(entry.template_id) ?? "Vorlage") : "organisationsweit"})
            </span>
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-1)" }}>
              {entry.terms.join(", ") || "(keine Begriffe)"}
            </p>
            {entry.initial_prompt && (
              <p style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                „{entry.initial_prompt}“
              </p>
            )}
          </div>
          <Button variant="tertiary" onClick={() => void handleDelete(entry)}>
            <Trash2 size={16} aria-hidden="true" />
          </Button>
        </div>
      ))}
    </div>
  );
}
