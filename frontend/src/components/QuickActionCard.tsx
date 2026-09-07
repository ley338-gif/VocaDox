import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import styles from "./QuickActionCard.module.css";

/** One tile in the Dashboard's "Schnellaktionen" row — icon, title, short description, chevron. */
export function QuickActionCard({
  icon,
  title,
  description,
  onClick,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className={styles.card} onClick={onClick}>
      <span className={styles.icon}>{icon}</span>
      <span className={styles.body}>
        <span className={styles.title}>{title}</span>
        <span className={styles.description}>{description}</span>
      </span>
      <ChevronRight size={16} aria-hidden="true" className={styles.chevron} />
    </button>
  );
}
