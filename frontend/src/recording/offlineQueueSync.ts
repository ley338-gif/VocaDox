import { ApiError } from "../api/client";
import type { QueuedRecording } from "./offlineQueue";
import { retryDelayMs } from "./offlineQueue";

export interface OfflineQueueSyncDependencies {
  list: () => Promise<QueuedRecording[]>;
  update: (id: string, changes: Partial<QueuedRecording>) => Promise<void>;
  remove: (id: string) => Promise<void>;
  upload: (entry: QueuedRecording) => Promise<unknown>;
  uploadMarker: (
    entry: QueuedRecording,
    marker: QueuedRecording["markers"][number]
  ) => Promise<unknown>;
}

export interface OfflineQueueSyncResult {
  completedCount: number;
  nextRetryAt: number | null;
}

function uploadErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return `HTTP ${error.status}`;
  return "Netzwerkfehler";
}

export function isRetryableUploadError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === 408 || error.status === 425 || error.status === 429 || error.status >= 500;
}

export async function processOfflineQueue(
  dependencies: OfflineQueueSyncDependencies,
  options: { online: boolean; now?: number }
): Promise<OfflineQueueSyncResult> {
  const now = options.now ?? Date.now();
  const queued = [...(await dependencies.list())].sort((a, b) =>
    a.createdAt.localeCompare(b.createdAt)
  );
  let completedCount = 0;
  let nextRetryAt: number | null = null;

  for (const entry of queued) {
    if (entry.status === "failed") continue;

    if (!options.online) {
      if (entry.status !== "waiting-for-network") {
        await dependencies.update(entry.id, { status: "waiting-for-network" });
      }
      continue;
    }

    const dueAt = entry.nextAttemptAt ? Date.parse(entry.nextAttemptAt) : now;
    if (dueAt > now) {
      nextRetryAt = nextRetryAt === null ? dueAt : Math.min(nextRetryAt, dueAt);
      continue;
    }

    const attemptCount = entry.attemptCount + 1;
    await dependencies.update(entry.id, {
      status: "uploading",
      attemptCount,
      nextAttemptAt: null,
      lastError: null,
    });

    try {
      await dependencies.upload(entry);
      await Promise.allSettled(
        entry.markers.map((marker) => dependencies.uploadMarker(entry, marker))
      );
      await dependencies.remove(entry.id);
      completedCount += 1;
    } catch (error) {
      if (!isRetryableUploadError(error)) {
        await dependencies.update(entry.id, {
          status: "failed",
          nextAttemptAt: null,
          lastError: uploadErrorMessage(error),
        });
        continue;
      }

      const retryAt = now + retryDelayMs(attemptCount);
      await dependencies.update(entry.id, {
        status: "waiting-for-network",
        nextAttemptAt: new Date(retryAt).toISOString(),
        lastError: uploadErrorMessage(error),
      });
      nextRetryAt = retryAt;
      break;
    }
  }

  return { completedCount, nextRetryAt };
}
