import { useQuery } from "@tanstack/react-query";

import { getModelsOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";

/** Phase 7 Admin Portal Diarization page — same pattern as AdminSpeechPage. */
export function AdminDiarizationPage() {
  const overviewQuery = useQuery({ queryKey: ["admin", "models"], queryFn: getModelsOverview });
  const diarization = overviewQuery.data?.diarization;

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Diarization
      </h1>
      {diarization && (
        <dl style={{ marginTop: "var(--space-6)" }}>
          <dt style={{ fontWeight: 600 }}>Provider</dt>
          <dd>{String(diarization.provider)}</dd>
          <dt style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Model</dt>
          <dd>{String(diarization.model)}</dd>
          <dt style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Status</dt>
          <dd>
            <Badge tone={diarization.installed ? "success" : "warning"}>
              {diarization.installed ? "installed" : "not installed"}
            </Badge>
          </dd>
          {Boolean(diarization.detail) && (
            <>
              <dt style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Detail</dt>
              <dd style={{ color: "var(--text-secondary)" }}>{String(diarization.detail)}</dd>
            </>
          )}
        </dl>
      )}
    </AdminLayout>
  );
}
