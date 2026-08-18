import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  ApiError,
  csrf as apiCsrf,
  login as apiLogin,
  logout as apiLogout,
  me as apiMe,
} from "../api/client";
import type { AuthUser } from "./context";
import { AuthContext } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // On load, an existing session cookie (if any) is still valid
    // server-side even though we don't have its CSRF token in memory yet
    // — GET /auth/me and GET /auth/csrf are both safe GETs, so neither
    // needs the CSRF header. /auth/csrf re-reads the token already bound
    // to this session (see backend/app/identity/router.py) so mutating
    // actions (create conversation, upload, delete, ...) keep working
    // after a full page reload instead of silently no-oping — this
    // closed a real Phase 2 gap where every reload left CSRF-protected
    // actions unusable with no error shown until this fix.
    apiMe()
      .then(async (response) => {
        setUser({
          userId: response.user_id,
          username: response.username,
          displayName: response.display_name,
          email: response.email,
          permissions: response.permissions,
        });
        try {
          const csrfResponse = await apiCsrf();
          setCsrfToken(csrfResponse.csrf_token);
        } catch {
          // Non-fatal: user stays signed in and can still read data; a
          // mutating action will surface its own auth error if this
          // somehow still fails (e.g. a session that expired between
          // the two calls).
        }
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
