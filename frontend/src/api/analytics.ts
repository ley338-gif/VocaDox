/**
 * Typed client for the Phase 8 analytics/evaluation/model-lifecycle admin
 * surface (spec §50/§51). Same plain-fetch pattern as api/admin.ts.
 */

import { ApiError } from "./client";

const API_PREFIX = "/api/v1";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, { ...init, credentials: "include" });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown, csrfToken: string): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  };
}

// -- Technical / Quality / Correction analytics ---------------------------

export interface TechnicalAnalytics {
  window_days: number;
  total_jobs: number;
  volume_by_day: Record<string, number>;
  by_job_type: Record<
    string,
    {
      queued: number;
      running: number;
      succeeded: number;
      failed: number;
      cancelled: number;
      success_rate: number | null;
      avg_latency_seconds: number | null;
    }
  >;
}

export function getTechnicalAnalytics(days = 30): Promise<TechnicalAnalytics> {
  return request(`/admin/analytics/technical?days=${days}`);
}

export interface QualityMetrics {
  transcript_segments_total: number;
  transcript_segments_corrected: number;
  transcript_correction_rate: number | null;
  fact_review_status_counts: Record<string, number>;
  facts_total: number;
  fact_corrected_or_removed_rate: number | null;
  review_issue_status_counts: Record<string, number>;
  review_issue_resolution_counts: Record<string, number>;
}

export function getQualityMetrics(): Promise<QualityMetrics> {
  return request("/admin/analytics/quality");
}

export interface CorrectionMetrics {
  fact_corrections_by_category: Record<string, number>;
  most_corrected_subjects: { subject: string; count: number }[];
  transcript_segment_corrections_total: number;
}

export function getCorrectionMetrics(): Promise<CorrectionMetrics> {
  return request("/admin/analytics/corrections");
}

// -- Evaluation Lab ------------------------------------------------------

export interface EvalCategoryOutcome {
  category: string;
  json_valid: boolean;
  item_count: number;
  error: string | null;
}

export interface EvalResult {
  label: string;
  facts_expected: number;
  facts_matched: number;
  evidence_linkage_rate: number | null;
  contradictions_expected: number;
  contradictions_detected: number;
  json_valid_categories: number;
  json_total_categories: number;
  latency_seconds: number;
  per_category: EvalCategoryOutcome[];
  error: string | null;
}

export interface VocabularyEvalResult {
  word_error_rate: number;
}

// R0 (research roadmap, post-GA): per-fixture and per-overlap-level DER/JER
// -- see backend app.analytics.diarization_eval.DiarizationEvalSummary.as_public_dict.
export interface DiarizationOverlapLevelResult {
  overlap_level: "none" | "some" | "heavy";
  fixture_count: number;
  mean_der: number | null;
  mean_jer: number | null;
}

export interface DiarizationFixtureResult {
  fixture_id: string;
  overlap_level: "none" | "some" | "heavy";
  der: number | null;
  jer: number | null;
  reference_speaker_count: number;
  hypothesis_speaker_count: number | null;
  duration_seconds: number;
  error: string | null;
}

export interface DiarizationEvalResult {
  provider: string;
  model: string;
  model_revision: string | null;
  fixture_source: string;
  mean_der: number | null;
  mean_jer: number | null;
  latency_seconds: number;
  by_overlap_level: DiarizationOverlapLevelResult[];
  per_fixture: DiarizationFixtureResult[];
}

export interface EvaluationRun {
  id: string;
  run_type:
    | "model_comparison"
    | "prompt_comparison"
    | "vocabulary_comparison"
    | "diarization_accuracy";
  status: "running" | "completed" | "failed";
  fixture_key: string;
  subject_a: Record<string, unknown>;
  subject_b: Record<string, unknown>;
  result_a: EvalResult | VocabularyEvalResult | DiarizationEvalResult | null;
  result_b: EvalResult | VocabularyEvalResult | DiarizationEvalResult | null;
  error_message_safe: string | null;
  created_at: string;
  completed_at: string | null;
}

export function listEvaluationRuns(): Promise<{ items: EvaluationRun[]; total: number }> {
  return request("/admin/evaluation/runs?limit=50");
}

export function runModelComparison(
  modelProfileIdA: string,
  modelProfileIdB: string,
  csrfToken: string
): Promise<EvaluationRun> {
  return request(
    "/admin/evaluation/model-comparison",
    jsonInit(
      "POST",
      { model_profile_id_a: modelProfileIdA, model_profile_id_b: modelProfileIdB },
      csrfToken
    )
  );
}

export function runPromptComparison(
  promptVersionIdA: string,
  promptVersionIdB: string,
  modelProfileId: string,
  csrfToken: string
): Promise<EvaluationRun> {
  return request(
    "/admin/evaluation/prompt-comparison",
    jsonInit(
      "POST",
      {
        prompt_version_id_a: promptVersionIdA,
        prompt_version_id_b: promptVersionIdB,
        model_profile_id: modelProfileId,
      },
      csrfToken
    )
  );
}

export function runVocabularyComparison(
  conversationId: string,
  csrfToken: string
): Promise<EvaluationRun> {
  return request(
    "/admin/evaluation/vocabulary-comparison",
    jsonInit("POST", { conversation_id: conversationId }, csrfToken)
  );
}

// R0 (research roadmap, post-GA): runs the configured diarization
// provider's real diarize() against local RTTM fixtures at three overlap
// levels. Takes no body -- always scored against the fixed local fixture
// set (see backend app.analytics.diarization_eval).
export function runDiarizationAccuracyEval(csrfToken: string): Promise<EvaluationRun> {
  return request("/admin/evaluation/diarization-accuracy", jsonInit("POST", {}, csrfToken));
}

// -- Quality report (post-GA P1-4) -----------------------------------------

export interface ConversationWerResult {
  conversation_id: string;
  word_error_rate: number;
  reference_word_count: number;
}

export interface SkippedConversation {
  conversation_id: string;
  reason: string;
}

export interface QualityReport {
  generated_at: string;
  speech_provider: string;
  speech_model: string;
  speech_model_revision: string | null;
  conversation_results: ConversationWerResult[];
  skipped: SkippedConversation[];
  mean_word_error_rate: number | null;
  quality_metrics: QualityMetrics;
}

export function generateQualityReport(
  conversationIds: string[],
  csrfToken: string
): Promise<QualityReport> {
  return request(
    "/admin/evaluation/quality-report",
    jsonInit("POST", { conversation_ids: conversationIds }, csrfToken)
  );
}

export async function fetchQualityReportExport(
  conversationIds: string[],
  format: "pdf" | "docx",
  csrfToken: string
): Promise<Blob> {
  const response = await fetch(`${API_PREFIX}/admin/evaluation/quality-report?format=${format}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ conversation_ids: conversationIds }),
  });
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  return response.blob();
}

// -- Model Lifecycle ------------------------------------------------------

export interface LifecycleEvent {
  id: string;
  model_profile_id: string;
  from_status: string | null;
  to_status: string;
  is_rollback: boolean;
  checklist: Record<string, boolean> | null;
  note: string | null;
  actor_user_id: string | null;
  created_at: string;
}

export interface ModelLifecycle {
  model_profile_id: string;
  lifecycle_status: string;
  events: LifecycleEvent[];
}

export function getModelLifecycle(modelProfileId: string): Promise<ModelLifecycle> {
  return request(`/admin/model-profiles/${modelProfileId}/lifecycle`);
}

export const LIFECYCLE_CHECKLIST_KEYS = [
  "license_check",
  "compatibility_check",
  "benchmark",
  "security_review",
  "admin_approval",
] as const;

export function transitionModelLifecycle(
  modelProfileId: string,
  payload: {
    to_status: string;
    is_rollback?: boolean;
    checklist?: Record<string, boolean> | null;
    note?: string | null;
  },
  csrfToken: string
): Promise<LifecycleEvent> {
  return request(
    `/admin/model-profiles/${modelProfileId}/lifecycle-transition`,
    jsonInit("POST", payload, csrfToken)
  );
}
