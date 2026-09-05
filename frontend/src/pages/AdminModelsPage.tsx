import { useQuery } from "@tanstack/react-query";

import { getModelsOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { DataTable, type DataTableColumn } from "../design-system/Table";

interface ModelRow {
  role: string;
  provider: string;
  model: string;
  installed: boolean;
  detail: string;
}

const COLUMNS: DataTableColumn<ModelRow>[] = [
  { key: "role", header: "Rolle", render: (row) => row.role },
  { key: "provider", header: "Anbieter", render: (row) => row.provider },
  { key: "model", header: "Modell", render: (row) => row.model },
  {
    key: "status",
    header: "Status",
    render: (row) => (
      <Badge tone={row.installed ? "success" : "warning"}>
        {row.installed ? "installiert" : "nicht installiert"}
      </Badge>
    ),
  },
  { key: "detail", header: "Detail", render: (row) => <span style={{ color: "var(--text-secondary)" }}>{row.detail}</span> },
];

/**
 * Phase 7 Admin Portal Models page: real status for speech/diarization/LLM
 * (Phase 3/4's existing provider `.status()` checks) — "Not installed, not
 * fake Healthy" (Phase 3 principle). Model installation itself stays the
 * Phase 3.1 `model-manager` CLI's job — this page surfaces status, it does
 * not add a web upload/install flow.
 */
export function AdminModelsPage() {
  const overviewQuery = useQuery({ queryKey: ["admin", "models"], queryFn: getModelsOverview });
  const overview = overviewQuery.data;

  const rows: ModelRow[] = overview
    ? [
        {
          role: "Sprache (STT)",
          provider: String(overview.speech.provider),
          model: String(overview.speech.model),
          installed: Boolean(overview.speech.installed),
          detail: String(overview.speech.detail ?? ""),
        },
        {
          role: "Diarisierung",
          provider: String(overview.diarization.provider),
          model: String(overview.diarization.model),
          installed: Boolean(overview.diarization.installed),
          detail: String(overview.diarization.detail ?? ""),
        },
        {
          role: "LLM (Extraktion)",
          provider: overview.llm.provider,
          model: overview.llm.model,
          installed: overview.llm.installed,
          detail: overview.llm.detail ?? "",
        },
      ]
    : [];

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Modelle</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        Zur Installation oder Aktualisierung eines Modells das <code>model-manager</code>-CLI
        verwenden (siehe <code>docs/admin/model-installation.md</code>) — diese Seite zeigt nur
        echten, live geprüften Status.
      </p>
      <DataTable columns={COLUMNS} rows={rows} keyExtractor={(row) => row.role} loading={overviewQuery.isLoading} />
    </AdminLayout>
  );
}
