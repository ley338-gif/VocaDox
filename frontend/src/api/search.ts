/**
 * Typed client for the post-GA P0-1 cross-conversation search endpoint.
 * Same plain-fetch pattern as api/conversations.ts.
 */

import { ApiError } from "./client";

const API_PREFIX = "/api/v1";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, { credentials: "include" });
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

export type SearchSourceType = "transcript_segment" | "extracted_fact" | "document";

export interface SearchResult {
  conversation_id: string;
  conversation_title: string;
  source_type: SearchSourceType;
  source_id: string;
  snippet: string;
  rank: number;
  updated_at: string;
}

export interface SearchResponse {
  items: SearchResult[];
  total: number;
  limit: number;
  offset: number;
}

export function search(params: { q: string; limit?: number; offset?: number }): Promise<SearchResponse> {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  qs.set("limit", String(params.limit ?? 20));
  qs.set("offset", String(params.offset ?? 0));
  return request(`/search?${qs.toString()}`);
}
