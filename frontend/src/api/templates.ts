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
  current_published_version_id: string | null;
}

export interface TemplateVersion {
  id: string;
  template_id: string;
  version_number: number;
  status: "draft" | "test" | "published" | "retired";
  extraction_categories: CategoryDefinition[];
  presentation: { category: string; title: string }[];
}

export function listTemplates(): Promise<Template[]> {
  return request("/templates");
}

export function listTemplateVersions(templateId: string): Promise<TemplateVersion[]> {
  return request(`/templates/${templateId}/versions`);
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
