import { useQuery } from "@tanstack/react-query";

import { getAbout } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Skeleton } from "../design-system/States";
import { DataTable, type DataTableColumn } from "../design-system/Table";

interface LicenseRow {
  category: string;
  counts: Record<string, number>;
}

const COLUMNS: DataTableColumn<LicenseRow>[] = [
  { key: "category", header: "Kategorie", render: (r) => r.category.replace(/_/g, " ") },
  { key: "approved", header: "Genehmigt", render: (r) => r.counts.approved ?? 0 },
  { key: "review", header: "Prüfung nötig", render: (r) => r.counts.review_required ?? 0 },
  { key: "blocked", header: "Blockiert", render: (r) => r.counts.blocked ?? 0 },
  { key: "unknown", header: "Unbekannt", render: (r) => r.counts.unknown ?? 0 },
];

/**
 * Phase 7 Admin Portal About & Licenses page: application version plus
 * the license-compliance inventory summary and a THIRD_PARTY_NOTICES.md
 * excerpt (app.administration.service.license_summary/
 * third_party_notices_excerpt). Note: the production container image does
 * not ship compliance/THIRD_PARTY_NOTICES.md (outside the Docker build
 * context) — a real deployment shows the application version with an
 * honest "not found" for the license section rather than fabricated data.
 */
export function AdminAboutPage() {
  const aboutQuery = useQuery({ queryKey: ["admin", "about"], queryFn: getAbout });
  const about = aboutQuery.data;

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Über &amp; Lizenzen
      </h1>
      {aboutQuery.isLoading && <Skeleton height="6rem" />}
      {about && (
        <>
          <p style={{ marginTop: "var(--space-4)" }}>
            VocaDox <strong>{about.application_version}</strong>
          </p>

          <section style={{ marginTop: "var(--space-6)" }}>
            <h2 style={{ fontSize: "var(--font-h2-size)", marginBottom: "var(--space-3)" }}>Lizenz-Compliance</h2>
            {Object.keys(about.license_summary).length === 0 ? (
              <p style={{ color: "var(--text-muted)" }}>
                Compliance-Inventardateien sind in diesem Deployment nicht enthalten.
              </p>
            ) : (
              <DataTable
                columns={COLUMNS}
                rows={Object.entries(about.license_summary).map(([category, counts]) => ({ category, counts }))}
                keyExtractor={(r) => r.category}
              />
            )}
          </section>

          <section style={{ marginTop: "var(--space-6)" }}>
            <h2 style={{ fontSize: "var(--font-h2-size)", marginBottom: "var(--space-3)" }}>Hinweise zu Drittanbietern</h2>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                background: "var(--surface-sunken)",
                padding: "var(--space-4)",
                borderRadius: "var(--radius-md)",
                maxHeight: "400px",
                overflow: "auto",
              }}
            >
              {about.third_party_notices_excerpt}
            </pre>
          </section>
        </>
      )}
    </AdminLayout>
  );
}
