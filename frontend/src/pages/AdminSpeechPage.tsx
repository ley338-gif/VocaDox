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
 *
 * R2 (research roadmap, post-GA): the "Anbieter" field above is already
 * provider-agnostic (it renders whatever `SpeechProviderStatus.provider`
 * the configured `VOCADOX_SPEECH_PROVIDER` reports — "faster-whisper" or
 * "nvidia-nemotron") — no code change was needed for the status card to
 * show a second provider. The note below is the one addition, same
 * pattern AdminDiarizationPage's R1 change used: since switching
 * providers is an ops-level env var, not a UI control, this makes the two
 * valid real options discoverable here rather than only in
 * docs/admin/model-installation.md.
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
      {speech && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <Card>
            <p style={{ fontWeight: 600, margin: "0 0 var(--space-2) 0" }}>
              Unterstützte Anbieter
            </p>
            <p style={{ margin: "0 0 var(--space-3) 0", color: "var(--text-secondary)" }}>
              Der aktive Anbieter wird über <code>VOCADOX_SPEECH_PROVIDER</code> auf
              Server-Ebene konfiguriert (kein UI-Umschalter) — siehe
              docs/admin/model-installation.md.
            </p>
            <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
              <Badge tone={speech.provider === "faster-whisper" ? "success" : "neutral"}>
                faster-whisper
              </Badge>
              <Badge tone={speech.provider === "nvidia-nemotron" ? "success" : "neutral"}>
                nvidia-nemotron
              </Badge>
            </div>
          </Card>
        </div>
      )}
    </AdminLayout>
  );
}
