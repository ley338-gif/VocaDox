import type { ReactNode } from "react";

import styles from "./IconAvatar.module.css";

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "purple" | "teal";

/**
 * A small round, tone-tinted icon badge (e.g. a status glyph next to a
 * list row) — same tone vocabulary/tint formula as Badge/StatusDot
 * (`design-system/Badge.module.css`) so a given tone always reads the
 * same color everywhere, just in a bigger circular shape instead of a
 * text pill or dot.
 */
export function IconAvatar({ tone = "neutral", icon }: { tone?: Tone; icon: ReactNode }) {
  return (
    <span className={`${styles.avatar} ${styles[tone]}`} aria-hidden="true">
      {icon}
    </span>
  );
}
