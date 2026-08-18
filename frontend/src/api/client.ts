/**
 * Minimal fetch wrapper for the auth endpoints. No new HTTP client
 * dependency was added — the app already depends on @tanstack/react-query
 * for caching around plain `fetch`, matching the existing package.json.
 *
 * `credentials: "include"` is required on every call so the httponly
 * session cookie set by POST /auth/login is sent back on subsequent
 * requests (and so the browser can receive/clear it on login/logout).
 */

const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // response had no JSON body; fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface LoginResponse {
  user_id: string;
  username: string;
  display_name: string;
  csrf_token: string;
}

export interface CurrentUserResponse {
  user_id: string;
  username: string;
  display_name: string;
  email: string | null;
  permissions: string[];
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout(csrfToken: string): Promise<void> {
  return request<void>("/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function me(): Promise<CurrentUserResponse> {
  return request<CurrentUserResponse>("/auth/me", { method: "GET" });
}

export interface CsrfTokenResponse {
  csrf_token: string;
}

/** Recovers the current session's CSRF token after a full page reload —
 * see AuthContext.tsx for why this is needed in addition to /auth/me. */
export function csrf(): Promise<CsrfTokenResponse> {
  return request<CsrfTokenResponse>("/auth/csrf", { method: "GET" });
}
