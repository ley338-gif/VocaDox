import type { ReactNode } from "react";

import { Card } from "./Card";
import styles from "./SidePanelCard.module.css";

/**
 * Right-rail card used across detail pages (Kurzfassung/Marker/
 * Teilnehmer/Aufgaben on the Conversation detail page) — an icon-badged
 * title over a thin Card, with an optional trailing action (a "show
 * more"-style link/button).
 */
interface SidePanelCardProps {
  icon: ReactNode;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}

export function SidePanelCard({ icon, title, action, children }: SidePanelCardProps) {
  return (
    <Card
      title={
        <span className={styles.header}>
          <span className={styles.icon}>{icon}</span>
          <span className={styles.title}>{title}</span>
        </span>
      }
      actions={action}
    >
      {children}
    </Card>
  );
}
