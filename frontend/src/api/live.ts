/**
 * Typed client for the live transcript/draft during recording (post-GA
 * P2-1). Same plain-fetch pattern as api/search.ts.
 */

import { ApiError } from "./client";

const API_PREFIX = "/api/v1";

export interface LiveSession {
  transcript_text: string;
  draft_text: string | null;
  chunk_count: number;
  updated_at: string;
}

export async function ingestLiveChunk(
  conversationId: string,
  blob: Blob,
  csrfToken: string
): Promise<LiveSession> {
  const formData = new FormData();
  formData.append("file", blob, "chunk.webm");
  const response = await fetch(`${API_PREFIX}/conversations/${conversationId}/live/chunks`, {
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
  return (await response.json()) as LiveSession;
}

export async function clearLiveSession(conversationId: string, csrfToken: string): Promise<void> {
  await fetch(`${API_PREFIX}/conversations/${conversationId}/live`, {
    method: "DELETE",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken },
  });
}
