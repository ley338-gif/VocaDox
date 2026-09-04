import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type EvalResult,
  listEvaluationRuns,
  runModelComparison,
  runPromptComparison,
} from "../api/analytics";
import { listModelProfiles } from "../api/profiles";
import { listPromptVersions, listPrompts } from "../api/templates";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Select } from "../design-system/FormControls";

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

  const [mode, setMode] = useState<"model" | "prompt">("model");
  const [modelA, setModelA] = useState("");
  const [modelB, setModelB] = useState("");
  const [promptA, setPromptA] = useState("");
  const [promptB, setPromptB] = useState("");
  const [promptModel, setPromptModel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

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
      setError(err instanceof Error ? err.message : "comparison failed");
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
      setError(err instanceof Error ? err.message : "comparison failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Evaluation Lab
      </h1>
      <p style={{ color: "var(--text-muted)", marginTop: "var(--space-2)" }}>
        Runs a synthetic fixture through two real subjects and compares real measured results —
        facts matched against a known gold set, evidence linkage, contradiction detection, JSON
        schema validity, and latency.
      </p>

      {canRun && (
        <section style={{ marginTop: "var(--space-6)" }}>
          <div style={{ display: "flex", gap: "var(--space-4)" }}>
            <button
              onClick={() => setMode("model")}
              style={{
                fontWeight: mode === "model" ? 600 : 400,
                border: "none",
                background: "transparent",
                cursor: "pointer",
              }}
            >
              Model comparison
            </button>
            <button
              onClick={() => setMode("prompt")}
              style={{
                fontWeight: mode === "prompt" ? 600 : 400,
                border: "none",
                background: "transparent",
                cursor: "pointer",
              }}
            >
              Prompt comparison
            </button>
          </div>

          {mode === "model" && (
            <div
              style={{
                display: "flex",
                gap: "var(--space-3)",
                alignItems: "center",
                marginTop: "var(--space-3)",
              }}
            >
              <Select value={modelA} onChange={(e) => setModelA(e.target.value)}>
                <option value="">Model profile A…</option>
                {modelProfilesQuery.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.provider}/{p.model_identifier})
                  </option>
                ))}
              </Select>
              <span>vs.</span>
              <Select value={modelB} onChange={(e) => setModelB(e.target.value)}>
                <option value="">Model profile B…</option>
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
                {running ? "Running…" : "Run comparison"}
              </Button>
            </div>
          )}

          {mode === "prompt" && (
            <div
              style={{
                display: "flex",
                gap: "var(--space-3)",
                alignItems: "center",
                marginTop: "var(--space-3)",
                flexWrap: "wrap",
              }}
            >
              <Select value={promptA} onChange={(e) => setPromptA(e.target.value)}>
                <option value="">Prompt version A…</option>
                {promptVersionsAQuery.data?.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number} ({v.status})
                  </option>
                ))}
              </Select>
              <span>vs.</span>
              <Select value={promptB} onChange={(e) => setPromptB(e.target.value)}>
                <option value="">Prompt version B…</option>
                {promptVersionsAQuery.data?.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number} ({v.status})
                  </option>
                ))}
              </Select>
              <Select value={promptModel} onChange={(e) => setPromptModel(e.target.value)}>
                <option value="">using model profile…</option>
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
                {running ? "Running…" : "Run comparison"}
              </Button>
            </div>
          )}
          {error && <p style={{ color: "var(--color-danger)" }}>{error}</p>}
        </section>
      )}

      <section style={{ marginTop: "var(--space-8)" }}>
        <h2 style={{ fontSize: "var(--font-h2-size)" }}>Past runs</h2>
        {runsQuery.data?.items.map((run) => (
          <div
            key={run.id}
            style={{
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
              marginTop: "var(--space-4)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{run.run_type.replace("_", " ")}</strong>
              <Badge tone={run.status === "completed" ? "success" : "danger"}>{run.status}</Badge>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
              {new Date(run.created_at).toLocaleString()} · fixture: {run.fixture_key}
            </p>
            {run.error_message_safe && (
              <p style={{ color: "var(--color-danger)" }}>{run.error_message_safe}</p>
            )}
            {run.result_a && run.result_b && (
              <table style={{ width: "100%", marginTop: "var(--space-3)", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                    <th>Metric</th>
                    <th>{run.result_a.label}</th>
                    <th>{run.result_b.label}</th>
                  </tr>
                </thead>
                <tbody>
                  <MetricRow label="Facts matched" a={run.result_a} b={run.result_b} field="facts_matched" total="facts_expected" />
                  <tr>
                    <td>Evidence linkage</td>
                    <td>{formatPct(run.result_a.evidence_linkage_rate)}</td>
                    <td>{formatPct(run.result_b.evidence_linkage_rate)}</td>
                  </tr>
                  <MetricRow
                    label="Contradictions"
                    a={run.result_a}
                    b={run.result_b}
                    field="contradictions_detected"
                    total="contradictions_expected"
                  />
                  <MetricRow
                    label="JSON valid"
                    a={run.result_a}
                    b={run.result_b}
                    field="json_valid_categories"
                    total="json_total_categories"
                  />
                  <tr>
                    <td>Latency</td>
                    <td>{run.result_a.latency_seconds.toFixed(1)}s</td>
                    <td>{run.result_b.latency_seconds.toFixed(1)}s</td>
                  </tr>
                </tbody>
              </table>
            )}
          </div>
        ))}
      </section>
    </AdminLayout>
  );
}

function formatPct(rate: number | null): string {
  return rate === null ? "n/a" : `${Math.round(rate * 100)}%`;
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
