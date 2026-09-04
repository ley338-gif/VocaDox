/**
 * Typed client for the Phase 9 Timeline/Comparison/Follow-ups-Tasks REST
 * API. Same plain-fetch pattern as api/intelligence.ts.
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

export interface TimelineEntry {
  conversation_id: string;
  title: string;
  conversation_type: string;
  status: string;
  occurred_at: string;
  fact_count: number;
}

export interface TimelineResponse {
  external_reference: string;
  conversations: TimelineEntry[];
}

export type ComparisonStatus = "new" | "changed" | "not_mentioned" | "contradicted";

export interface ComparisonItem {
  status: ComparisonStatus;
  subject: string;
  attribute: string;
  conversation_id: string;
  conversation_title: string;
  current_fact_id: string | null;
  current_value: string | null;
  prior_fact_id: string | null;
  prior_value: string | null;
  prior_conversation_id: string | null;
}

export interface ComparisonResponse {
  external_reference: string;
  conversation_count: number;
  items: ComparisonItem[];
}

export type FollowUpSource = "ai_extracted" | "user_created";
export type FollowUpStatus = "open" | "done" | "dismissed";

export interface FollowUpTask {
  id: string;
  organization_id: string;
  conversation_id: string;
  source: FollowUpSource;
  source_fact_id: string | null;
  description: string;
  assignee: string | null;
  due_date: string | null;
  status: FollowUpStatus;
  created_by_user_id: string | null;
  updated_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export function getRelatedConversations(conversationId: string): Promise<TimelineResponse> {
  return request<TimelineResponse>(`/conversations/${conversationId}/related`);
}

export function getExternalReferenceTimeline(
  externalReference: string,
  organizationId: string
): Promise<TimelineResponse> {
  return request<TimelineResponse>(
    `/external-references/${encodeURIComponent(externalReference)}/timeline?organization_id=${organizationId}`
  );
}

export function getExternalReferenceComparison(
  externalReference: string,
  organizationId: string
): Promise<ComparisonResponse> {
  return request<ComparisonResponse>(
    `/external-references/${encodeURIComponent(externalReference)}/comparison?organization_id=${organizationId}`
  );
}

export function listConversationTasks(conversationId: string): Promise<FollowUpTask[]> {
  return request<FollowUpTask[]>(`/conversations/${conversationId}/tasks`);
}

export function createConversationTask(
  conversationId: string,
  body: { description: string; assignee?: string; due_date?: string },
  csrfToken: string
): Promise<FollowUpTask> {
  return request<FollowUpTask>(`/conversations/${conversationId}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  });
}

export function updateTaskStatus(
  taskId: string,
  status: FollowUpStatus,
  csrfToken: string
): Promise<FollowUpTask> {
  return request<FollowUpTask>(`/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ status }),
  });
}
