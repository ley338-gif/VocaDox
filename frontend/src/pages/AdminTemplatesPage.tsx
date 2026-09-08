import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { type AdminOrganization, listOrganizations } from "../api/admin";
import { ApiError } from "../api/client";
import {
  type CategoryDefinition,
  createTemplate,
  createTemplateVersion,
  letterheadLogoUrl,
  listTemplateVersions,
  listTemplates,
  publishTemplateVersion,
  type TemplateVersion,
  updateTemplateOrganization,
  uploadLetterheadLogo,
} from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { Select, TextInput, Textarea } from "../design-system/FormControls";
import { ErrorState } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";

/**
 * Phase 6's admin-facing Template Engine surface (spec §42's Template
 * lifecycle), given a proper home in the Phase 7 Admin Portal shell
 * (MANAGEMENT > Templates). Model Profiles / Processing Profiles moved to
 * their own AdminProfilesPage (AI > Processing Profiles) and Prompts to
 * AdminPromptsPage (AI > Prompts) — each nav section per spec §48.
 *
 * Post-GA: authoring is real now — "Neue Vorlage erstellen"/"Neue
 * Entwurfsversion" (mirrors AdminProfilesPage.tsx's NewProfileForm/
 * NewVersionForm pattern), an optional organization tag per template
 * (light scoping only — see app.templates.router's docstring, no per-org
 * self-service isolation), and the "freeform" document_layout (a
 * template author's own free-text body with `[category_n]` placeholders,
 * plus an optional letterhead logo). `extraction_categories` stays a raw
 * JSON textarea — its nested per-field shape is too complex for a good
 * dynamic form yet; `presentation`'s simpler `{category, title}` shape
 * gets a real add/remove row editor.
 */
export function AdminTemplatesPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [expandedTemplateId, setExpandedTemplateId] = useState<string | null>(null);
  const [showNewVersion, setShowNewVersion] = useState<string | null>(null);
  const [showNewTemplate, setShowNewTemplate] = useState(false);

  const templatesQuery = useQuery({ queryKey: ["admin", "templates"], queryFn: listTemplates });
  const orgsQuery = useQuery({ queryKey: ["admin", "organizations"], queryFn: listOrganizations });

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

  async function handleOrgChange(templateId: string, organizationId: string) {
    if (!csrfToken) return;
    await updateTemplateOrganization(templateId, organizationId || null, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "templates"] });
  }

  const canWrite = hasPermission("template:write");
  const orgName = (id: string | null) =>
    id ? (orgsQuery.data?.find((o) => o.id === id)?.name ?? id) : null;

  const versionColumns = (templateId: string): DataTableColumn<TemplateVersion>[] => [
    { key: "version", header: "Version", render: (v) => `v${v.version_number}` },
    { key: "status", header: "Status", render: (v) => <StatusBadge status={v.status} /> },
    {
      key: "layout",
      header: "Layout",
      render: (v) => (
        <span style={{ fontSize: "var(--font-caption-size)" }}>
          {v.document_layout === "sections" && "Abschnitte"}
          {v.document_layout === "letter" && "Brief"}
          {v.document_layout === "freeform" && "Freitext"}
        </span>
      ),
    },
    {
      key: "categories",
      header: "Kategorien",
      render: (v) => v.extraction_categories.map((c) => c.key).join(", "),
    },
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
            Vorlagen
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
            Vorlagen definieren, was aus einem Gespräch extrahiert wird und wie ein
            zusammengestelltes Dokument aufgebaut ist.
          </p>
        </div>
        {canWrite && (
          <Button variant="primary" onClick={() => setShowNewTemplate((s) => !s)}>
            {showNewTemplate ? "Abbrechen" : "Neue Vorlage erstellen"}
          </Button>
        )}
      </div>

      {showNewTemplate && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <TemplateForm
            mode="template"
            organizations={orgsQuery.data ?? []}
            onCreated={() => {
              setShowNewTemplate(false);
              void queryClient.invalidateQueries({ queryKey: ["admin", "templates"] });
            }}
          />
        </div>
      )}

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-3)",
          marginTop: "var(--space-6)",
        }}
      >
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
                )}{" "}
                {template.organization_id ? (
                  <Badge tone="info">{orgName(template.organization_id)}</Badge>
                ) : (
                  <Badge tone="neutral">Global</Badge>
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

            {canWrite && (
              <div
                style={{
                  marginTop: "var(--space-3)",
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                }}
              >
                <label style={{ fontSize: "var(--font-caption-size)", color: "var(--text-muted)" }}>
                  Organisation
                </label>
                <Select
                  value={template.organization_id ?? ""}
                  onChange={(e) => void handleOrgChange(template.id, e.target.value)}
                >
                  <option value="">kein Organisationsbezug (global)</option>
                  {orgsQuery.data?.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </Select>
              </div>
            )}

            {expandedTemplateId === template.id && versionsQuery.data && (
              <div style={{ marginTop: "var(--space-4)" }}>
                <DataTable
                  columns={versionColumns(template.id)}
                  rows={versionsQuery.data}
                  keyExtractor={(v) => v.id}
                />
              </div>
            )}

            {canWrite && expandedTemplateId === template.id && (
              <div style={{ marginTop: "var(--space-4)" }}>
                <Button
                  variant="secondary"
                  onClick={() =>
                    setShowNewVersion(showNewVersion === template.id ? null : template.id)
                  }
                >
                  {showNewVersion === template.id ? "Abbrechen" : "Neue Entwurfsversion"}
                </Button>
                {showNewVersion === template.id && (
                  <div style={{ marginTop: "var(--space-3)" }}>
                    <TemplateForm
                      mode="version"
                      templateId={template.id}
                      organizations={orgsQuery.data ?? []}
                      onCreated={() => {
                        setShowNewVersion(null);
                        void queryClient.invalidateQueries({
                          queryKey: ["admin", "template-versions", template.id],
                        });
                      }}
                    />
                  </div>
                )}
              </div>
            )}
          </Card>
        ))}
      </div>
    </AdminLayout>
  );
}

type DocumentLayoutOption = "sections" | "letter" | "freeform";

interface PresentationRow {
  category: string;
  title: string;
}

/** Shared by both "Neue Vorlage erstellen" and "Neue Entwurfsversion" —
 * the exact same content fields, just a different submit call at the end
 * (create_template vs. create_draft_version), matching
 * AdminProfilesPage.tsx's NewProfileForm/NewVersionForm split. */
function TemplateForm({
  mode,
  templateId,
  organizations,
  onCreated,
}: {
  mode: "template" | "version";
  templateId?: string;
  organizations: AdminOrganization[];
  onCreated: () => void;
}) {
  const { csrfToken } = useAuth();
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [categoriesText, setCategoriesText] = useState(
    '[{"key": "general_fact", "builtin": true}]'
  );
  const [presentationRows, setPresentationRows] = useState<PresentationRow[]>([
    { category: "general_fact", title: "Fakten" },
  ]);
  const [documentLayout, setDocumentLayout] = useState<DocumentLayoutOption>("sections");
  const [documentBody, setDocumentBody] = useState("");
  const [letterheadAssetKey, setLetterheadAssetKey] = useState<string | null>(null);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateRow(index: number, field: keyof PresentationRow, value: string) {
    setPresentationRows((rows) =>
      rows.map((row, i) => (i === index ? { ...row, [field]: value } : row))
    );
  }

  async function handleLogoChange(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file || !csrfToken) return;
    setUploadingLogo(true);
    setError(null);
    try {
      const { asset_key } = await uploadLetterheadLogo(file, csrfToken);
      setLetterheadAssetKey(asset_key);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Logo konnte nicht hochgeladen werden.");
    } finally {
      setUploadingLogo(false);
    }
  }

  async function handleSubmit() {
    let extractionCategories: CategoryDefinition[];
    try {
      extractionCategories = JSON.parse(categoriesText) as CategoryDefinition[];
    } catch {
      setError("Kategorien müssen gültiges JSON sein.");
      return;
    }
    const presentation = presentationRows.filter((r) => r.category.trim() && r.title.trim());
    if (!csrfToken || presentation.length === 0) {
      setError("Mindestens eine Kategorie/Titel-Zeile ist erforderlich.");
      return;
    }
    if (mode === "template" && (!key.trim() || !name.trim())) {
      setError("Schlüssel und Name sind erforderlich.");
      return;
    }
    setError(null);
    const payload = {
      extraction_categories: extractionCategories,
      presentation,
      document_layout: documentLayout,
      document_body: documentLayout === "freeform" ? documentBody : null,
      letterhead_logo_asset_key: letterheadAssetKey,
    };
    try {
      if (mode === "template") {
        await createTemplate(
          {
            key: key.trim(),
            name: name.trim(),
            description: description.trim() || null,
            organization_id: organizationId || null,
            ...payload,
          },
          csrfToken
        );
      } else {
        if (!templateId) return;
        await createTemplateVersion(templateId, payload, csrfToken);
      }
      onCreated();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Vorlage/Version konnte nicht erstellt werden."
      );
    }
  }

  return (
    <Card title={mode === "template" ? "Neue Vorlage" : undefined}>
      <div style={{ display: "grid", gap: "var(--space-3)", maxWidth: "560px" }}>
        {mode === "template" && (
          <>
            <label>
              Schlüssel (eindeutig, z. B. "meeting_de")
              <TextInput value={key} onChange={(e) => setKey(e.target.value)} />
            </label>
            <label>
              Name (Anzeigename)
              <TextInput value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
              Beschreibung (optional)
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                style={{ width: "100%" }}
              />
            </label>
            <label>
              Organisation (optional)
              <Select value={organizationId} onChange={(e) => setOrganizationId(e.target.value)}>
                <option value="">kein Organisationsbezug (global)</option>
                {organizations.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </Select>
            </label>
          </>
        )}

        <label>
          Extraktionskategorien (JSON)
          <Textarea
            value={categoriesText}
            onChange={(e) => setCategoriesText(e.target.value)}
            rows={5}
            style={{ width: "100%", fontFamily: "monospace" }}
          />
        </label>

        <div>
          <div style={{ marginBottom: "var(--space-1)" }}>Abschnitte (Kategorie → Titel)</div>
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            {presentationRows.map((row, index) => (
              <div key={index} style={{ display: "flex", gap: "var(--space-2)" }}>
                <TextInput
                  placeholder="Kategorie-Schlüssel"
                  value={row.category}
                  onChange={(e) => updateRow(index, "category", e.target.value)}
                />
                <TextInput
                  placeholder="Titel"
                  value={row.title}
                  onChange={(e) => updateRow(index, "title", e.target.value)}
                />
                <Button
                  variant="tertiary"
                  type="button"
                  onClick={() =>
                    setPresentationRows((rows) => rows.filter((_, i) => i !== index))
                  }
                >
                  Entfernen
                </Button>
              </div>
            ))}
            <Button
              variant="secondary"
              type="button"
              onClick={() =>
                setPresentationRows((rows) => [...rows, { category: "", title: "" }])
              }
            >
              + Zeile
            </Button>
          </div>
        </div>

        <label>
          Dokument-Layout
          <Select
            value={documentLayout}
            onChange={(e) => setDocumentLayout(e.target.value as DocumentLayoutOption)}
          >
            <option value="sections">Abschnitte</option>
            <option value="letter">Brief</option>
            <option value="freeform">Freitext mit Platzhaltern</option>
          </Select>
        </label>

        {documentLayout === "freeform" && (
          <label>
            Freitext-Vorlage
            <Textarea
              value={documentBody}
              onChange={(e) => setDocumentBody(e.target.value)}
              rows={12}
              style={{ width: "100%", fontFamily: "monospace" }}
              placeholder={
                "Sehr geehrte Kolleginnen und Kollegen,\n\n" +
                "wir berichten über [diagnose_1].\n\n" +
                "Mit freundlichen Grüßen"
              }
            />
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)", margin: "var(--space-1) 0 0" }}>
              Platzhalter im Format [Kategorie-Schlüssel_Nummer], z. B. [decision_1] für die erste
              erfasste Entscheidung. Fehlt der Fakt, erscheint ehrlich "[nicht erfasst: …]" — nie
              erfundener Text.
            </p>
          </label>
        )}

        <div>
          <div style={{ marginBottom: "var(--space-1)" }}>Briefkopf-Logo (optional, PNG/JPEG)</div>
          {letterheadAssetKey && (
            <div style={{ marginBottom: "var(--space-2)" }}>
              <img
                src={letterheadLogoUrl(letterheadAssetKey)}
                alt="Briefkopf-Logo"
                style={{ maxHeight: "60px", display: "block", marginBottom: "var(--space-1)" }}
              />
              <Button variant="tertiary" type="button" onClick={() => setLetterheadAssetKey(null)}>
                Entfernen
              </Button>
            </div>
          )}
          <input
            type="file"
            accept="image/png,image/jpeg"
            disabled={uploadingLogo}
            onChange={(e) => void handleLogoChange(e.target.files)}
          />
        </div>

        {error && <ErrorState message={error} />}
        <Button variant="primary" disabled={uploadingLogo} onClick={() => void handleSubmit()}>
          {mode === "template" ? "Vorlage erstellen" : "Entwurfsversion erstellen"}
        </Button>
      </div>
    </Card>
  );
}
