import { Link } from "react-router";

/**
 * Placeholder for the future `/admin` portal (Users/Groups/Organizations/
 * ... — Phase 7). Only reachable if `RequirePermission code="system:admin"`
 * passes, proving the routing/permission separation between `/app` and
 * `/admin` exists from Phase 1 onward. Templates &amp; Processing
 * Profiles (Phase 6's actual admin-facing deliverable) are real, linked
 * below — see AdminTemplatesPage.
 */
export function AdminHomePage() {
  return (
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Admin portal
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        You have <code>system:admin</code> permission. The full admin
        console (Users, Groups, Organizations, ...) ships in Phase 7.
      </p>
      <p style={{ marginTop: "var(--space-4)" }}>
        <Link to="/admin/templates">Templates &amp; Processing Profiles</Link>
      </p>
    </div>
  );
}
