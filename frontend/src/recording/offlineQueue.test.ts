import { describe, expect, it } from "vitest";

import {
  filterQueuedRecordingsForOwner,
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
