/**
 * Typed client for Ask VocaDox (post-GA P1-1). Same plain-fetch pattern
 * as api/search.ts.
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

export interface AskCitation {
  fact_id: string;
  conversation_id: string;
  conversation_title: string;
  category: string;
  text: string;
}

export interface AskStatement {
  text: string;
  citations: AskCitation[];
}

export interface AskAnswer {
  id: string;
  question: string;
  statements: AskStatement[];
  had_candidate_evidence: boolean;
  created_at: string;
}

export function ask(
  question: string,
  conversationId: string | null,
  csrfToken: string
): Promise<AskAnswer> {
  return request("/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({ question, conversation_id: conversationId || undefined }),
  });
}
