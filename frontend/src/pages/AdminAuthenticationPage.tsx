import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";

/**
 * Phase 7 Admin Portal Authentication page: read-only visibility into
 * configured auth providers. Phase 1 built the `AuthProvider` interface
 * (app.identity.auth_providers) with only LOCAL actually implemented —
 * OIDC/LDAP_AD/REVERSE_PROXY remain interface-only future work per that
 * phase's explicit scope. This page surfaces that honestly rather than
 * implying providers exist that don't — no new auth provider type is
 * implemented this phase.
 */
export function AdminAuthenticationPage() {
  const providers: { key: string; label: string; implemented: boolean }[] = [
    { key: "local", label: "Local (username/password)", implemented: true },
    { key: "oidc", label: "OIDC", implemented: false },
    { key: "ldap_ad", label: "LDAP / Active Directory", implemented: false },
    { key: "reverse_proxy", label: "Reverse proxy (header-based)", implemented: false },
  ];

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Authentication
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        VocaDox supports a pluggable authentication provider interface
        (<code>app.identity.auth_providers.AuthProvider</code>). Only Local is
        implemented today — every user account currently authenticates with a
        locally-stored password hash (Argon2). The other provider types exist
        as a stable interface/schema (the <code>users.auth_provider</code>{" "}
        column already accepts these values) so a future phase can implement
        them without a data-model change.
      </p>
      <table style={{ width: "100%", marginTop: "var(--space-6)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>Provider</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.key} style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td style={{ padding: "var(--space-2) 0" }}>{p.label}</td>
              <td>
                <Badge tone={p.implemented ? "success" : "neutral"}>
                  {p.implemented ? "active" : "not implemented"}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </AdminLayout>
  );
}
