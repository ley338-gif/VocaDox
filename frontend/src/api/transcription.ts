/**
 * Typed client for the Phase 3 transcript/processing/speaker REST API.
 * Same plain-fetch pattern as api/conversations.ts.
 */

import { ApiError } from "./client";

const API_PREFIX = "/api/v1";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    credentials: "include",
  });
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
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown, csrfToken?: string): RequestInit {
  return {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
    },
    body: JSON.stringify(body),
  };
}

export type TranscriptStatus = "pending" | "processing" | "ready" | "failed";
export type ProcessingJobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type AlignmentQuality = "confident" | "ambiguous" | "overlap" | "unassigned";
export type ReviewStatus = "unreviewed" | "confirmed" | "corrected" | "flagged";

export interface Transcript {
  id: string;
  conversation_id: string;
  source_media_id: string;
  language: string | null;
  status: TranscriptStatus;
  provider: string;
  model: string;
  model_revision: string | null;
  is_active: boolean;
  error_code: string | null;
  error_message_safe: string | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptWord {
  text: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
}

export interface TranscriptSegment {
  id: string;
  transcript_id: string;
  speaker_id: string | null;
  sequence: number;
  start_ms: number;
  end_ms: number;
  original_text: string;
  corrected_text: string | null;
  confidence: number | null;
  words: TranscriptWord[] | null;
  review_status: ReviewStatus;
  alignment_quality: AlignmentQuality;
  review_flag: boolean;
  review_flag_reason: string | null;
}

export interface ProcessingJob {
  id: string;
  job_type: "normalize" | "transcribe" | "diarize" | "align";
  status: ProcessingJobStatus;
  progress: number;
  attempt: number;
  max_attempts: number;
  failure_class: string | null;
  error_code: string | null;
  error_message_safe: string | null;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProcessingStatusResponse {
  conversation_status: string;
  jobs: ProcessingJob[];
}

export interface DetectedSpeaker {
  id: string;
  conversation_id: string;
  internal_label: string;
  display_label: string | null;
  participant_id: string | null;
  assigned_by_user_id: string | null;
  assigned_at: string | null;
}

export function processTranscript(
  conversationId: string,
  body: {
    diarize?: boolean;
    language_hint?: string;
    reprocess?: boolean;
    min_speakers?: number;
    max_speakers?: number;
  },
  csrfToken: string
): Promise<Transcript> {
  return request<Transcript>(
    `/conversations/${conversationId}/process/transcript`,
    jsonInit("POST", body, csrfToken)
  );
}

export function getProcessingStatus(conversationId: string): Promise<ProcessingStatusResponse> {
  return request<ProcessingStatusResponse>(`/conversations/${conversationId}/processing`);
}

export function retryProcessing(conversationId: string, csrfToken: string): Promise<ProcessingJob> {
  return request<ProcessingJob>(`/conversations/${conversationId}/processing/retry`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function getTranscript(conversationId: string): Promise<Transcript> {
  return request<Transcript>(`/conversations/${conversationId}/transcript`);
}

export function listTranscriptSegments(
  conversationId: string,
  q?: string
): Promise<TranscriptSegment[]> {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  return request<TranscriptSegment[]>(`/conversations/${conversationId}/transcript/segments${qs}`);
}

export function correctSegment(
  conversationId: string,
  segmentId: string,
  body: { corrected_text?: string; review_status?: ReviewStatus },
  csrfToken: string
): Promise<TranscriptSegment> {
  return request<TranscriptSegment>(
    `/conversations/${conversationId}/transcript/segments/${segmentId}`,
    jsonInit("PATCH", body, csrfToken)
  );
}

export function listSpeakers(conversationId: string): Promise<DetectedSpeaker[]> {
  return request<DetectedSpeaker[]>(`/conversations/${conversationId}/speakers`);
}

export function assignSpeaker(
  conversationId: string,
  speakerId: string,
  body: { participant_id?: string | null; display_label?: string | null },
  csrfToken: string
): Promise<DetectedSpeaker> {
  return request<DetectedSpeaker>(
    `/conversations/${conversationId}/speakers/${speakerId}`,
    jsonInit("PATCH", body, csrfToken)
  );
}

export function transcriptExportUrl(conversationId: string, format: "text" | "json" | "markdown"): string {
  return `${API_PREFIX}/conversations/${conversationId}/transcript/export?format=${format}`;
}
