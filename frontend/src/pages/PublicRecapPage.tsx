/**
 * Post-GA P3-2: the one page in this app reachable with no VocaDox
 * login at all — a time-limited Recap share link. Deliberately minimal:
 * no navigation, no other conversation data, nothing beyond the recap
 * text itself and when the link expires.
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Sparkles } from "lucide-react";
import { useParams } from "react-router";

import { getPublicRecap } from "../api/recap";
import { ApiError } from "../api/client";
import { Skeleton } from "../design-system/States";
import styles from "./PublicRecapPage.module.css";

export function PublicRecapPage() {
  const { token } = useParams<{ token: string }>();

  const recapQuery = useQuery({
    queryKey: ["public-recap", token],
    queryFn: () => getPublicRecap(token ?? ""),
    enabled: Boolean(token),
    retry: false,
  });

  if (recapQuery.isLoading) {
    return (
      <div className={styles.page}>
        <Skeleton height="8rem" />
      </div>
    );
  }

  if (recapQuery.isError) {
    const notFound = recapQuery.error instanceof ApiError && recapQuery.error.status === 404;
    return (
      <div className={styles.page}>
        <div className={styles.errorBox} role="alert">
          <AlertTriangle size={20} aria-hidden="true" />
          <p>
            {notFound
              ? "Dieser Link ist ungültig, abgelaufen oder wurde widerrufen."
              : "Der Recap konnte nicht geladen werden."}
          </p>
        </div>
      </div>
    );
  }

  const recap = recapQuery.data;
  if (!recap) return null;

  return (
    <div className={styles.page}>
      <p className={styles.disclosure}>
        <Sparkles size={13} aria-hidden="true" /> KI-generierte Zusammenfassung eines Gesprächs —
        gültig bis {new Date(recap.expires_at).toLocaleString("de-DE")}.
      </p>
      <div className={styles.content}>{recap.content}</div>
    </div>
  );
}
