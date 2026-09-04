/**
 * Typed client for the Phase 6 Model Profile / Processing Profile admin
 * surface (spec §18/§19). Same plain-fetch pattern as api/conversations.ts.
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

export interface ModelProfile {
  id: string;
  name: string;
  purpose: string;
  provider: string;
  model_identifier: string;
  context_length: number;
  temperature: number;
  max_tokens: number;
  structured_output: boolean;
  thinking_mode: string | null;
  version: string;
  enabled: boolean;
}

export interface ProcessingProfile {
  id: string;
  key: string;
  name: string;
  description: string | null;
  is_system_default: boolean;
  current_published_version_id: string | null;
  enabled: boolean;
}

export interface ProcessingProfileVersion {
  id: string;
  processing_profile_id: string;
  version_number: number;
  status: string;
  template_id: string;
  template_version_id: string;
  language: string;
  published_at: string | null;
}

export function listModelProfiles(): Promise<ModelProfile[]> {
  return request("/model-profiles");
}

export function listProcessingProfiles(): Promise<ProcessingProfile[]> {
  return request("/processing-profiles");
}

export function listProcessingProfileVersions(
  processingProfileId: string
): Promise<ProcessingProfileVersion[]> {
  return request(`/processing-profiles/${processingProfileId}/versions`);
}

export function publishProcessingProfileVersion(
  processingProfileId: string,
  versionId: string,
  csrfToken: string
): Promise<ProcessingProfileVersion> {
  return request(
    `/processing-profiles/${processingProfileId}/versions/${versionId}/publish`,
    { method: "POST", headers: { "X-CSRF-Token": csrfToken } }
  );
}

export interface EffectiveConfigField {
  field: string;
  value: unknown;
  source: "system_default" | "processing_profile" | "conversation_override" | null;
}

export interface EffectiveConfig {
  processing_profile_id: string | null;
  processing_profile_version_id: string | null;
  fields: EffectiveConfigField[];
}

export function getEffectiveConfig(conversationId: string): Promise<EffectiveConfig> {
  return request(`/conversations/${conversationId}/effective-config`);
}

export function setConfigOverride(
  conversationId: string,
  payload: Record<string, string | null>,
  csrfToken: string
): Promise<unknown> {
  return request(`/conversations/${conversationId}/config-override`, jsonInit("PATCH", payload, csrfToken));
}
