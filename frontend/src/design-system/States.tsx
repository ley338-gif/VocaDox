import { AlertTriangle } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { Button } from "./Button";
import styles from "./States.module.css";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className={styles.empty}>
      {icon && <div className={styles.emptyIcon}>{icon}</div>}
      <p className={styles.emptyTitle}>{title}</p>
      {description && <p className={styles.emptyDescription}>{description}</p>}
      {action}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  details?: string;
}

export function ErrorState({ title = "Etwas ist schiefgelaufen", message, onRetry, details }: ErrorStateProps) {
  return (
    <div className={styles.error} role="alert">
      <div className={styles.errorHeader}>
        <AlertTriangle size={16} aria-hidden="true" />
        <span>{title}</span>
      </div>
      {message && <p className={styles.errorMessage}>{message}</p>}
      {details && <p className={styles.errorMessage}>{details}</p>}
      {onRetry && (
        <div className={styles.errorActions}>
          <Button variant="secondary" type="button" onClick={onRetry}>
            Erneut versuchen
          </Button>
        </div>
      )}
    </div>
  );
}

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  className?: string;
  style?: CSSProperties;
}

export function Skeleton({ width = "100%", height = "1rem", className, style }: SkeletonProps) {
  const classes = [styles.skeleton, className].filter(Boolean).join(" ");
  return <div className={classes} style={{ width, height, ...style }} aria-hidden="true" />;
}
