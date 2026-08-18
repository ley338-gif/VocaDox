/**
 * Pure state machine for the browser recording workflow — deliberately
 * free of any DOM/MediaRecorder/getUserMedia dependency so it can be unit
 * tested directly (jsdom has no real MediaRecorder implementation, so the
 * *logic* has to be testable independently of the browser APIs — see
 * recordingMachine.test.ts). `useRecorder.ts` is the thin adapter that
 * wires real browser events onto these transitions.
 *
 * States mirror the reliability scenarios the Phase 2 brief calls out:
 * permission denied, mic disconnected/MediaRecorder error, upload failure
 * + retry, accidental double-stop, duplicate finalize. Never claims crash
 * recovery — a page reload while `recording` loses the in-progress take,
 * which is a documented limitation (see docs/user/recording.md).
 */

export type RecordingState =
  | "idle"
  | "requesting-permission"
  | "permission-denied"
  | "unsupported"
  | "ready"
  | "recording"
  | "paused"
  | "stopped"
  | "uploading"
  | "uploaded"
  | "upload-failed"
  | "discarded";

export type RecordingEvent =
  | { type: "REQUEST_PERMISSION" }
  | { type: "PERMISSION_GRANTED" }
  | { type: "PERMISSION_DENIED" }
  | { type: "UNSUPPORTED" }
  | { type: "START" }
  | { type: "PAUSE" }
  | { type: "RESUME" }
  | { type: "MARKER" }
  | { type: "STOP" }
  | { type: "RECORDER_ERROR" }
  | { type: "DEVICE_DISCONNECTED" }
  | { type: "DISCARD" }
  | { type: "UPLOAD_START" }
  | { type: "UPLOAD_SUCCESS" }
  | { type: "UPLOAD_FAILURE" }
  | { type: "RETRY_UPLOAD" };

const TRANSITIONS: Record<RecordingState, Partial<Record<RecordingEvent["type"], RecordingState>>> = {
  idle: { REQUEST_PERMISSION: "requesting-permission", UNSUPPORTED: "unsupported" },
  "requesting-permission": {
    PERMISSION_GRANTED: "ready",
    PERMISSION_DENIED: "permission-denied",
  },
  "permission-denied": { REQUEST_PERMISSION: "requesting-permission" },
  unsupported: {},
  ready: { START: "recording" },
  recording: {
    PAUSE: "paused",
    MARKER: "recording", // markers don't change state, just recorded as a side effect
    STOP: "stopped",
    RECORDER_ERROR: "stopped",
    DEVICE_DISCONNECTED: "stopped",
  },
  paused: {
    RESUME: "recording",
    STOP: "stopped",
    RECORDER_ERROR: "stopped",
    DEVICE_DISCONNECTED: "stopped",
  },
  stopped: { DISCARD: "discarded", UPLOAD_START: "uploading" },
  uploading: { UPLOAD_SUCCESS: "uploaded", UPLOAD_FAILURE: "upload-failed" },
  "upload-failed": { RETRY_UPLOAD: "uploading", DISCARD: "discarded" },
  uploaded: {},
  discarded: {},
};

export function canTransition(state: RecordingState, event: RecordingEvent["type"]): boolean {
  return TRANSITIONS[state]?.[event] !== undefined;
}

export function reduceRecordingState(state: RecordingState, event: RecordingEvent): RecordingState {
  const next = TRANSITIONS[state]?.[event.type];
  // Unknown transitions are deliberately no-ops (e.g. a duplicate STOP
  // while already "stopped", or a duplicate finalize once "uploading") —
  // this is what makes double-stop / duplicate-finalize safe at the state
  // layer, on top of the server's own idempotency_key handling.
  return next ?? state;
}

export function isRecordingActive(state: RecordingState): boolean {
  return state === "recording" || state === "paused";
}

/** True while leaving the page would lose in-progress work — used to
 * decide whether to show a navigation-away warning. */
export function hasUnsavedRecording(state: RecordingState): boolean {
  return isRecordingActive(state) || state === "stopped" || state === "upload-failed";
}
