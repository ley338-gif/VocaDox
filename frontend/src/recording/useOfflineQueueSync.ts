import { useCallback, useEffect, useRef, useState } from "react";

import { addMarker, finalizeRecording } from "../api/conversations";
import {
  isOfflineQueueSupported,
  listQueuedRecordings,
  removeFailedRecordings,
  removeQueuedRecording,
  resetFailedRecordings,
  RETRY_BASE_DELAY_MS,
  updateQueuedRecording,
} from "./offlineQueue";
import { processOfflineQueue } from "./offlineQueueSync";

const readOnline = () => typeof navigator === "undefined" || navigator.onLine;

export function useOfflineQueueSync(csrfToken: string | null, userId: string | null) {
  const [pendingCount, setPendingCount] = useState(0);
  const [failedCount, setFailedCount] = useState(0);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isOnline, setIsOnline] = useState(readOnline);
  const [nextRetryAt, setNextRetryAt] = useState<number | null>(null);
  const [recentlyCompleted, setRecentlyCompleted] = useState(0);
  const syncingRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!isOfflineQueueSupported() || !userId) {
      setPendingCount(0);
      setFailedCount(0);
      return;
    }
    const queued = await listQueuedRecordings(userId);
    setPendingCount(queued.length);
    setFailedCount(queued.filter((entry) => entry.status === "failed").length);
  }, [userId]);

  const flush = useCallback(async () => {
    if (!csrfToken || !userId || !isOfflineQueueSupported() || syncingRef.current) return;
    syncingRef.current = true;
    setIsSyncing(true);
    try {
      const result = await processOfflineQueue(
        {
          list: () => listQueuedRecordings(userId),
          update: updateQueuedRecording,
          remove: removeQueuedRecording,
          upload: (entry) =>
            finalizeRecording(
              entry.conversationId,
              entry.blob,
              entry.idempotencyKey,
              csrfToken
            ),
          uploadMarker: (entry, marker) =>
            addMarker(
              entry.conversationId,
              { timestamp_ms: Math.round(marker.timestampMs), label: marker.label },
              csrfToken
            ),
        },
        { online: readOnline() }
      );
      setNextRetryAt(result.nextRetryAt);
      if (result.completedCount > 0) {
        setRecentlyCompleted(result.completedCount);
        window.setTimeout(() => setRecentlyCompleted(0), 5_000);
      }
    } catch {
      setNextRetryAt(Date.now() + RETRY_BASE_DELAY_MS);
    } finally {
      syncingRef.current = false;
      setIsSyncing(false);
      try {
        await refresh();
      } catch {
        // IndexedDB can be temporarily unavailable (for example in private mode).
      }
    }
  }, [csrfToken, refresh, userId]);

  const retryFailed = useCallback(async () => {
    if (!userId) return;
    await resetFailedRecordings(userId);
    await refresh();
    await flush();
  }, [flush, refresh, userId]);

  const discardFailed = useCallback(async () => {
    if (!userId) return;
    await removeFailedRecordings(userId);
    await refresh();
  }, [refresh, userId]);

  useEffect(() => {
    void refresh();
    void flush();
    const handleOnline = () => {
      setIsOnline(true);
      void flush();
    };
    const handleOffline = () => {
      setIsOnline(false);
      void flush();
    };
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [flush, refresh]);

  useEffect(() => {
    if (nextRetryAt === null || !isOnline) return;
    const timeout = window.setTimeout(() => void flush(), Math.max(0, nextRetryAt - Date.now()));
    return () => window.clearTimeout(timeout);
  }, [flush, isOnline, nextRetryAt]);

  return {
    pendingCount,
    failedCount,
    isSyncing,
    isOnline,
    recentlyCompleted,
    retryFailed,
    discardFailed,
  };
}
