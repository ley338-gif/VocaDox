import { useQuery } from "@tanstack/react-query";

import { getModelsOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";

function statusBadge(installed: boolean) {
  return <Badge tone={installed ? "success" : "warning"}>{installed ? "installed" : "not installed"}</Badge>;
}

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

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Models</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        To install or update a model, use the <code>model-manager</code> CLI
        (see <code>docs/admin/model-installation.md</code>) — this page shows
        real, live-checked status only.
      </p>
      {overview && (
        <table style={{ width: "100%", marginTop: "var(--space-6)", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
              <th>Role</th>
              <th>Provider</th>
              <th>Model</th>
              <th>Status</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>Speech-to-text</td>
              <td>{String(overview.speech.provider)}</td>
              <td>{String(overview.speech.model)}</td>
              <td>{statusBadge(Boolean(overview.speech.installed))}</td>
              <td style={{ color: "var(--text-secondary)" }}>{String(overview.speech.detail ?? "")}</td>
            </tr>
            <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>Diarization</td>
              <td>{String(overview.diarization.provider)}</td>
              <td>{String(overview.diarization.model)}</td>
              <td>{statusBadge(Boolean(overview.diarization.installed))}</td>
              <td style={{ color: "var(--text-secondary)" }}>
                {String(overview.diarization.detail ?? "")}
              </td>
            </tr>
            <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>LLM (extraction)</td>
              <td>{overview.llm.provider}</td>
              <td>{overview.llm.model}</td>
              <td>{statusBadge(overview.llm.installed)}</td>
              <td style={{ color: "var(--text-secondary)" }}>{overview.llm.detail ?? ""}</td>
            </tr>
          </tbody>
        </table>
      )}
    </AdminLayout>
  );
}
