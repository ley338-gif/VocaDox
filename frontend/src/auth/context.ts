import { createContext } from "react";

export interface AuthUser {
  userId: string;
  username: string;
  displayName: string;
  email: string | null;
  permissions: string[];
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
