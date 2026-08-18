import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, login as apiLogin, logout as apiLogout, me as apiMe } from "../api/client";
import type { AuthUser } from "./context";
import { AuthContext } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // On load, an existing session cookie (if any) is still valid
    // server-side even though we don't have its CSRF token in memory —
    // GET /auth/me doesn't require CSRF (only state-changing requests do).
    // The user can still view their session; logout will simply be
    // unavailable until they next log in fresh, which is an acceptable
    // Phase 1 tradeoff (documented in PHASE_1_VALIDATION_REPORT.md).
    apiMe()
      .then((response) => {
        setUser({
          userId: response.user_id,
          username: response.username,
          displayName: response.display_name,
          email: response.email,
          permissions: response.permissions,
        });
      })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const response = await apiLogin(username, password);
    setCsrfToken(response.csrf_token);
    setUser({
      userId: response.user_id,
      username: response.username,
      displayName: response.display_name,
      email: null,
      permissions: [],
    });
    const me = await apiMe();
    setUser({
      userId: me.user_id,
      username: me.username,
      displayName: me.display_name,
      email: me.email,
      permissions: me.permissions,
    });
  }, []);

  const logout = useCallback(async () => {
    if (csrfToken) {
      try {
        await apiLogout(csrfToken);
      } catch (error) {
        // A 401 here just means the session already expired server-side;
        // any other error still shouldn't block clearing local state.
        if (!(error instanceof ApiError)) throw error;
      }
    }
    setUser(null);
    setCsrfToken(null);
  }, [csrfToken]);

  const hasPermission = useCallback(
    (code: string) => user?.permissions.includes(code) ?? false,
    [user]
  );

  const value = useMemo(
    () => ({ user, csrfToken, loading, login, logout, hasPermission }),
    [user, csrfToken, loading, login, logout, hasPermission]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
