import { describe, expect, it } from "vitest";

import {
  filterQueuedRecordingsForOwner,
  normalizeQueuedRecording,
  queueRecordingId,
  retryDelayMs,
  type QueuedRecording,
} from "./offlineQueue";

function queued(ownerUserId: string | undefined, id: string): QueuedRecording {
  return {
    id,
    conversationId: `conversation-${id}`,
    ownerUserId,
    idempotencyKey: `key-${id}`,
    blob: new Blob([id]),
    markers: [],
    createdAt: "2026-09-10T00:00:00.000Z",
    updatedAt: "2026-09-10T00:00:00.000Z",
    status: "pending",
    attemptCount: 0,
    nextAttemptAt: null,
    lastError: null,
  } as QueuedRecording;
}

describe("filterQueuedRecordingsForOwner", () => {
  it("returns only recordings owned by the current immutable user id", () => {
    const result = filterQueuedRecordingsForOwner(
      [queued("user-a", "a"), queued("user-b", "b")],
      "user-a"
    );
    expect(result.map((entry) => entry.id)).toEqual(["a"]);
  });

  it("quarantines legacy records without an owner", () => {
    expect(filterQueuedRecordingsForOwner([queued(undefined, "legacy")], "user-a")).toEqual([]);
  });
});

describe("offline queue reliability helpers", () => {
  it("uses the server idempotency key to deduplicate the same local upload", () => {
    expect(queueRecordingId("user-a", "take-123")).toBe("user-a:take-123");
  });

  it("backs off exponentially and caps retries at five minutes", () => {
    expect(retryDelayMs(1)).toBe(5_000);
    expect(retryDelayMs(2)).toBe(10_000);
    expect(retryDelayMs(7)).toBe(300_000);
  });

  it("recovers an interrupted uploading record after an app restart", () => {
    expect(normalizeQueuedRecording({ ...queued("user-a", "a"), status: "uploading" }).status).toBe(
      "pending"
    );
  });
});
