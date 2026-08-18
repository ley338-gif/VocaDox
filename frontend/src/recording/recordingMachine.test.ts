import { describe, expect, it } from "vitest";

import {
  canTransition,
  hasUnsavedRecording,
  isRecordingActive,
  reduceRecordingState,
} from "./recordingMachine";

describe("recordingMachine", () => {
  it("starts idle and requires an explicit permission request", () => {
    expect(canTransition("idle", "START")).toBe(false);
  });

  it("never auto-starts recording — READY only reachable after PERMISSION_GRANTED", () => {
    let state = reduceRecordingState("idle", { type: "REQUEST_PERMISSION" });
    expect(state).toBe("requesting-permission");
    state = reduceRecordingState(state, { type: "PERMISSION_GRANTED" });
    expect(state).toBe("ready");
    expect(canTransition(state, "START")).toBe(true);
  });

  it("permission denied is a distinct, recoverable state", () => {
    let state = reduceRecordingState("idle", { type: "REQUEST_PERMISSION" });
    state = reduceRecordingState(state, { type: "PERMISSION_DENIED" });
    expect(state).toBe("permission-denied");
    // Recoverable: user can retry the permission prompt.
    state = reduceRecordingState(state, { type: "REQUEST_PERMISSION" });
    expect(state).toBe("requesting-permission");
  });

  it("supports pause and resume while recording", () => {
    let state: import("./recordingMachine").RecordingState = "recording";
    state = reduceRecordingState(state, { type: "PAUSE" });
    expect(state).toBe("paused");
    expect(isRecordingActive(state)).toBe(true);
    state = reduceRecordingState(state, { type: "RESUME" });
    expect(state).toBe("recording");
  });

  it("MARKER does not change state while recording", () => {
    const state = reduceRecordingState("recording", { type: "MARKER" });
    expect(state).toBe("recording");
  });

  it("a MediaRecorder error or device disconnect stops the recording", () => {
    expect(reduceRecordingState("recording", { type: "RECORDER_ERROR" })).toBe("stopped");
    expect(reduceRecordingState("paused", { type: "DEVICE_DISCONNECTED" })).toBe("stopped");
  });

  it("accidental double-stop is a safe no-op", () => {
    const stopped = reduceRecordingState("recording", { type: "STOP" });
    expect(stopped).toBe("stopped");
    const stoppedAgain = reduceRecordingState(stopped, { type: "STOP" });
    expect(stoppedAgain).toBe("stopped");
  });

  it("upload can fail and be retried", () => {
    let state = reduceRecordingState("stopped", { type: "UPLOAD_START" });
    expect(state).toBe("uploading");
    state = reduceRecordingState(state, { type: "UPLOAD_FAILURE" });
    expect(state).toBe("upload-failed");
    state = reduceRecordingState(state, { type: "RETRY_UPLOAD" });
    expect(state).toBe("uploading");
    state = reduceRecordingState(state, { type: "UPLOAD_SUCCESS" });
    expect(state).toBe("uploaded");
  });

  it("a duplicate finalize/upload-start while already uploading is a no-op", () => {
    const state = reduceRecordingState("uploading", { type: "UPLOAD_START" });
    expect(state).toBe("uploading");
  });

  it("discard is available after stopping or after a failed upload", () => {
    expect(reduceRecordingState("stopped", { type: "DISCARD" })).toBe("discarded");
    expect(reduceRecordingState("upload-failed", { type: "DISCARD" })).toBe("discarded");
  });

  it("hasUnsavedRecording flags active/stopped/failed states for the navigation-away warning", () => {
    expect(hasUnsavedRecording("recording")).toBe(true);
    expect(hasUnsavedRecording("paused")).toBe(true);
    expect(hasUnsavedRecording("stopped")).toBe(true);
    expect(hasUnsavedRecording("upload-failed")).toBe(true);
    expect(hasUnsavedRecording("uploaded")).toBe(false);
    expect(hasUnsavedRecording("idle")).toBe(false);
    expect(hasUnsavedRecording("discarded")).toBe(false);
  });

  it("unsupported-browser state has no further transitions except staying put", () => {
    const state = reduceRecordingState("idle", { type: "UNSUPPORTED" });
    expect(state).toBe("unsupported");
    expect(reduceRecordingState(state, { type: "REQUEST_PERMISSION" })).toBe("unsupported");
  });
});
