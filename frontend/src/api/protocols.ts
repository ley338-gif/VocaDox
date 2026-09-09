/**
 * Typed client for the Protokoll REST surface (Post-GA) — same plain-
 * fetch pattern as api/documents.ts / api/profiles.ts.
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

export type ProtocolSectionType =
  | "introduction"
  | "topic"
  | "facts"
  | "discussion"
  | "decision"
  | "action_items"
  | "open_questions"
  | "note"
  | "conclusion";

export type ProtocolItemType =
  | "important_point"
  | "decision"
  | "action_item"
  | "open_question"
  | "fact"
  | "note";

export interface ProtocolItem {
  id: string;
  protocol_section_id: string;
  position: number;
  item_type: ProtocolItemType;
  text: string;
  responsible_label: string | null;
  due_date: string | null;
  completed: boolean | null;
  confidence: number | null;
  manually_edited: boolean;
}

export interface ProtocolSection {
  id: string;
  protocol_revision_id: string;
  position: number;
  section_type: ProtocolSectionType;
  title: string;
  summary: string;
  start_ms: number | null;
  end_ms: number | null;
  confidence: number | null;
  manually_edited: boolean;
  items: ProtocolItem[];
}

export interface ProtocolRevision {
  id: string;
  protocol_id: string;
  revision_number: number;
  status: "generating" | "ready" | "failed";
  created_at: string;
  sections: ProtocolSection[];
}

export interface ProtocolRevisionSummary {
  id: string;
  revision_number: number;
  status: string;
  created_at: string;
}

export interface Protocol {
  id: string;
  conversation_id: string;
  current_revision_id: string | null;
  created_at: string;
  updated_at: string;
  current_revision: ProtocolRevision | null;
}

export interface ProtocolSource {
  id: string;
  transcript_segment_id: string;
  segment_start_ms: number;
  segment_end_ms: number;
  segment_text: string;
  speaker_label: string | null;
}

/** Returns `null` (not a thrown 404) when no protocol exists yet for this
 * conversation — the empty-state case every caller has to handle anyway,
 * so callers don't each need their own try/catch around a 404. */
export async function getProtocol(conversationId: string): Promise<Protocol | null> {
  try {
    return await request<Protocol>(`/conversations/${conversationId}/protocol`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function generateProtocol(conversationId: string, csrfToken: string): Promise<void> {
  await request(`/conversations/${conversationId}/protocol/generate`, jsonInit("POST", {}, csrfToken));
}

export function listProtocolRevisions(conversationId: string): Promise<ProtocolRevisionSummary[]> {
  return request(`/conversations/${conversationId}/protocol/revisions`);
}

export function getSectionSources(
  conversationId: string,
  sectionId: string
): Promise<ProtocolSource[]> {
  return request(`/conversations/${conversationId}/protocol/sections/${sectionId}/sources`);
}

export function getItemSources(conversationId: string, itemId: string): Promise<ProtocolSource[]> {
  return request(`/conversations/${conversationId}/protocol/items/${itemId}/sources`);
}
