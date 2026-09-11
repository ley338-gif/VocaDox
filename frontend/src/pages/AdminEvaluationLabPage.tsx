import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type DiarizationEvalResult,
  type EvalResult,
  type QualityReport,
  type VocabularyEvalResult,
  fetchQualityReportExport,
  generateQualityReport,
  listEvaluationRuns,
  runDiarizationAccuracyEval,
  runModelComparison,
  runPromptComparison,
  runVocabularyComparison,
} from "../api/analytics";
import { listModelProfiles } from "../api/profiles";
import { listPromptVersions, listPrompts } from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { Select, TextInput } from "../design-system/FormControls";
import { ErrorState } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { TabPanel, Tabs } from "../design-system/Tabs";

function isVocabularyResult(
  result: EvalResult | VocabularyEvalResult
): result is VocabularyEvalResult {
  return "word_error_rate" in result;
}

function isDiarizationResult(
  result: EvalResult | VocabularyEvalResult | DiarizationEvalResult
): result is DiarizationEvalResult {
  return "by_overlap_level" in result;
}

/**
 * Phase 8 Evaluation Lab (spec §50): runs the same synthetic fixture
 * through two real subjects (two `ModelProfile`s, or two `PromptVersion`s
 * of the same model) and shows real, measured results side by side — the
 * illustrative spec table (Facts/Evidence/Contradictions/JSON Valid/
 * Latency), populated from a real backend run, never a mockup. See
 * `backend/app/analytics/eval_engine.py` and `fixtures.py` for exactly
 * what is measured and how, and PHASE_8_VALIDATION_REPORT.md for the real
 * two-different-real-model (Ollama) comparison this mechanism actually
 * produced.
 */
export function AdminEvaluationLabPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const canRun = hasPermission("evaluation:run");

  const [mode, setMode] = useState<
    "model" | "prompt" | "vocabulary" | "diarization" | "quality-report"
  >("model");
  const [modelA, setModelA] = useState("");
  const [modelB, setModelB] = useState("");
  const [promptA, setPromptA] = useState("");
  const [promptB, setPromptB] = useState("");
  const [promptModel, setPromptModel] = useState("");
  const [vocabConversationId, setVocabConversationId] = useState("");
  const [qualityReportIdsText, setQualityReportIdsText] = useState("");
  const [qualityReport, setQualityReport] = useState<QualityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const qualityReportConversationIds = qualityReportIdsText
    .split(/[\s,]+/)
    .map((id) => id.trim())
    .filter(Boolean);

  const modelProfilesQuery = useQuery({
    queryKey: ["admin", "model-profiles"],
    queryFn: listModelProfiles,
  });
  const promptVersionsAQuery = useQuery({
    queryKey: ["admin", "prompt-versions", "for-eval"],
    queryFn: async () => {
      const prompts = await listPrompts();
      const all = await Promise.all(prompts.map((p) => listPromptVersions(p.id)));
      return all.flat();
    },
    enabled: mode === "prompt",
  });
  const runsQuery = useQuery({
    queryKey: ["admin", "evaluation", "runs"],
    queryFn: listEvaluationRuns,
  });

  async function handleRunModelComparison() {
    if (!csrfToken || !modelA || !modelB) return;
    setError(null);
    setRunning(true);
    try {
      await runModelComparison(modelA, modelB, csrfToken);
      await queryClient.invalidateQueries({ queryKey: ["admin", "evaluation", "runs"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Vergleich fehlgeschlagen.");
    } finally {
      setRunning(false);
    }
  }

  async function handleRunPromptComparison() {
    if (!csrfToken || !promptA || !promptB || !promptModel) return;
    setError(null);
    setRunning(true);
    try {
      await runPromptComparison(promptA, promptB, promptModel, csrfToken);
      await queryClient.invalidateQueries({ queryKey: ["admin", "evaluation", "runs"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Vergleich fehlgeschlagen.");
    } finally {
      setRunning(false);
    }
  }

  async function handleRunVocabularyComparison() {
    if (!csrfToken || !vocabConversationId.trim()) return;
    setError(null);
    setRunning(true);
    try {
      await runVocabularyComparison(vocabConversationId.trim(), csrfToken);
      await queryClient.invalidateQueries({ queryKey: ["admin", "evaluation", "runs"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Vergleich fehlgeschlagen.");
    } finally {
      setRunning(false);
    }
  }

  async function handleRunDiarizationAccuracyEval() {
    if (!csrfToken) return;
    setError(null);
    setRunning(true);
    try {
      await runDiarizationAccuracyEval(csrfToken);
      await queryClient.invalidateQueries({ queryKey: ["admin", "evaluation", "runs"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lauf fehlgeschlagen.");
    } finally {
      setRunning(false);
    }
  }

  async function handleGenerateQualityReport() {
    if (!csrfToken || qualityReportConversationIds.length === 0) return;
    setError(null);
    setRunning(true);
    try {
      const report = await generateQualityReport(qualityReportConversationIds, csrfToken);
      setQualityReport(report);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bericht konnte nicht erstellt werden.");
    } finally {
      setRunning(false);
    }
  }

  async function handleExportQualityReport(format: "pdf" | "docx") {
    if (!csrfToken || qualityReportConversationIds.length === 0) return;
    setError(null);
    try {
      const blob = await fetchQualityReportExport(qualityReportConversationIds, format, csrfToken);
      const url = URL.createObjectURL(blob);
      const a = window.document.createElement("a");
      a.href = url;
      a.download = `quality-report.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export fehlgeschlagen.");
    }
  }

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Evaluation Lab
      </h1>
      <p style={{ color: "var(--text-muted)", marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        Führt eine synthetische Test-Vorlage durch zwei echte Subjekte und vergleicht echte gemessene
        Ergebnisse — Fakten gegen einen bekannten Referenzsatz, Evidenzverknüpfung, Widerspruchserkennung,
        JSON-Schema-Gültigkeit und Latenz.
      </p>

      {canRun && (
        <section style={{ marginBottom: "var(--space-8)" }}>
          <Tabs
            idPrefix="evallab-mode"
            activeId={mode}
            onChange={(id) =>
              setMode(id as "model" | "prompt" | "vocabulary" | "diarization" | "quality-report")
            }
            items={[
              { id: "model", label: "Modellvergleich" },
              { id: "prompt", label: "Promptvergleich" },
              { id: "vocabulary", label: "Fachwortschatz" },
              { id: "diarization", label: "Sprechererkennung (DER/JER)" },
              { id: "quality-report", label: "Qualitätsbericht" },
            ]}
          />

          <TabPanel id="model" activeId={mode} idPrefix="evallab-mode">
            <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", flexWrap: "wrap" }}>
              <Select value={modelA} onChange={(e) => setModelA(e.target.value)}>
                <option value="">Modellprofil A…</option>
                {modelProfilesQuery.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.provider}/{p.model_identifier})
                  </option>
                ))}
              </Select>
              <span>vs.</span>
              <Select value={modelB} onChange={(e) => setModelB(e.target.value)}>
                <option value="">Modellprofil B…</option>
                {modelProfilesQuery.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.provider}/{p.model_identifier})
                  </option>
                ))}
              </Select>
              <Button
                onClick={() => void handleRunModelComparison()}
                disabled={running || !modelA || !modelB}
              >
                {running ? "Läuft…" : "Vergleich starten"}
              </Button>
            </div>
          </TabPanel>

          <TabPanel id="prompt" activeId={mode} idPrefix="evallab-mode">
            <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", flexWrap: "wrap" }}>
              <Select value={promptA} onChange={(e) => setPromptA(e.target.value)}>
                <option value="">Promptversion A…</option>
                {promptVersionsAQuery.data?.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number} ({v.status})
                  </option>
                ))}
              </Select>
              <span>vs.</span>
              <Select value={promptB} onChange={(e) => setPromptB(e.target.value)}>
                <option value="">Promptversion B…</option>
                {promptVersionsAQuery.data?.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number} ({v.status})
                  </option>
                ))}
              </Select>
              <Select value={promptModel} onChange={(e) => setPromptModel(e.target.value)}>
                <option value="">mit Modellprofil…</option>
                {modelProfilesQuery.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
              <Button
                onClick={() => void handleRunPromptComparison()}
                disabled={running || !promptA || !promptB || !promptModel}
              >
                {running ? "Läuft…" : "Vergleich starten"}
              </Button>
            </div>
          </TabPanel>

          <TabPanel id="vocabulary" activeId={mode} idPrefix="evallab-mode">
            <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-3)" }}>
              Führt die echte Spracherkennung auf dem Original-Audio eines bereits transkribierten
              Gesprächs zweimal aus — einmal ohne, einmal mit dem für dessen Organisation/Vorlage
              hinterlegten Fachwortschatz — und vergleicht die Wortfehlerrate gegen das geprüfte
              Transkript. Setzt voraus, dass für das Gespräch bereits ein Fachwortschatz-Eintrag
              existiert.
            </p>
            <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", flexWrap: "wrap" }}>
              <TextInput
                placeholder="Gesprächs-ID…"
                value={vocabConversationId}
                onChange={(e) => setVocabConversationId(e.target.value)}
                style={{ minWidth: "22rem" }}
              />
              <Button
                onClick={() => void handleRunVocabularyComparison()}
                disabled={running || !vocabConversationId.trim()}
              >
                {running ? "Läuft…" : "Vergleich starten"}
              </Button>
            </div>
          </TabPanel>

          <TabPanel id="diarization" activeId={mode} idPrefix="evallab-mode">
            <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-3)" }}>
              R0 (Forschungs-Roadmap): führt die echte Sprechererkennung des konfigurierten
              Anbieters gegen lokale, mit RTTM-Referenz versehene Testdaten bei drei
              Überlappungsgraden (keine/etwas/stark) aus und berechnet Diarization Error Rate
              (DER) sowie Jaccard Error Rate (JER) je Testdatei und je Überlappungsgrad. Nutzt
              standardmäßig die mitgelieferten synthetischen Testdaten (Vorbedingungscheck,
              nicht echte Stimmen) — für echte Stimmen siehe{" "}
              <code>VOCADOX_DIARIZATION_FIXTURES_DIR</code>.
            </p>
            <Button onClick={() => void handleRunDiarizationAccuracyEval()} disabled={running}>
              {running ? "Läuft…" : "DER/JER-Lauf starten"}
            </Button>
          </TabPanel>

          <TabPanel id="quality-report" activeId={mode} idPrefix="evallab-mode">
            <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-3)" }}>
              Erstellt einen exportierbaren Qualitätsnachweis (Wortfehlerrate + Extraktionsgüte)
              über eine von Ihnen benannte Stichprobe bereits geprüfter Gespräche — geeignet für
              Beschaffung, Datenschutzbeauftragte und EU-AI-Act-Dokumentation. Bis zu 20
              Gesprächs-IDs, durch Komma oder Zeilenumbruch getrennt.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <textarea
                value={qualityReportIdsText}
                onChange={(e) => setQualityReportIdsText(e.target.value)}
                placeholder="Gesprächs-IDs…"
                rows={3}
                style={{
                  width: "100%",
                  maxWidth: "40rem",
                  font: "inherit",
                  padding: "var(--space-2)",
                  border: "1px solid var(--border-default)",
                  borderRadius: "var(--radius-md)",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                }}
              />
              <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
                <Button
                  onClick={() => void handleGenerateQualityReport()}
                  disabled={running || qualityReportConversationIds.length === 0}
                >
                  {running ? "Läuft…" : "Bericht erstellen"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => void handleExportQualityReport("pdf")}
                  disabled={qualityReportConversationIds.length === 0}
                >
                  Als PDF exportieren
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => void handleExportQualityReport("docx")}
                  disabled={qualityReportConversationIds.length === 0}
                >
                  Als DOCX exportieren
                </Button>
              </div>
            </div>

            {qualityReport && (
              <div style={{ marginTop: "var(--space-4)" }}>
                <p>
                  <strong>Spracherkennung:</strong> {qualityReport.speech_provider} /{" "}
                  {qualityReport.speech_model}
                  {qualityReport.speech_model_revision ? ` (${qualityReport.speech_model_revision})` : ""}
                </p>
                <p>
                  <strong>Mittlere Wortfehlerrate:</strong>{" "}
                  {qualityReport.mean_word_error_rate === null
                    ? "keine auswertbaren Gespräche"
                    : formatPct(qualityReport.mean_word_error_rate)}{" "}
                  ({qualityReport.conversation_results.length} ausgewertet,{" "}
                  {qualityReport.skipped.length} übersprungen)
                </p>
                {qualityReport.conversation_results.length > 0 && (
                  <table style={{ width: "100%", marginTop: "var(--space-3)", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                        <th>Gespräch</th>
                        <th>Wortfehlerrate</th>
                        <th>Referenzwörter</th>
                      </tr>
                    </thead>
                    <tbody>
                      {qualityReport.conversation_results.map((r) => (
                        <tr key={r.conversation_id}>
                          <td>{r.conversation_id}</td>
                          <td>{formatPct(r.word_error_rate)}</td>
                          <td>{r.reference_word_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {qualityReport.skipped.length > 0 && (
                  <div style={{ marginTop: "var(--space-3)" }}>
                    <strong>Übersprungen:</strong>
                    <ul>
                      {qualityReport.skipped.map((s) => (
                        <li key={s.conversation_id}>
                          {s.conversation_id}: {s.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p style={{ marginTop: "var(--space-3)" }}>
                  <strong>Extraktionsgüte dieser Stichprobe:</strong>{" "}
                  {qualityReport.quality_metrics.transcript_segments_corrected} von{" "}
                  {qualityReport.quality_metrics.transcript_segments_total} Transkript-Segmenten
                  korrigiert
                  {qualityReport.quality_metrics.fact_corrected_or_removed_rate !== null && (
                    <>
                      {" · "}
                      {formatPct(qualityReport.quality_metrics.fact_corrected_or_removed_rate)}{" "}
                      der Fakten korrigiert/entfernt
                    </>
                  )}
                </p>
              </div>
            )}
          </TabPanel>
          {error && (
            <div style={{ marginTop: "var(--space-3)" }}>
              <ErrorState message={error} />
            </div>
          )}
        </section>
      )}

      <section>
        <h2 style={{ fontSize: "var(--font-h2-size)", marginBottom: "var(--space-4)" }}>Vergangene Läufe</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {runsQuery.data?.items.map((run) => (
            <Card key={run.id}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{run.run_type.replace("_", " ")}</strong>
                <StatusBadge status={run.status} label={run.status === "completed" ? "abgeschlossen" : undefined} />
              </div>
              <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
                {new Date(run.created_at).toLocaleString()} · Vorlage: {run.fixture_key}
              </p>
              {run.error_message_safe && (
                <p style={{ color: "var(--color-danger)" }}>{run.error_message_safe}</p>
              )}
              {run.result_a && isDiarizationResult(run.result_a) && (
                <table style={{ width: "100%", marginTop: "var(--space-3)", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                      <th>Überlappungsgrad</th>
                      <th>Testdateien</th>
                      <th>DER (Ø)</th>
                      <th>JER (Ø)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.result_a.by_overlap_level.map((level) => (
                      <tr key={level.overlap_level}>
                        <td>{level.overlap_level}</td>
                        <td>{level.fixture_count}</td>
                        <td>{formatPct(level.mean_der)}</td>
                        <td>{formatPct(level.mean_jer)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {run.result_a &&
                run.result_b &&
                !isDiarizationResult(run.result_a) &&
                !isDiarizationResult(run.result_b) &&
                (isVocabularyResult(run.result_a) && isVocabularyResult(run.result_b) ? (
                  <table style={{ width: "100%", marginTop: "var(--space-3)", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                        <th>Metrik</th>
                        <th>{String(run.subject_a.label ?? "ohne Glossar")}</th>
                        <th>{String(run.subject_b.label ?? "mit Glossar")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Wortfehlerrate</td>
                        <td>{formatPct(run.result_a.word_error_rate)}</td>
                        <td>{formatPct(run.result_b.word_error_rate)}</td>
                      </tr>
                    </tbody>
                  </table>
                ) : !isVocabularyResult(run.result_a) && !isVocabularyResult(run.result_b) ? (
                  <table style={{ width: "100%", marginTop: "var(--space-3)", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                        <th>Metrik</th>
                        <th>{run.result_a.label}</th>
                        <th>{run.result_b.label}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <MetricRow label="Fakten gefunden" a={run.result_a} b={run.result_b} field="facts_matched" total="facts_expected" />
                      <tr>
                        <td>Evidenzverknüpfung</td>
                        <td>{formatPct(run.result_a.evidence_linkage_rate)}</td>
                        <td>{formatPct(run.result_b.evidence_linkage_rate)}</td>
                      </tr>
                      <MetricRow
                        label="Widersprüche"
                        a={run.result_a}
                        b={run.result_b}
                        field="contradictions_detected"
                        total="contradictions_expected"
                      />
                      <MetricRow
                        label="JSON gültig"
                        a={run.result_a}
                        b={run.result_b}
                        field="json_valid_categories"
                        total="json_total_categories"
                      />
                      <tr>
                        <td>Latenz</td>
                        <td>{run.result_a.latency_seconds.toFixed(1)}s</td>
                        <td>{run.result_b.latency_seconds.toFixed(1)}s</td>
                      </tr>
                    </tbody>
                  </table>
                ) : null)}
            </Card>
          ))}
        </div>
      </section>
    </AdminLayout>
  );
}

function formatPct(rate: number | null): string {
  return rate === null ? "k. A." : `${Math.round(rate * 100)}%`;
}

function MetricRow({
  label,
  a,
  b,
  field,
  total,
}: {
  label: string;
  a: EvalResult;
  b: EvalResult;
  field: keyof EvalResult;
  total: keyof EvalResult;
}) {
  return (
    <tr>
      <td>{label}</td>
      <td>
        {String(a[field])}/{String(a[total])}
      </td>
      <td>
        {String(b[field])}/{String(b[total])}
      </td>
    </tr>
  );
}
