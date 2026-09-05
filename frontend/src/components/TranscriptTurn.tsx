import { AlertTriangle } from "lucide-react";

import { Button } from "../design-system/Button";
import { TextInput } from "../design-system/FormControls";
import type { TranscriptSegment } from "../api/transcription";
import { SpeakerBadge } from "./SpeakerBadge";
import styles from "./TranscriptPanel.module.css";

function formatTs(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/** One transcript turn — extracted from TranscriptPanel so the segment
 * row markup (timestamp/speaker/confidence/review-flag/correction) is a
 * standalone, testable unit. All mutation/edit-state logic stays in the
 * parent; this component is presentational plus the inline-correction
 * form fields. */
export function TranscriptTurn({
  segment,
  speakerColorKey,
  speakerName,
  active,
  editing,
  editValue,
  canCorrect,
  onSeek,
  onStartEdit,
  onEditValueChange,
  onSaveEdit,
  onCancelEdit,
}: {
  segment: TranscriptSegment;
  speakerColorKey: string;
  speakerName: string;
  active: boolean;
  editing: boolean;
  editValue: string;
  canCorrect: boolean;
  onSeek: () => void;
  onStartEdit: () => void;
  onEditValueChange: (value: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
}) {
  return (
    <li className={`${styles.segment} ${active ? styles.segmentActive : ""}`}>
      <button
        type="button"
        className={styles.timestamp}
        onClick={onSeek}
        aria-label={`Zu ${formatTs(segment.start_ms)} springen`}
      >
        {formatTs(segment.start_ms)}
      </button>
      <div className={styles.segmentBody}>
        <div className={styles.segmentMeta}>
          <SpeakerBadge colorKey={speakerColorKey} label={speakerName} />
          {segment.confidence !== null && (
            <span className={styles.muted}>{Math.round(segment.confidence * 100)}%</span>
          )}
          {segment.review_flag && (
            <span
              className={styles.flag}
              role="img"
              aria-label={`Review nötig: ${segment.review_flag_reason ?? ""}`}
            >
              <AlertTriangle size={14} aria-hidden="true" /> prüfen
            </span>
          )}
        </div>
        {editing ? (
          <div className={styles.editRow}>
            <TextInput
              aria-label="Korrigierter Text"
              value={editValue}
              onChange={(event) => onEditValueChange(event.target.value)}
            />
            <Button variant="primary" type="button" onClick={onSaveEdit}>
              Speichern
            </Button>
            <Button variant="tertiary" type="button" onClick={onCancelEdit}>
              Abbrechen
            </Button>
          </div>
        ) : (
          <p
            onClick={() => {
              if (canCorrect) onStartEdit();
            }}
            className={canCorrect ? styles.editable : undefined}
          >
            {segment.corrected_text ?? segment.original_text}
          </p>
        )}
        {segment.corrected_text && <p className={styles.originalText}>Original: {segment.original_text}</p>}
      </div>
    </li>
  );
}
