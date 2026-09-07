/**
 * Typed client for the shareable, participant-facing Recap (post-GA).
 * Follows the same pattern as api/documents.ts.
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

function jsonInit(method: string, csrfToken?: string): RequestInit {
  return {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
    },
    body: JSON.stringify({}),
  };
}

export type RecapStatus = "draft" | "approved";

export interface RecapRevision {
  id: string;
  recap_id: string;
  revision_number: number;
  content: string;
  language: string | null;
  provider: string;
  model_identifier: string;
  status: RecapStatus;
  created_by_user_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Recap {
  id: string;
  conversation_id: string;
  status: RecapStatus;
  current_revision_id: string | null;
  created_at: string;
  updated_at: string;
  current_revision: RecapRevision | null;
}

export function getRecap(conversationId: string): Promise<Recap> {
  return request(`/conversations/${conversationId}/recap`);
}

export function generateRecap(conversationId: string, csrfToken: string): Promise<Recap> {
  return request(`/conversations/${conversationId}/recap/generate`, jsonInit("POST", csrfToken));
}

export function approveRecap(conversationId: string, csrfToken: string): Promise<Recap> {
  return request(`/conversations/${conversationId}/recap/approve`, jsonInit("POST", csrfToken));
}

export function recapExportUrl(conversationId: string, format: "text" | "docx" | "pdf" = "text"): string {
  return `${API_PREFIX}/conversations/${conversationId}/recap/export?format=${format}`;
}

// -- Share links (post-GA P3-2) ------------------------------------------

export interface ShareLink {
  id: string;
  conversation_id: string;
  token: string;
  expires_at: string;
  revoked_at: string | null;
  created_by_user_id: string | null;
  access_count: number;
  last_accessed_at: string | null;
  created_at: string;
}

export function listShareLinks(conversationId: string): Promise<ShareLink[]> {
  return request(`/conversations/${conversationId}/recap/share-links`);
}

export function createShareLink(
  conversationId: string,
  ttlHours: number,
  csrfToken: string
): Promise<ShareLink> {
  return request(`/conversations/${conversationId}/recap/share-links`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ ttl_hours: ttlHours }),
  });
}

export function revokeShareLink(
  conversationId: string,
  linkId: string,
  csrfToken: string
): Promise<void> {
  return request(`/conversations/${conversationId}/recap/share-links/${linkId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export interface PublicRecap {
  content: string;
  revision_number: number;
  approved_at: string | null;
  expires_at: string;
}

export function getPublicRecap(token: string): Promise<PublicRecap> {
  return request(`/public/recap/${token}`);
}
