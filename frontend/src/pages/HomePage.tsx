import { Navigate } from "react-router";

import { useAuth } from "../auth/useAuth";

/**
 * Root landing route. All 12 roadmap phases are implemented — this just
 * routes a visitor to the right place rather than showing content itself:
 * signed-in users land on their workspace, everyone else on the login
 * page. (Previously showed static "Phase 0 scaffold" placeholder text
 * left over from before any domain features existed — found stale during
 * a post-GA manual walkthrough and fixed.)
 */
export function HomePage() {
  const { user, loading } = useAuth();

  if (loading) return null;
  return <Navigate to={user ? "/app" : "/login"} replace />;
}
