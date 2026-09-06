/**
 * Typed client for KnownSpeaker CRUD (post-GA: persistent cross-
 * conversation speaker identity). Follows the same pattern as
 * api/conversations.ts.
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

export interface KnownSpeaker {
  id: string;
  organization_id: string;
  display_name: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export function listKnownSpeakers(organizationId: string): Promise<KnownSpeaker[]> {
  return request(`/known-speakers?organization_id=${organizationId}`);
}

export function createKnownSpeaker(
  organizationId: string,
  payload: { display_name: string; notes?: string },
  csrfToken: string
): Promise<KnownSpeaker> {
  return request(
    `/known-speakers?organization_id=${organizationId}`,
    jsonInit("POST", payload, csrfToken)
  );
}

export function updateKnownSpeaker(
  knownSpeakerId: string,
  payload: { display_name?: string; notes?: string },
  csrfToken: string
): Promise<KnownSpeaker> {
  return request(`/known-speakers/${knownSpeakerId}`, jsonInit("PATCH", payload, csrfToken));
}

export function deleteKnownSpeaker(knownSpeakerId: string, csrfToken: string): Promise<void> {
  return request(`/known-speakers/${knownSpeakerId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}
