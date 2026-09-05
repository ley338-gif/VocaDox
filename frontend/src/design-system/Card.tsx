import type { ReactNode } from "react";

import styles from "./Card.module.css";

interface CardProps {
  children: ReactNode;
  title?: ReactNode;
  actions?: ReactNode;
  padded?: boolean;
  className?: string;
}

export function Card({ children, title, actions, padded = true, className }: CardProps) {
  const classes = [styles.card, className].filter(Boolean).join(" ");
  return (
    <div className={classes}>
      {(title ?? actions) && (
        <div className={styles.cardHeader}>
          {title && <h3 className={styles.cardTitle}>{title}</h3>}
          {actions}
        </div>
      )}
      <div className={padded ? styles.padded : undefined}>{children}</div>
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  hint?: string;
}

export function StatCard({ label, value, icon, hint }: StatCardProps) {
  return (
    <div className={`${styles.card} ${styles.statCard}`}>
      {icon && <div className={styles.statIcon}>{icon}</div>}
      <div className={styles.statBody}>
        <span className={styles.statValue}>{value}</span>
        <span className={styles.statLabel}>{label}</span>
        {hint && <span className={styles.statHint}>{hint}</span>}
      </div>
    </div>
  );
}
