import type { DocumentSection } from "../api/documents";
import styles from "./DocumentContent.module.css";

/**
 * Renders a document revision's `structured_content` (section title +
 * statement list) as real headings/lists instead of the flattened
 * `rendered_text` string — the structure already exists server-side
 * (see backend app.documents.service.compose_document), this just stops
 * discarding it on the way to the screen.
 */
export function DocumentContent({
  sections,
  maxStatements,
}: {
  sections: DocumentSection[];
  /** When set, shows only the first N statements total (across sections)
   * — used for the Übersicht "Kurzfassung" preview so it stays a short
   * summary instead of duplicating the entire Dokumentation tab. */
  maxStatements?: number;
}) {
  if (sections.length === 0) {
    return <p className={styles.empty}>(Keine Fakten zum Zusammenstellen)</p>;
  }

  let remaining = maxStatements ?? Infinity;
  let truncated = false;
  const visibleSections = sections
    .map((section) => {
      if (remaining <= 0) {
        if (section.statements.length > 0) truncated = true;
        return null;
      }
      if (section.statements.length <= remaining) {
        remaining -= section.statements.length;
        return section;
      }
      truncated = true;
      const kept = section.statements.slice(0, remaining);
      remaining = 0;
      return { ...section, statements: kept };
    })
    .filter((section): section is DocumentSection => section !== null);

  return (
    <div className={styles.content}>
      {visibleSections.map((section) => (
        <section key={section.category} className={styles.section}>
          <h3 className={styles.sectionTitle}>{section.title}</h3>
          <ul className={styles.statementList}>
            {section.statements.map((statement, index) => (
              <li key={index} className={styles.statement}>
                {statement.text}
              </li>
            ))}
          </ul>
        </section>
      ))}
      {truncated && <p className={styles.truncated}>…</p>}
    </div>
  );
}
