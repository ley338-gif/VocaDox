const DB_NAME = "vocadox-offline-queue";
const DB_VERSION = 2;
const STORE_NAME = "recordings";

export const RETRY_BASE_DELAY_MS = 5_000;
export const RETRY_MAX_DELAY_MS = 5 * 60_000;

export type QueueStatus = "pending" | "waiting-for-network" | "uploading" | "failed";

export interface QueuedMarker {
  timestampMs: number;
  label?: string;
}

export interface QueuedRecording {
  id: string;
  conversationId: string;
  ownerUserId: string;
  idempotencyKey: string;
  blob: Blob;
  markers: QueuedMarker[];
  createdAt: string;
  updatedAt: string;
  status: QueueStatus;
  attemptCount: number;
  nextAttemptAt: string | null;
  lastError: string | null;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      let store: IDBObjectStore;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
      } else {
        store = request.transaction!.objectStore(STORE_NAME);
      }
      if (!store.indexNames.contains("ownerUserId")) {
        store.createIndex("ownerUserId", "ownerUserId", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore, resolve: (value: T) => void, reject: (reason?: unknown) => void) => void
): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      operation(tx.objectStore(STORE_NAME), resolve, reject);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

export function isOfflineQueueSupported(): boolean {
  return typeof indexedDB !== "undefined";
}

export function queueRecordingId(ownerUserId: string, idempotencyKey: string): string {
  return `${ownerUserId}:${idempotencyKey}`;
}

export function retryDelayMs(attemptCount: number): number {
  return Math.min(
    RETRY_BASE_DELAY_MS * 2 ** Math.max(0, attemptCount - 1),
    RETRY_MAX_DELAY_MS
  );
}

export function normalizeQueuedRecording(
  entry: Partial<QueuedRecording> &
    Pick<QueuedRecording, "id" | "conversationId" | "ownerUserId" | "idempotencyKey" | "blob" | "markers" | "createdAt">
): QueuedRecording {
  const updatedAt = entry.updatedAt ?? entry.createdAt;
  return {
    ...entry,
    updatedAt,
    status: entry.status === "uploading" ? "pending" : (entry.status ?? "pending"),
    attemptCount: entry.attemptCount ?? 0,
    nextAttemptAt: entry.nextAttemptAt ?? null,
    lastError: entry.lastError ?? null,
  };
}

export async function enqueueRecording(
  entry: Omit<
    QueuedRecording,
    "id" | "createdAt" | "updatedAt" | "status" | "attemptCount" | "nextAttemptAt" | "lastError"
  >
): Promise<string> {
  const id = queueRecordingId(entry.ownerUserId, entry.idempotencyKey);
  const now = new Date().toISOString();
  const online = typeof navigator === "undefined" || navigator.onLine;
  const record: QueuedRecording = {
    ...entry,
    id,
    createdAt: now,
    updatedAt: now,
    status: online ? "pending" : "waiting-for-network",
    attemptCount: 0,
    nextAttemptAt: null,
    lastError: null,
  };
  await withStore<void>("readwrite", (store, resolve) => {
    store.put(record);
    store.transaction.oncomplete = () => resolve();
  });
  return id;
}

export async function listQueuedRecordings(ownerUserId: string): Promise<QueuedRecording[]> {
  const result = await withStore<QueuedRecording[]>("readonly", (store, resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result as QueuedRecording[]);
    request.onerror = () => reject(request.error);
  });
  return filterQueuedRecordingsForOwner(result, ownerUserId).map(normalizeQueuedRecording);
}

export function filterQueuedRecordingsForOwner(
  entries: QueuedRecording[],
  ownerUserId: string
): QueuedRecording[] {
  return entries.filter((entry) => entry.ownerUserId === ownerUserId);
}

export async function updateQueuedRecording(
  id: string,
  changes: Partial<QueuedRecording>
): Promise<void> {
  await withStore<void>("readwrite", (store, resolve, reject) => {
    const request = store.get(id);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      if (!request.result) {
        resolve();
        return;
      }
      store.put({ ...request.result, ...changes, id, updatedAt: new Date().toISOString() });
    };
    store.transaction.oncomplete = () => resolve();
  });
}

export async function resetFailedRecordings(ownerUserId: string): Promise<void> {
  const failed = (await listQueuedRecordings(ownerUserId)).filter((entry) => entry.status === "failed");
  await Promise.all(
    failed.map((entry) =>
      updateQueuedRecording(entry.id, {
        status: "pending",
        attemptCount: 0,
        nextAttemptAt: null,
        lastError: null,
      })
    )
  );
}

export async function removeFailedRecordings(ownerUserId: string): Promise<void> {
  const failed = (await listQueuedRecordings(ownerUserId)).filter((entry) => entry.status === "failed");
  await Promise.all(failed.map((entry) => removeQueuedRecording(entry.id)));
}

export async function removeQueuedRecording(id: string): Promise<void> {
  await withStore<void>("readwrite", (store, resolve) => {
    store.delete(id);
    store.transaction.oncomplete = () => resolve();
  });
}
