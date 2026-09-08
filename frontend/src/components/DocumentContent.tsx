import type { DocumentLayout, DocumentSection } from "../api/documents";
import styles from "./DocumentContent.module.css";

// Static chrome for the "letter" layout — never fact-derived, so it
// deliberately stays out of `structured_content` (every statement there
// must trace back to real fact_ids). Mirrored in the backend's
// app.documents.router._letter_chrome for DOCX/PDF export.
const LETTER_SALUTATION = "Sehr geehrte Kolleginnen und Kollegen,";
const LETTER_CLOSING = "Mit freundlichen kollegialen Grüßen";

/**
 * Renders a document revision's `structured_content` (section title +
 * statement list) as real headings/lists instead of the flattened
 * `rendered_text` string — the structure already exists server-side
 * (see backend app.documents.service.compose_document), this just stops
 * discarding it on the way to the screen.
 *
 * `layout="letter"` (post-GA — a profile/template choice, e.g. the
 * "Medical Consultation" template) renders the exact same sections as a
 * formal letter instead: a subject line, salutation, prose paragraphs
 * (no bullets) per section, and a closing line.
 */
export function DocumentContent({
  sections,
  layout = "sections",
  conversationTitle,
  generatedAt,
  maxStatements,
}: {
  sections: DocumentSection[];
  layout?: DocumentLayout;
  /** Required to build the letter's subject line; ignored for "sections". */
  conversationTitle?: string;
  /** Required to build the letter's subject line; ignored for "sections". */
  generatedAt?: string;
  /** When set, shows only the first N statements total (across sections)
   * — used for the Übersicht "Kurzfassung" preview so it stays a short
   * summary instead of duplicating the entire Dokumentation tab. */
  maxStatements?: number;
}) {
  if (sections.length === 0) {
    return <p className={styles.empty}>(Keine Fakten zum Zusammenstellen)</p>;
  }

  if (layout === "freeform") {
    // Post-GA: `sections` is one aggregate pseudo-section (title=null) —
    // see backend app.documents.service.compose_document. The author's
    // own text already contains all letterhead/salutation/closing
    // wording verbatim, so nothing is synthesized here (unlike "letter").
    // `maxStatements` has no natural "N statements" meaning for a single
    // flowing body — reinterpreted as "max paragraphs" instead, the only
    // sane adaptation for the Übersicht "Kurzfassung" preview.
    const bodyText = sections[0]?.statements[0]?.text ?? "";
    const allParagraphs = bodyText.split(/\n\n+/).filter((p) => p.trim());
    const shown = maxStatements != null ? allParagraphs.slice(0, maxStatements) : allParagraphs;
    const wasTruncated = maxStatements != null && allParagraphs.length > maxStatements;
    return (
      <div className={styles.freeform}>
        {shown.map((paragraph, index) => (
          <p key={index} className={styles.freeformParagraph}>
            {paragraph}
          </p>
        ))}
        {wasTruncated && <p className={styles.truncated}>…</p>}
      </div>
    );
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

  if (layout === "letter") {
    const subject =
      conversationTitle && generatedAt
        ? `Betreff: ${conversationTitle} vom ${new Date(generatedAt).toLocaleDateString("de-DE")}`
        : null;
    return (
      <div className={styles.letter}>
        {subject && <p className={styles.letterSubject}>{subject}</p>}
        <p>{LETTER_SALUTATION}</p>
        {visibleSections.map((section) => (
          <section key={section.category} className={styles.letterSection}>
            <h3 className={styles.sectionTitle}>{section.title}</h3>
            {section.statements.map((statement, index) => (
              <p key={index} className={styles.letterParagraph}>
                {statement.text}
              </p>
            ))}
          </section>
        ))}
        {truncated && <p className={styles.truncated}>…</p>}
        <p className={styles.letterClosing}>{LETTER_CLOSING}</p>
      </div>
    );
  }

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
