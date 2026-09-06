import { createContext } from "react";

import type { GroupSummary } from "../api/client";

export interface AuthUser {
  userId: string;
  username: string;
  displayName: string;
  email: string | null;
  permissions: string[];
  /** The user's own team memberships (app.conversations.authz's team-
   * scoped visibility reuses the existing Group model as "team") — used
   * e.g. by NewConversationPage's team picker. */
  groups: GroupSummary[];
}

export interface AuthState {
  user: AuthUser | null;
  csrfToken: string | null;
  /** True while the initial GET /auth/me probe (on app load) is in flight. */
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (code: string) => boolean;
}

export const AuthContext = createContext<AuthState | undefined>(undefined);
