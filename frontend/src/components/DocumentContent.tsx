import type { DocumentSection } from "../api/documents";
import styles from "./DocumentContent.module.css";

/**
 * Renders a document revision's `structured_content` (section title +
 * statement list) as real headings/lists instead of the flattened
 * `rendered_text` string — the structure already exists server-side
 * (see backend app.documents.service.compose_document), this just stops
 * discarding it on the way to the screen.
 */
export function DocumentContent({ sections }: { sections: DocumentSection[] }) {
  if (sections.length === 0) {
    return <p className={styles.empty}>(Keine Fakten zum Zusammenstellen)</p>;
  }

  return (
    <div className={styles.content}>
      {sections.map((section) => (
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
    </div>
  );
}
