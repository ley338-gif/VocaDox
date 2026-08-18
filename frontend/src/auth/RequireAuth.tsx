import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useAuth } from "./useAuth";

/** Session-aware route guard. Redirects to /login (preserving the
 * originally-requested path) when there is no authenticated user. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return <>{children}</>;
}

/** Permission-gated route guard (spec: `/admin` must be gated on
 * `system:admin`, checked as a genuine permission — not a role-name
 * comparison). Renders nothing informative beyond a 403-style message so
 * unauthorized users can't infer the route exists. */
export function RequirePermission({
  code,
  children,
}: {
  code: string;
  children: ReactNode;
}) {
  const { user, loading, hasPermission } = useAuth();
  const location = useLocation();

  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (!hasPermission(code)) {
    return (
      <div style={{ padding: "var(--space-6)" }}>
        <h1 style={{ fontSize: "var(--font-h2-size)" }}>Access denied</h1>
        <p style={{ color: "var(--text-secondary)" }}>
          You don&apos;t have permission to view this page.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
