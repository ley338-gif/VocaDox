import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import type { QueuedRecording } from "./offlineQueue";
import { processOfflineQueue, type OfflineQueueSyncDependencies } from "./offlineQueueSync";

function queued(id: string, overrides: Partial<QueuedRecording> = {}): QueuedRecording {
  return {
    id,
    conversationId: `conversation-${id}`,
    ownerUserId: "user-a",
    idempotencyKey: `key-${id}`,
    blob: new Blob([id]),
    markers: [],
    createdAt: `2026-09-10T00:00:0${id}.000Z`,
    updatedAt: "2026-09-10T00:00:00.000Z",
    status: "pending",
    attemptCount: 0,
    nextAttemptAt: null,
    lastError: null,
    ...overrides,
  };
}

function dependencies(entries: QueuedRecording[]): OfflineQueueSyncDependencies {
  return {
    list: vi.fn().mockResolvedValue(entries),
    update: vi.fn().mockResolvedValue(undefined),
    remove: vi.fn().mockResolvedValue(undefined),
    upload: vi.fn().mockResolvedValue(undefined),
    uploadMarker: vi.fn().mockResolvedValue(undefined),
  };
}

describe("processOfflineQueue", () => {
  it("removes a recording only after its upload succeeds", async () => {
    const deps = dependencies([queued("1", { markers: [{ timestampMs: 123 }] })]);

    const result = await processOfflineQueue(deps, { online: true, now: 0 });

    expect(deps.upload).toHaveBeenCalledOnce();
    expect(deps.uploadMarker).toHaveBeenCalledOnce();
    expect(deps.remove).toHaveBeenCalledWith("1");
    expect(result.completedCount).toBe(1);
  });

  it("schedules a transient failure and stops to protect a weak connection", async () => {
    const deps = dependencies([queued("1"), queued("2")]);
    vi.mocked(deps.upload).mockRejectedValueOnce(new TypeError("network"));

    const result = await processOfflineQueue(deps, { online: true, now: 0 });

    expect(deps.upload).toHaveBeenCalledOnce();
    expect(deps.update).toHaveBeenLastCalledWith("1", {
      status: "waiting-for-network",
      nextAttemptAt: "1970-01-01T00:00:05.000Z",
      lastError: "Netzwerkfehler",
    });
    expect(result.nextRetryAt).toBe(5_000);
  });

  it("marks a permanent rejection as failed and continues with later recordings", async () => {
    const deps = dependencies([queued("1"), queued("2")]);
    vi.mocked(deps.upload).mockRejectedValueOnce(new ApiError(400, "invalid"));

    const result = await processOfflineQueue(deps, { online: true, now: 0 });

    expect(deps.update).toHaveBeenCalledWith("1", {
      status: "failed",
      nextAttemptAt: null,
      lastError: "HTTP 400",
    });
    expect(deps.remove).toHaveBeenCalledWith("2");
    expect(result.completedCount).toBe(1);
  });

  it("waits until a future retry is due", async () => {
    const deps = dependencies([
      queued("1", { nextAttemptAt: "1970-01-01T00:00:10.000Z" }),
    ]);

    const result = await processOfflineQueue(deps, { online: true, now: 5_000 });

    expect(deps.upload).not.toHaveBeenCalled();
    expect(result.nextRetryAt).toBe(10_000);
  });

  it("marks pending recordings as waiting while offline", async () => {
    const deps = dependencies([queued("1")]);

    await processOfflineQueue(deps, { online: false, now: 0 });

    expect(deps.update).toHaveBeenCalledWith("1", { status: "waiting-for-network" });
    expect(deps.upload).not.toHaveBeenCalled();
  });
});
