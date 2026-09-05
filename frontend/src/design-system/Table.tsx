import { ChevronDown, ChevronUp } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { Skeleton } from "./States";
import styles from "./Table.module.css";

export interface DataTableColumn<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  sortValue?: (row: T) => string | number;
  align?: "left" | "right" | "center";
  width?: string;
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  keyExtractor: (row: T) => string;
  loading?: boolean;
  error?: ReactNode;
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
  rowActions?: (row: T) => ReactNode;
  skeletonRows?: number;
}

type SortDirection = "asc" | "desc";

export function DataTable<T>({
  columns,
  rows,
  keyExtractor,
  loading,
  error,
  empty,
  onRowClick,
  rowActions,
  skeletonRows = 5,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const column = columns.find((c) => c.key === sortKey);
    if (!column?.sortValue) return rows;
    const sortValue = column.sortValue;
    const factor = sortDirection === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = sortValue(a);
      const bv = sortValue(b);
      if (av < bv) return -1 * factor;
      if (av > bv) return 1 * factor;
      return 0;
    });
  }, [rows, sortKey, sortDirection, columns]);

  const columnCount = columns.length + (rowActions ? 1 : 0);

  function toggleSort(column: DataTableColumn<T>) {
    if (!column.sortable) return;
    if (sortKey === column.key) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(column.key);
      setSortDirection("asc");
    }
  }

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                style={{ width: column.width, textAlign: column.align }}
                aria-sort={
                  sortKey === column.key ? (sortDirection === "asc" ? "ascending" : "descending") : undefined
                }
              >
                {column.sortable ? (
                  <button type="button" className={styles.sortable} onClick={() => toggleSort(column)}>
                    <span className={styles.thContent}>
                      {column.header}
                      {sortKey === column.key &&
                        (sortDirection === "asc" ? (
                          <ChevronUp size={12} aria-hidden="true" />
                        ) : (
                          <ChevronDown size={12} aria-hidden="true" />
                        ))}
                    </span>
                  </button>
                ) : (
                  <span className={styles.thContent}>{column.header}</span>
                )}
              </th>
            ))}
            {rowActions && <th aria-label="Aktionen" />}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: skeletonRows }).map((_, rowIndex) => (
              <tr key={rowIndex}>
                {Array.from({ length: columnCount }).map((__, colIndex) => (
                  <td key={colIndex}>
                    <Skeleton height="1rem" />
                  </td>
                ))}
              </tr>
            ))
          ) : error ? (
            <tr>
              <td colSpan={columnCount} className={styles.statusCell}>
                {error}
              </td>
            </tr>
          ) : sortedRows.length === 0 ? (
            <tr>
              <td colSpan={columnCount} className={styles.statusCell}>
                {empty}
              </td>
            </tr>
          ) : (
            sortedRows.map((row) => (
              <tr
                key={keyExtractor(row)}
                className={onRowClick ? styles.clickableRow : undefined}
                onClick={() => onRowClick?.(row)}
                tabIndex={onRowClick ? 0 : undefined}
                role={onRowClick ? "button" : undefined}
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
              >
                {columns.map((column) => (
                  <td key={column.key} style={{ textAlign: column.align }}>
                    {column.render(row)}
                  </td>
                ))}
                {rowActions && (
                  <td
                    className={styles.actionsCell}
                    onClick={(event) => event.stopPropagation()}
                  >
                    {rowActions(row)}
                  </td>
                )}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
