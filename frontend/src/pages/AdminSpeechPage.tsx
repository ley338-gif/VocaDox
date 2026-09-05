import { useQuery } from "@tanstack/react-query";

import { getModelsOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Card } from "../design-system/Card";
import { Skeleton } from "../design-system/States";

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
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)", marginBottom: "var(--space-6)" }}>
        Sprache
      </h1>
      {overviewQuery.isLoading && <Skeleton height="8rem" />}
      {speech && (
        <Card>
          <dl style={{ display: "grid", gap: "var(--space-3)", margin: 0 }}>
            <div>
              <dt style={{ fontWeight: 600 }}>Anbieter</dt>
              <dd style={{ margin: 0 }}>{String(speech.provider)}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>Modell</dt>
              <dd style={{ margin: 0 }}>{String(speech.model)}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>Gerät</dt>
              <dd style={{ margin: 0 }}>
                {String(speech.device)} {Boolean(speech.cuda_available) && <Badge tone="info">CUDA</Badge>}
              </dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>Status</dt>
              <dd style={{ margin: 0 }}>
                <Badge tone={speech.installed ? "success" : "warning"}>
                  {speech.installed ? "installiert" : "nicht installiert"}
                </Badge>
              </dd>
            </div>
            {Boolean(speech.detail) && (
              <div>
                <dt style={{ fontWeight: 600 }}>Detail</dt>
                <dd style={{ margin: 0, color: "var(--text-secondary)" }}>{String(speech.detail)}</dd>
              </div>
            )}
          </dl>
        </Card>
      )}
    </AdminLayout>
  );
}
