import { useQuery } from "@tanstack/react-query";
import { FileText, ListTree } from "lucide-react";

import { getProtocol } from "../api/protocols";
import { SidePanelCard } from "../design-system/SidePanelCard";
import { Skeleton } from "../design-system/States";
import styles from "./ProtocolSidebarCards.module.css";

const SECTION_TYPE_LABELS: Record<string, string> = {
  introduction: "Einleitung",
  topic: "Thema",
  facts: "Fakten",
  discussion: "Diskussion",
  decision: "Entscheidung",
  action_items: "Aufgaben",
  open_questions: "Offene Punkte",
  note: "Notiz",
  conclusion: "Abschluss",
};

/** "Protokollstatus": a compact summary card, sharing the same
 * `["protocol", conversationId]` query as ProtocolPanel (React Query
 * dedupes the request — no extra network call). */
export function ProtocolStatusCard({ conversationId }: { conversationId: string }) {
  const query = useQuery({
    queryKey: ["protocol", conversationId],
    queryFn: () => getProtocol(conversationId),
  });

  if (query.isLoading) {
    return (
      <SidePanelCard icon={<FileText size={16} aria-hidden="true" />} title="Protokollstatus">
        <Skeleton height="3rem" />
      </SidePanelCard>
    );
  }

  const revision = query.data?.current_revision;
  if (!revision) {
    return (
      <SidePanelCard icon={<FileText size={16} aria-hidden="true" />} title="Protokollstatus">
        <p className={styles.empty}>Noch kein Protokoll erstellt</p>
      </SidePanelCard>
    );
  }

  const itemCounts = revision.sections.flatMap((s) => s.items).reduce(
    (acc, item) => {
      acc[item.item_type] = (acc[item.item_type] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
  const importantPoints = itemCounts.important_point ?? 0;
  const decisions = itemCounts.decision ?? 0;
  const actionItems = itemCounts.action_item ?? 0;

  return (
    <SidePanelCard icon={<FileText size={16} aria-hidden="true" />} title="Protokollstatus">
      <div className={styles.statusRow}>
        <span className={styles.statusBadge}>
          {revision.status === "ready" ? "Aktuell" : revision.status}
        </span>
      </div>
      <p className={styles.meta}>
        Erstellt: {new Date(revision.created_at).toLocaleString("de-DE")}
      </p>
      <ul className={styles.countList}>
        <li>{revision.sections.length} Abschnitte</li>
        {importantPoints > 0 && <li>{importantPoints} wichtige Punkte</li>}
        {decisions > 0 && <li>{decisions} Beschlüsse</li>}
        {actionItems > 0 && <li>{actionItems} Aufgaben</li>}
      </ul>
    </SidePanelCard>
  );
}

/** "Gesprächsstruktur": the section list as a navigable outline. Clicking
 * an entry scrolls it into view when the Protokoll tab is already
 * mounted (best-effort, synchronous DOM lookup — the section elements
 * carry a stable `protocol-section-{id}` id for exactly this); it always
 * also calls `onSelectSection` so the caller can switch to the Protokoll
 * tab if it isn't already active. */
export function ProtocolStructureCard({
  conversationId,
  onSelectSection,
}: {
  conversationId: string;
  onSelectSection: (sectionId: string) => void;
}) {
  const query = useQuery({
    queryKey: ["protocol", conversationId],
    queryFn: () => getProtocol(conversationId),
  });

  const sections = query.data?.current_revision?.sections ?? [];
  if (!query.isLoading && sections.length === 0) return null;

  return (
    <SidePanelCard icon={<ListTree size={16} aria-hidden="true" />} title="Gesprächsstruktur">
      {query.isLoading ? (
        <Skeleton height="3rem" />
      ) : (
        <>
          <p className={styles.meta}>{sections.length} Abschnitte</p>
          <ol className={styles.structureList}>
            {sections.map((section, index) => (
              <li key={section.id}>
                <button
                  type="button"
                  className={styles.structureItem}
                  onClick={() => {
                    document
                      .getElementById(`protocol-section-${section.id}`)
                      ?.scrollIntoView({ behavior: "smooth", block: "start" });
                    onSelectSection(section.id);
                  }}
                  title={SECTION_TYPE_LABELS[section.section_type] ?? section.section_type}
                >
                  <span className={styles.structureIndex}>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className={styles.structureTitle}>{section.title}</span>
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
    </SidePanelCard>
  );
}
