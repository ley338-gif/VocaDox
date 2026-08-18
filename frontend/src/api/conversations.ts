/**
 * Typed client for the Phase 2 conversation-capture REST API. Follows the
 * same plain-fetch + credentials:"include" pattern as api/client.ts (no new
 * HTTP dependency). Mutating calls take `csrfToken` explicitly, mirroring
 * how AuthContext already threads it through for /auth/logout.
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

export type ConversationType =
  | "general"
  | "medical"
  | "therapy"
  | "meeting"
  | "interview"
  | "other";
export type ConversationStatus =
  | "created"
  | "recording"
  | "uploaded"
  | "normalizing"
  | "ready"
  | "failed"
  | "deleted";
export type PrivacyMode = "standard" | "restricted";
export type ParticipantType = "unknown" | "staff" | "patient" | "client" | "guest" | "other";

export interface Conversation {
  id: string;
  organization_id: string;
  created_by_user_id: string | null;
  title: string;
  description: string | null;
  conversation_type: ConversationType;
  status: ConversationStatus;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  external_reference: string | null;
  external_reference_type: string | null;
  privacy_mode: PrivacyMode;
  retention_policy_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MediaAsset {
  id: string;
  conversation_id: string;
  kind: "source_audio" | "normalized_audio" | "attachment";
  source_type: "browser_recording" | "file_upload" | "api_upload" | "derived";
  original_filename: string | null;
  content_type: string;
  size_bytes: number;
  sha256: string;
  duration_ms: number | null;
  sample_rate: number | null;
  channels: number | null;
  codec: string | null;
  container: string | null;
  derived_from_media_id: string | null;
  created_by_user_id: string | null;
  created_at: string;
}

export interface Participant {
  id: string;
  conversation_id: string;
  display_name: string;
  participant_type: ParticipantType;
  external_reference: string | null;
  notes: string | null;
  created_at: string;
}

export interface Marker {
  id: string;
  conversation_id: string;
  created_by_user_id: string | null;
  timestamp_ms: number;
  label: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface Note {
  id: string;
  conversation_id: string;
  created_by_user_id: string | null;
  content: string;
  timestamp_ms: number | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: Conversation[];
  total: number;
  limit: number;
  offset: number;
}

export function listConversations(params: {
  status?: string;
  type?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<ConversationListResponse> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.type) q.set("type", params.type);
  if (params.search) q.set("search", params.search);
  q.set("limit", String(params.limit ?? 50));
  q.set("offset", String(params.offset ?? 0));
  return request(`/conversations?${q.toString()}`);
}

export function getConversation(id: string): Promise<Conversation> {
  return request(`/conversations/${id}`);
}

export function createConversation(
  payload: {
    title: string;
    organization_id: string;
    description?: string;
    conversation_type?: ConversationType;
    external_reference?: string;
    external_reference_type?: string;
    privacy_mode?: PrivacyMode;
  },
  csrfToken: string
): Promise<Conversation> {
  return request("/conversations", jsonInit("POST", payload, csrfToken));
}

export function updateConversation(
  id: string,
  payload: Partial<{
    title: string;
    description: string;
    conversation_type: ConversationType;
    external_reference: string;
    external_reference_type: string;
    privacy_mode: PrivacyMode;
  }>,
  csrfToken: string
): Promise<Conversation> {
  return request(`/conversations/${id}`, jsonInit("PATCH", payload, csrfToken));
}

export function deleteConversation(id: string, csrfToken: string): Promise<void> {
  return request(`/conversations/${id}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function listMedia(conversationId: string): Promise<MediaAsset[]> {
  return request(`/conversations/${conversationId}/media`);
}

export function uploadMedia(
  conversationId: string,
  file: File,
  csrfToken: string,
  onProgress?: (fraction: number) => void
): Promise<MediaAsset> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file, file.name);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_PREFIX}/conversations/${conversationId}/media`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as MediaAsset);
      } else {
        let detail = xhr.statusText;
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string };
          if (body.detail) detail = body.detail;
        } catch {
          // ignore
        }
        reject(new ApiError(xhr.status, detail));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "network error during upload"));
    xhr.send(form);
  });
}

export function finalizeRecording(
  conversationId: string,
  blob: Blob,
  idempotencyKey: string,
  csrfToken: string,
  originalFilename?: string
): Promise<MediaAsset> {
  const q = new URLSearchParams({ idempotency_key: idempotencyKey });
  if (originalFilename) q.set("original_filename", originalFilename);
  return request(`/conversations/${conversationId}/recordings?${q.toString()}`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken, "Content-Type": "application/octet-stream" },
    body: blob,
  });
}

export function mediaContentUrl(conversationId: string, mediaId: string): string {
  return `${API_PREFIX}/conversations/${conversationId}/media/${mediaId}/content`;
}

export function deleteMedia(
  conversationId: string,
  mediaId: string,
  csrfToken: string
): Promise<void> {
  return request(`/conversations/${conversationId}/media/${mediaId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function listParticipants(conversationId: string): Promise<Participant[]> {
  return request(`/conversations/${conversationId}/participants`);
}

export function addParticipant(
  conversationId: string,
  payload: { display_name: string; participant_type?: ParticipantType; notes?: string },
  csrfToken: string
): Promise<Participant> {
  return request(`/conversations/${conversationId}/participants`, jsonInit("POST", payload, csrfToken));
}

export function deleteParticipant(
  conversationId: string,
  participantId: string,
  csrfToken: string
): Promise<void> {
  return request(`/conversations/${conversationId}/participants/${participantId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function listMarkers(conversationId: string): Promise<Marker[]> {
  return request(`/conversations/${conversationId}/markers`);
}

export function addMarker(
  conversationId: string,
  payload: { timestamp_ms: number; label?: string; note?: string },
  csrfToken: string
): Promise<Marker> {
  return request(`/conversations/${conversationId}/markers`, jsonInit("POST", payload, csrfToken));
}

export function deleteMarker(
  conversationId: string,
  markerId: string,
  csrfToken: string
): Promise<void> {
  return request(`/conversations/${conversationId}/markers/${markerId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function listNotes(conversationId: string): Promise<Note[]> {
  return request(`/conversations/${conversationId}/notes`);
}

export function addNote(
  conversationId: string,
  payload: { content: string; timestamp_ms?: number },
  csrfToken: string
): Promise<Note> {
  return request(`/conversations/${conversationId}/notes`, jsonInit("POST", payload, csrfToken));
}

export function deleteNote(conversationId: string, noteId: string, csrfToken: string): Promise<void> {
  return request(`/conversations/${conversationId}/notes/${noteId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}
