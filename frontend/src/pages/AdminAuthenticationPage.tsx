import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { DataTable, type DataTableColumn } from "../design-system/Table";

interface ProviderRow {
  key: string;
  label: string;
  implemented: boolean;
}

const PROVIDERS: ProviderRow[] = [
  { key: "local", label: "Lokal (Benutzername/Passwort)", implemented: true },
  { key: "oidc", label: "OIDC", implemented: false },
  { key: "ldap_ad", label: "LDAP / Active Directory", implemented: false },
  { key: "reverse_proxy", label: "Reverse Proxy (header-basiert)", implemented: false },
];

const COLUMNS: DataTableColumn<ProviderRow>[] = [
  { key: "label", header: "Anbieter", render: (p) => p.label },
  {
    key: "status",
    header: "Status",
    render: (p) => (
      <Badge tone={p.implemented ? "success" : "neutral"}>
        {p.implemented ? "aktiv" : "nicht implementiert"}
      </Badge>
    ),
  },
];

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
  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Authentifizierung
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        VocaDox unterstützt eine austauschbare Authentifizierungsanbieter-Schnittstelle
        (<code>app.identity.auth_providers.AuthProvider</code>). Heute ist nur Lokal
        implementiert — jedes Benutzerkonto authentifiziert sich derzeit mit einem lokal
        gespeicherten Passwort-Hash (Argon2). Die anderen Anbietertypen existieren als stabile
        Schnittstelle/Schema (die Spalte <code>users.auth_provider</code> akzeptiert diese Werte
        bereits), sodass eine spätere Phase sie ohne Datenmodelländerung implementieren kann.
      </p>
      <DataTable columns={COLUMNS} rows={PROVIDERS} keyExtractor={(p) => p.key} />
    </AdminLayout>
  );
}
