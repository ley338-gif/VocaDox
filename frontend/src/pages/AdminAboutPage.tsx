import { useQuery } from "@tanstack/react-query";

import { getAbout } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";

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
        About &amp; Licenses
      </h1>
      {about && (
        <>
          <p style={{ marginTop: "var(--space-4)" }}>
            VocaDox <strong>{about.application_version}</strong>
          </p>

          <section style={{ marginTop: "var(--space-6)" }}>
            <h2 style={{ fontSize: "var(--font-h2-size)" }}>License compliance</h2>
            {Object.keys(about.license_summary).length === 0 ? (
              <p style={{ color: "var(--text-muted)" }}>
                Compliance inventory files are not shipped in this deployment.
              </p>
            ) : (
              <table style={{ width: "100%", marginTop: "var(--space-3)" }}>
                <thead>
                  <tr style={{ textAlign: "left" }}>
                    <th>Category</th>
                    <th>Approved</th>
                    <th>Review required</th>
                    <th>Blocked</th>
                    <th>Unknown</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(about.license_summary).map(([category, counts]) => (
                    <tr key={category}>
                      <td>{category.replace(/_/g, " ")}</td>
                      <td>{counts.approved}</td>
                      <td>{counts.review_required}</td>
                      <td>{counts.blocked}</td>
                      <td>{counts.unknown}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section style={{ marginTop: "var(--space-6)" }}>
            <h2 style={{ fontSize: "var(--font-h2-size)" }}>Third-party notices</h2>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                background: "var(--color-gray-100)",
                padding: "var(--space-4)",
                borderRadius: "var(--radius-md)",
                marginTop: "var(--space-3)",
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
