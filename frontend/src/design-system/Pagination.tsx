import { ChevronLeft, ChevronRight } from "lucide-react";

import styles from "./Pagination.module.css";

interface PaginationProps {
  offset: number;
  limit: number;
  total: number;
  onOffsetChange: (offset: number) => void;
}

export function Pagination({ offset, limit, total, onOffsetChange }: PaginationProps) {
  if (total === 0) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className={styles.pagination}>
      <span className={styles.summary}>
        {from}–{to} von {total}
      </span>
      <div className={styles.controls}>
        <button
          type="button"
          className={styles.pageButton}
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
          aria-label="Vorherige Seite"
        >
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <button
          type="button"
          className={styles.pageButton}
          disabled={offset + limit >= total}
          onClick={() => onOffsetChange(offset + limit)}
          aria-label="Nächste Seite"
        >
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
