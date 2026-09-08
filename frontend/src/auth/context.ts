import { createContext } from "react";

import type { Gender, GroupSummary } from "../api/client";

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
  firstName: string | null;
  lastName: string | null;
  gender: Gender | null;
  avatarAssetKey: string | null;
}

export interface AuthState {
  user: AuthUser | null;
  csrfToken: string | null;
  /** True while the initial GET /auth/me probe (on app load) is in flight. */
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (code: string) => boolean;
  /** Re-fetches GET /auth/me and updates `user` in place -- used after a
   * self-service profile edit (MyProfileModal) so the topbar/avatar
   * reflect the change immediately, without a full page reload. */
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | undefined>(undefined);
