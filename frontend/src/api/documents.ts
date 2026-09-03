/**
 * Typed client for the Phase 5 document/revision/review-wizard REST API.
 * Same plain-fetch pattern as api/intelligence.ts.
 */

import { ApiError } from "./client";
import type { ReviewIssue } from "./intelligence";

const API_PREFIX = "/api/v1";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    credentials: "include",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string | { detail?: string; blocking_issue_ids?: string[] } };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail?.detail) detail = body.detail.detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export type DocumentRevisionStatus = "draft" | "review_required" | "ready_for_approval" | "approved";

export interface DocumentStatement {
  text: string;
  fact_ids: string[];
}

export interface DocumentSection {
  category: string;
  title: string;
  statements: DocumentStatement[];
}

export interface DocumentRevision {
  id: string;
  document_id: string;
  revision_number: number;
  structured_content: DocumentSection[];
  rendered_text: string;
  status: DocumentRevisionStatus;
  blocking_issue_ids: string[];
  created_by_user_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDocument {
  id: string;
  conversation_id: string;
  status: DocumentRevisionStatus;
  current_revision_id: string | null;
  created_at: string;
  updated_at: string;
  current_revision: DocumentRevision | null;
}

export function getDocument(conversationId: string): Promise<ConversationDocument> {
  return request<ConversationDocument>(`/conversations/${conversationId}/document`);
}

export function composeDocument(conversationId: string, csrfToken: string): Promise<ConversationDocument> {
  return request<ConversationDocument>(`/conversations/${conversationId}/document/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({}),
  });
}

export function listDocumentRevisions(conversationId: string): Promise<DocumentRevision[]> {
  return request<DocumentRevision[]>(`/conversations/${conversationId}/document/revisions`);
}

export function approveDocument(conversationId: string, csrfToken: string): Promise<ConversationDocument> {
  return request<ConversationDocument>(`/conversations/${conversationId}/document/approve`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function documentExportUrl(conversationId: string, format: "text" | "json"): string {
  return `${API_PREFIX}/conversations/${conversationId}/document/export?format=${format}`;
}

export async function fetchDocumentExport(conversationId: string, format: "text" | "json"): Promise<string> {
  const response = await fetch(documentExportUrl(conversationId, format), { credentials: "include" });
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  return response.text();
}

export type ReviewIssueAction = "confirm" | "correct" | "remove";

export function resolveReviewIssue(
  conversationId: string,
  issueId: string,
  body: { fact_id: string; action: ReviewIssueAction; corrected_value?: Record<string, unknown> },
  csrfToken: string
): Promise<ReviewIssue> {
  return request<ReviewIssue>(`/conversations/${conversationId}/review-issues/${issueId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  });
}
