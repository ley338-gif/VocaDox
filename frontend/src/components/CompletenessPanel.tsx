import { CheckCircle2, CircleDashed, Mic } from "lucide-react";

import type { Completeness } from "../api/completeness";
import { Badge } from "../design-system/Badge";
import { EmptyState, Skeleton } from "../design-system/States";
import styles from "./CompletenessPanel.module.css";

function scoreTone(score: number): "success" | "warning" | "danger" {
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "danger";
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

interface CompletenessPanelProps {
  completeness: Completeness | undefined;
  isLoading: boolean;
}

/**
 * Post-GA P1-3: shows whether the conversation currently covers its
 * Template's required categories, whether every decision/task has a
 * decision-maker/owner, and speaking-share/longest-monologue from
 * diarization — a live indicator, never a generated document claim (no
 * AI Evidence involved, purely derived from existing facts/segments).
 */
export function CompletenessPanel({ completeness, isLoading }: CompletenessPanelProps) {
  if (isLoading) return <Skeleton height="6rem" />;
  if (!completeness) return <EmptyState title="Keine Daten verfügbar" />;

  return (
    <div className={styles.panel}>
      <div className={styles.scoreRow}>
        <Badge tone={scoreTone(completeness.overall_score)}>
          {Math.round(completeness.overall_score * 100)}% vollständig
        </Badge>
        {completeness.template_name && (
          <span className={styles.templateLabel}>gegen „{completeness.template_name}“</span>
        )}
      </div>

      <ul className={styles.categoryList}>
        {completeness.categories.map((category) => (
          <li key={category.category} className={styles.categoryItem}>
            {category.covered ? (
              <CheckCircle2 size={14} className={styles.coveredIcon} aria-hidden="true" />
            ) : (
              <CircleDashed size={14} className={styles.missingIcon} aria-hidden="true" />
            )}
            <span>{category.title}</span>
            {category.fact_count > 0 && (
              <span className={styles.factCount}>({category.fact_count})</span>
            )}
          </li>
        ))}
      </ul>

      {completeness.decisions_total > 0 && completeness.decisions_missing_decided_by > 0 && (
        <p className={styles.gapText}>
          {completeness.decisions_missing_decided_by} von {completeness.decisions_total}{" "}
          Entscheidungen ohne Entscheidungsträger.
        </p>
      )}
      {completeness.tasks_total > 0 && completeness.tasks_missing_assignee > 0 && (
        <p className={styles.gapText}>
          {completeness.tasks_missing_assignee} von {completeness.tasks_total} Aufgaben ohne
          Verantwortliche(n).
        </p>
      )}

      {completeness.speaking_shares.length > 0 && (
        <div className={styles.speakingSection}>
          <p className={styles.sectionHeading}>
            <Mic size={13} aria-hidden="true" /> Redeanteil
          </p>
          <ul className={styles.speakingList}>
            {completeness.speaking_shares.map((share) => (
              <li key={share.speaker_id} className={styles.speakingItem}>
                <span>{share.label}</span>
                <span>{Math.round(share.share * 100)}%</span>
              </li>
            ))}
          </ul>
          {completeness.longest_monologue && (
            <p className={styles.monologueText}>
              Längster Monolog: {completeness.longest_monologue.label} (
              {formatDuration(completeness.longest_monologue.duration_ms)})
            </p>
          )}
        </div>
      )}
    </div>
  );
}
