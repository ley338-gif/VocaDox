import { useQuery } from "@tanstack/react-query";

import { getModelsOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";

/**
 * Phase 7 Admin Portal Speech page: the dedicated provider/model/status/
 * device view for speech-to-text (spec §48 nav has Speech as its own
 * section, distinct from the combined Models overview) — same data
 * source as AdminModelsPage's speech row, extended with the device field
 * Phase 3's `SpeechProviderStatus` already carries.
 */
export function AdminSpeechPage() {
  const overviewQuery = useQuery({ queryKey: ["admin", "models"], queryFn: getModelsOverview });
  const speech = overviewQuery.data?.speech;

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Speech</h1>
      {speech && (
        <dl style={{ marginTop: "var(--space-6)" }}>
          <dt style={{ fontWeight: 600 }}>Provider</dt>
          <dd>{String(speech.provider)}</dd>
          <dt style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Model</dt>
          <dd>{String(speech.model)}</dd>
          <dt style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Device</dt>
          <dd>
            {String(speech.device)}{" "}
            {Boolean(speech.cuda_available) && <Badge tone="info">CUDA</Badge>}
          </dd>
          <dt style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Status</dt>
          <dd>
            <Badge tone={speech.installed ? "success" : "warning"}>
              {speech.installed ? "installed" : "not installed"}
            </Badge>
          </dd>
          {Boolean(speech.detail) && (
            <>
              <dt style={{ fontWeight: 600, marginTop: "var(--space-3)" }}>Detail</dt>
              <dd style={{ color: "var(--text-secondary)" }}>{String(speech.detail)}</dd>
            </>
          )}
        </dl>
      )}
    </AdminLayout>
  );
}
