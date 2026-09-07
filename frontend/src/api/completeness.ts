/**
 * Typed client for the template completeness score (post-GA P1-3):
 * category coverage against the conversation's resolved Template, plus
 * decision/task owner completeness and speaking-share/longest-monologue
 * from diarization. Read-only, computed on demand — same plain-fetch
 * pattern as api/search.ts.
 */

import { ApiError } from "./client";

const API_PREFIX = "/api/v1";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, { credentials: "include" });
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

export interface CategoryCoverage {
  category: string;
  title: string;
  covered: boolean;
  fact_count: number;
}

export interface SpeakingShare {
  speaker_id: string;
  label: string;
  speaking_ms: number;
  share: number;
}

export interface MonologueSpan {
  speaker_id: string;
  label: string;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
}

export interface Completeness {
  conversation_id: string;
  template_key: string | null;
  template_name: string | null;
  template_version_id: string | null;
  categories: CategoryCoverage[];
  category_coverage_ratio: number;
  decisions_total: number;
  decisions_missing_decided_by: number;
  tasks_total: number;
  tasks_missing_assignee: number;
  overall_score: number;
  speaking_shares: SpeakingShare[];
  longest_monologue: MonologueSpan | null;
}

export function getCompleteness(conversationId: string): Promise<Completeness> {
  return request(`/conversations/${conversationId}/completeness`);
}
