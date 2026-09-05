import { speakerColor } from "../lib/speakerColor";
import styles from "./SpeakerBadge.module.css";

/**
 * Colored dot + speaker name, extracted from TranscriptPanel so the same
 * visual identity (stable color per speaker, see lib/speakerColor) is
 * reusable wherever a speaker is shown — transcript turns, rename chips,
 * the conversation sidebar's speaker-assignment summary.
 */
export function SpeakerBadge({
  colorKey,
  label,
  onClick,
  active,
}: {
  /** Stable key to hash into a color — DetectedSpeaker.internal_label. */
  colorKey: string;
  label: string;
  onClick?: () => void;
  active?: boolean;
}) {
  const content = (
    <span className={styles.badge}>
      <span className={styles.dot} style={{ background: speakerColor(colorKey) }} aria-hidden="true" />
      <span style={{ color: speakerColor(colorKey) }}>{label}</span>
    </span>
  );

  if (!onClick) return content;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        display: "inline-flex",
        alignItems: "center",
        border: `1px solid ${active ? speakerColor(colorKey) : "var(--border-default)"}`,
        borderRadius: "var(--radius-2xl)",
        padding: "4px 10px",
        background: active ? "var(--surface-sunken)" : "var(--surface-raised)",
        cursor: "pointer",
      }}
    >
      {content}
    </button>
  );
}
