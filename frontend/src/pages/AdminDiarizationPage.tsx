import { useQuery } from "@tanstack/react-query";

import { getModelsOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Card } from "../design-system/Card";
import { Skeleton } from "../design-system/States";

/** Phase 7 Admin Portal Diarization page — same pattern as AdminSpeechPage.
 * R1 (research roadmap, post-GA): the "Anbieter" field below is already
 * provider-agnostic (it renders whatever `DiarizationProviderStatus.provider`
 * the configured `VOCADOX_DIARIZATION_PROVIDER` reports — "pyannote.audio" or
 * "nvidia-sortformer") — no code change was needed for the status card to
 * show a second provider. The note below is the one addition: since
 * switching providers is an ops-level env var, not a UI control (see
 * ADR-0048), this makes the two valid real options discoverable here rather
 * than only in docs/admin/model-installation.md. */
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
      {diarization && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <Card>
            <p style={{ fontWeight: 600, margin: "0 0 var(--space-2) 0" }}>
              Unterstützte Anbieter
            </p>
            <p style={{ margin: "0 0 var(--space-3) 0", color: "var(--text-secondary)" }}>
              Der aktive Anbieter wird über <code>VOCADOX_DIARIZATION_PROVIDER</code> auf
              Server-Ebene konfiguriert (kein UI-Umschalter) — siehe
              docs/admin/model-installation.md.
            </p>
            <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
              <Badge tone={diarization.provider === "pyannote.audio" ? "success" : "neutral"}>
                pyannote.audio
              </Badge>
              <Badge tone={diarization.provider === "nvidia-sortformer" ? "success" : "neutral"}>
                nvidia-sortformer
              </Badge>
            </div>
          </Card>
        </div>
      )}
    </AdminLayout>
  );
}
