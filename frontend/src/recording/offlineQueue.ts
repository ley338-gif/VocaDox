/**
 * Post-GA P2-3: IndexedDB-backed queue for a finished recording that
 * couldn't be uploaded (offline, or the upload request itself failed to
 * even reach the network). Unlike the existing in-memory "upload-failed,
 * click retry" state (`recordingMachine.ts`), a queued entry survives a
 * page reload/app restart — the actual point of an *offline* queue on a
 * mobile PWA, where losing connectivity and closing the browser/app
 * mid-session is the normal case being designed for, not an edge case.
 *
 * No new dependency — IndexedDB is a native browser API; this is a thin,
 * hand-written wrapper scoped to exactly the one shape this feature
 * needs, not a general-purpose IndexedDB library.
 */

const DB_NAME = "vocadox-offline-queue";
const DB_VERSION = 1;
const STORE_NAME = "recordings";

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
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export function isOfflineQueueSupported(): boolean {
  return typeof indexedDB !== "undefined";
}

export async function enqueueRecording(
  entry: Omit<QueuedRecording, "id" | "createdAt">
): Promise<string> {
  const db = await openDb();
  const id = crypto.randomUUID();
  const record: QueuedRecording = { ...entry, id, createdAt: new Date().toISOString() };
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  return id;
}

export async function listQueuedRecordings(ownerUserId: string): Promise<QueuedRecording[]> {
  const db = await openDb();
  const result = await new Promise<QueuedRecording[]>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const request = tx.objectStore(STORE_NAME).getAll();
    request.onsuccess = () => resolve(request.result as QueuedRecording[]);
    request.onerror = () => reject(request.error);
  });
  db.close();
  // Records created before owner binding intentionally remain quarantined
  // instead of being exposed or uploaded under whoever logs in next.
  return filterQueuedRecordingsForOwner(result, ownerUserId);
}

export function filterQueuedRecordingsForOwner(
  entries: QueuedRecording[],
  ownerUserId: string
): QueuedRecording[] {
  return entries.filter((entry) => entry.ownerUserId === ownerUserId);
}

export async function removeQueuedRecording(id: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}
