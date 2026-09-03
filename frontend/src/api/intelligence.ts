/**
 * Typed client for the Phase 4 fact extraction / evidence / review-issue
 * REST API. Same plain-fetch pattern as api/transcription.ts.
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

export type FactCategory = "general_fact" | "decision" | "task";
export type FactStatus = "verified" | "unverified" | "superseded";
export type Certainty = "stated" | "unclear" | "incomplete" | "not_mentioned";
export type ReviewIssueType = "uncertainty" | "potential_contradiction";
export type ReviewIssueSeverity = "low" | "medium" | "high" | "critical";

export interface ExtractedFact {
  id: string;
  conversation_id: string;
  processing_run_id: string | null;
  category: FactCategory;
  fact_type: string;
  structured_value: Record<string, unknown>;
  certainty: Certainty;
  confidence: number | null;
  status: FactStatus;
  created_at: string;
  updated_at: string;
}

export interface FactEvidence {
  id: string;
  fact_id: string;
  transcript_segment_id: string;
  evidence_type: string;
  created_at: string;
  segment_sequence: number | null;
  segment_start_ms: number | null;
  segment_end_ms: number | null;
  segment_text: string | null;
}

export interface ReviewIssue {
  id: string;
  conversation_id: string;
  issue_type: ReviewIssueType;
  severity: ReviewIssueSeverity;
  uncertainty_category: string | null;
  related_fact_ids: string[];
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export function triggerExtraction(conversationId: string, csrfToken: string): Promise<ExtractedFact[]> {
  return request<ExtractedFact[]>(`/conversations/${conversationId}/process/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({}),
  });
}

export function listFacts(conversationId: string): Promise<ExtractedFact[]> {
  return request<ExtractedFact[]>(`/conversations/${conversationId}/facts`);
}

export function getFactEvidence(conversationId: string, factId: string): Promise<FactEvidence[]> {
  return request<FactEvidence[]>(`/conversations/${conversationId}/facts/${factId}/evidence`);
}

export function listReviewIssues(conversationId: string): Promise<ReviewIssue[]> {
  return request<ReviewIssue[]>(`/conversations/${conversationId}/review-issues`);
}
