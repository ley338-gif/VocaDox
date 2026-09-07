/**
 * Typed client for custom transcription vocabulary CRUD (post-GA P0-3).
 * Same plain-fetch pattern as api/admin.ts.
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

export interface VocabularyEntry {
  id: string;
  organization_id: string;
  template_id: string | null;
  name: string;
  terms: string[];
  initial_prompt: string | null;
  created_at: string;
  updated_at: string;
}

export function listVocabulary(organizationId: string): Promise<VocabularyEntry[]> {
  return request(`/vocabulary?organization_id=${organizationId}`);
}

export function createVocabulary(
  organizationId: string,
  body: { template_id?: string | null; name: string; terms: string[]; initial_prompt?: string | null },
  csrfToken: string
): Promise<VocabularyEntry> {
  return request(`/vocabulary?organization_id=${organizationId}`, jsonInit("POST", body, csrfToken));
}

export function updateVocabulary(
  organizationId: string,
  entryId: string,
  body: { name?: string; terms?: string[]; initial_prompt?: string | null },
  csrfToken: string
): Promise<VocabularyEntry> {
  return request(
    `/vocabulary/${entryId}?organization_id=${organizationId}`,
    jsonInit("PATCH", body, csrfToken)
  );
}

export function deleteVocabulary(
  organizationId: string,
  entryId: string,
  csrfToken: string
): Promise<void> {
  return request(`/vocabulary/${entryId}?organization_id=${organizationId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}
