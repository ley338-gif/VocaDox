import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import styles from "./NavCard.module.css";

interface NavCardProps {
  icon: ReactNode;
  title: string;
  description: ReactNode;
  onClick: () => void;
}

export function NavCard({ icon, title, description, onClick }: NavCardProps) {
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
