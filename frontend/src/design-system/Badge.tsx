import styles from "./Badge.module.css";

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "purple" | "teal";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}

export function StatusDot({ tone = "neutral" }: { tone?: Tone }) {
  return <span className={`${styles.dot} ${styles[tone]}`} />;
}
