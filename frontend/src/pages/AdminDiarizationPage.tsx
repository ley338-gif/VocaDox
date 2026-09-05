import { useQuery } from "@tanstack/react-query";

import { getModelsOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Card } from "../design-system/Card";
import { Skeleton } from "../design-system/States";

/** Phase 7 Admin Portal Diarization page — same pattern as AdminSpeechPage. */
export function AdminDiarizationPage() {
  const overviewQuery = useQuery({ queryKey: ["admin", "models"], queryFn: getModelsOverview });
  const diarization = overviewQuery.data?.diarization;

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)", marginBottom: "var(--space-6)" }}>
        Diarisierung
      </h1>
      {overviewQuery.isLoading && <Skeleton height="8rem" />}
      {diarization && (
        <Card>
          <dl style={{ display: "grid", gap: "var(--space-3)", margin: 0 }}>
            <div>
              <dt style={{ fontWeight: 600 }}>Anbieter</dt>
              <dd style={{ margin: 0 }}>{String(diarization.provider)}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>Modell</dt>
              <dd style={{ margin: 0 }}>{String(diarization.model)}</dd>
            </div>
            <div>
              <dt style={{ fontWeight: 600 }}>Status</dt>
              <dd style={{ margin: 0 }}>
                <Badge tone={diarization.installed ? "success" : "warning"}>
                  {diarization.installed ? "installiert" : "nicht installiert"}
                </Badge>
              </dd>
            </div>
            {Boolean(diarization.detail) && (
              <div>
                <dt style={{ fontWeight: 600 }}>Detail</dt>
                <dd style={{ margin: 0, color: "var(--text-secondary)" }}>{String(diarization.detail)}</dd>
              </div>
            )}
          </dl>
        </Card>
      )}
    </AdminLayout>
  );
}
