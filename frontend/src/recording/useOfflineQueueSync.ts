/**
 * Post-GA P2-3: flushes the IndexedDB offline recording queue whenever
 * the browser reports it's back online (plus once on mount, in case
 * connectivity returned while the app wasn't loaded). Mounted once at
 * the app shell so it runs regardless of which page the user is on.
 *
 * Deliberately sequential, one entry at a time, oldest first: a mobile
 * connection regaining signal is often still weak, and firing many
 * concurrent large-audio uploads at once would be more likely to fail
 * all of them than to succeed. A single failure stops the flush for this
 * pass (the next `online` event or app load retries the whole queue) --
 * simpler and safer than partial bookkeeping of "which ones already
 * failed this pass".
 */
import { useCallback, useEffect, useState } from "react";

import { addMarker, finalizeRecording } from "../api/conversations";
import {
  isOfflineQueueSupported,
  listQueuedRecordings,
  removeQueuedRecording,
} from "./offlineQueue";

export function useOfflineQueueSync(csrfToken: string | null, userId: string | null) {
  const [pendingCount, setPendingCount] = useState(0);
  const [isSyncing, setIsSyncing] = useState(false);

  const refreshCount = useCallback(async () => {
    if (!isOfflineQueueSupported() || !userId) return;
    const queued = await listQueuedRecordings(userId);
    setPendingCount(queued.length);
  }, [userId]);

  const flush = useCallback(async () => {
    if (!csrfToken || !userId || !isOfflineQueueSupported() || isSyncing) return;
    setIsSyncing(true);
    try {
      const queued = await listQueuedRecordings(userId);
      const sorted = [...queued].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
      for (const entry of sorted) {
        try {
          await finalizeRecording(entry.conversationId, entry.blob, entry.idempotencyKey, csrfToken);
          await Promise.allSettled(
            entry.markers.map((marker) =>
              addMarker(
                entry.conversationId,
                { timestamp_ms: Math.round(marker.timestampMs), label: marker.label },
                csrfToken
              )
            )
          );
          await removeQueuedRecording(entry.id);
        } catch {
          // Still offline, or the server rejected it -- stop this pass;
          // the entry stays queued and the next online/mount trigger
          // retries from the top.
          break;
        }
      }
    } finally {
      setIsSyncing(false);
      await refreshCount();
    }
  }, [csrfToken, userId, isSyncing, refreshCount]);

  useEffect(() => {
    void refreshCount();
    void flush();
    const handleOnline = () => void flush();
    window.addEventListener("online", handleOnline);
    return () => window.removeEventListener("online", handleOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [csrfToken, userId]);

  return { pendingCount, isSyncing };
}
