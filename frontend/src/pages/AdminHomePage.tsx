/**
 * Placeholder for the future `/admin` portal (Users/Groups/Organizations/
 * Templates/... — Phase 7). Only reachable if `RequirePermission
 * code="system:admin"` passes, proving the routing/permission separation
 * between `/app` and `/admin` exists from Phase 1 onward.
 */
export function AdminHomePage() {
  return (
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Admin portal
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        You have <code>system:admin</code> permission. The full admin
        console (Users, Groups, Organizations, Templates, ...) ships in
        Phase 7.
      </p>
    </div>
  );
}
