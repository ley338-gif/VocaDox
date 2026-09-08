/**
 * Typed client for the Phase 6 Template Engine / Prompt admin surface
 * (spec §42/§43). Same plain-fetch pattern as api/conversations.ts.
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

export interface CategoryField {
  name: string;
  max_length?: number;
  description?: string;
}

export interface CategoryDefinition {
  key: string;
  builtin?: boolean;
  fact_type?: string;
  item_field?: string;
  instruction?: string;
  fields?: CategoryField[];
}

export interface Template {
  id: string;
  key: string;
  name: string;
  description: string | null;
  organization_id: string | null;
  current_published_version_id: string | null;
}

export interface TemplateVersion {
  id: string;
  template_id: string;
  version_number: number;
  status: "draft" | "test" | "published" | "retired";
  extraction_categories: CategoryDefinition[];
  presentation: { category: string; title: string }[];
  document_layout: "sections" | "letter" | "freeform";
  document_body: string | null;
  letterhead_logo_asset_key: string | null;
}

export interface TemplateVersionCreatePayload {
  extraction_categories: CategoryDefinition[];
  presentation: { category: string; title: string }[];
  document_layout?: "sections" | "letter" | "freeform";
  document_body?: string | null;
  letterhead_logo_asset_key?: string | null;
}

export interface TemplateCreatePayload extends TemplateVersionCreatePayload {
  key: string;
  name: string;
  description?: string | null;
  organization_id?: string | null;
}

export function listTemplates(): Promise<Template[]> {
  return request("/templates");
}

export function createTemplate(payload: TemplateCreatePayload, csrfToken: string): Promise<Template> {
  return request("/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export function updateTemplateOrganization(
  templateId: string,
  organizationId: string | null,
  csrfToken: string
): Promise<Template> {
  return request(`/templates/${templateId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ organization_id: organizationId }),
  });
}

export function listTemplateVersions(templateId: string): Promise<TemplateVersion[]> {
  return request(`/templates/${templateId}/versions`);
}

export function createTemplateVersion(
  templateId: string,
  payload: TemplateVersionCreatePayload,
  csrfToken: string
): Promise<TemplateVersion> {
  return request(`/templates/${templateId}/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export function publishTemplateVersion(
  templateId: string,
  versionId: string,
  csrfToken: string
): Promise<TemplateVersion> {
  return request(`/templates/${templateId}/versions/${versionId}/publish`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

// -- Letterhead logo (post-GA) -----------------------------------------------

export async function uploadLetterheadLogo(
  file: File,
  csrfToken: string
): Promise<{ asset_key: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_PREFIX}/templates/letterhead-logo`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken },
    body: formData,
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
  return (await response.json()) as { asset_key: string };
}

export function letterheadLogoUrl(assetKey: string): string {
  // `assetKey` contains "/"-separated namespace segments (see
  // app.providers.storage's docstring: "callers must treat it as opaque
  // and pass it back unchanged") that the backend's `{asset_key:path}`
  // route expects literally, not percent-encoded -- each segment is
  // already safe (hex/alnum/dots only), so no encoding is needed here.
  return `${API_PREFIX}/templates/letterhead-logo/${assetKey}`;
}

// -- Prompts (spec §43: DRAFT -> TEST -> PUBLISHED -> RETIRED) --------------

export interface Prompt {
  id: string;
  key: string;
  name: string;
  purpose: string;
  current_published_version_id: string | null;
}

export interface PromptVersion {
  id: string;
  prompt_id: string;
  version_number: number;
  status: "draft" | "test" | "published" | "retired";
  system_prompt: string;
  category_instructions: Record<string, string> | null;
}

export function listPrompts(): Promise<Prompt[]> {
  return request("/prompts");
}

export function listPromptVersions(promptId: string): Promise<PromptVersion[]> {
  return request(`/prompts/${promptId}/versions`);
}

export function publishPromptVersion(
  promptId: string,
  versionId: string,
  csrfToken: string
): Promise<PromptVersion> {
  return request(`/prompts/${promptId}/versions/${versionId}/publish`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}
