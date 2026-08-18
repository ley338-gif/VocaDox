import { AlertTriangle, Bookmark, Circle, Pause, Play, Square, Trash2, Upload } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import { finalizeRecording } from "../api/conversations";
import { Button } from "../design-system/Button";
import { isRecordingSupported, useRecorder } from "../recording/useRecorder";
import styles from "./RecordingWorkspace.module.css";

// Mirrors the backend's default `recording_consent_notice` setting
// (app.platform.config.Settings.recording_consent_notice). Not yet served
// from an admin-configurable endpoint — see docs/admin/recording-policy.md
// for the deferred "make this editable in the UI" follow-up.
const CONSENT_NOTICE =
  "Confirm that required consent/authorization for this recording has been obtained.";

function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function RecordingWorkspace({
  conversationId,
  csrfToken,
  onFinalized,
}: {
  conversationId: string;
  csrfToken: string;
  onFinalized: () => void;
}) {
  const [consentGiven, setConsentGiven] = useState(false);
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const recorder = useRecorder();

  if (!isRecordingSupported()) {
    return (
      <div className={styles.workspace} role="alert">
        <div className={styles.errorBanner}>
          <AlertTriangle size={16} aria-hidden="true" /> Recording isn&apos;t supported in this
          browser. Try a recent Chrome, Edge, or Firefox — or use &quot;Upload audio&quot;
          instead.
        </div>
      </div>
    );
  }

  if (!consentGiven) {
    return (
      <div className={styles.workspace}>
        <div className={styles.consentBox}>
          <p>{CONSENT_NOTICE}</p>
          <p className={styles.consentDisclaimer}>
            This confirmation does not by itself make the recording legally compliant. Consent
            and other legal obligations remain the responsibility of your organization/operator.
          </p>
          <div className={styles.controls}>
            <Button variant="secondary" type="button" onClick={() => onFinalized()}>
              Cancel
            </Button>
            <Button
              variant="primary"
              type="button"
              onClick={() => {
                setConsentGiven(true);
                void recorder.requestPermission();
              }}
            >
              Start recording
            </Button>
          </div>
        </div>
      </div>
    );
  }

  async function handleFinalize() {
    if (!recorder.blob) return;
    recorder.beginUpload();
    try {
      await finalizeRecording(conversationId, recorder.blob, idempotencyKey, csrfToken);
      recorder.uploadSucceeded();
      onFinalized();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Upload failed.";
      recorder.uploadFailed(message);
    }
  }

  return (
    <div className={styles.workspace}>
      {recorder.state === "permission-denied" && (
        <div className={styles.errorBanner} role="alert">
          <AlertTriangle size={16} aria-hidden="true" /> Microphone access was denied. Allow
          microphone access in your browser settings, then try again.
          <div style={{ marginTop: "var(--space-2)" }}>
            <Button variant="secondary" type="button" onClick={() => void recorder.requestPermission()}>
              Try again
            </Button>
          </div>
        </div>
      )}

      {recorder.errorMessage && (
        <div className={styles.errorBanner} role="alert">
          <AlertTriangle size={16} aria-hidden="true" /> {recorder.errorMessage}
        </div>
      )}

      {(recorder.state === "recording" || recorder.state === "paused") && (
        <div className={styles.statusRow}>
          <Circle
            size={12}
            aria-hidden="true"
            color={recorder.state === "recording" ? "var(--color-danger)" : "var(--text-muted)"}
            fill={recorder.state === "recording" ? "var(--color-danger)" : "none"}
          />
          <span aria-live="polite">
            {recorder.state === "recording" ? "Recording" : "Paused"} — {formatElapsed(recorder.elapsedMs)}
          </span>
          <div className={styles.levelMeterTrack} aria-hidden="true">
            <div
              className={styles.levelMeterFill}
              style={{ width: `${Math.min(100, recorder.level * 220)}%` }}
            />
          </div>
        </div>
      )}

      <div className={styles.controls}>
        {recorder.state === "ready" && (
          <Button variant="primary" type="button" onClick={recorder.start}>
            <Circle size={16} aria-hidden="true" /> Record
          </Button>
        )}
        {recorder.state === "recording" && (
          <>
            <Button variant="secondary" type="button" onClick={recorder.pause} aria-label="Pause recording">
              <Pause size={16} aria-hidden="true" /> Pause
            </Button>
            <Button
              variant="secondary"
              type="button"
              onClick={() => recorder.addMarker()}
              aria-label="Add marker"
            >
              <Bookmark size={16} aria-hidden="true" /> Marker
            </Button>
            <Button variant="destructive" type="button" onClick={recorder.stop} aria-label="Stop recording">
              <Square size={16} aria-hidden="true" /> Stop
            </Button>
          </>
        )}
        {recorder.state === "paused" && (
          <>
            <Button variant="secondary" type="button" onClick={recorder.resume} aria-label="Resume recording">
              <Play size={16} aria-hidden="true" /> Resume
            </Button>
            <Button variant="destructive" type="button" onClick={recorder.stop} aria-label="Stop recording">
              <Square size={16} aria-hidden="true" /> Stop
            </Button>
          </>
        )}
        {recorder.state === "stopped" && (
          <>
            <Button variant="secondary" type="button" onClick={recorder.discard} aria-label="Discard recording">
              <Trash2 size={16} aria-hidden="true" /> Discard
            </Button>
            <Button variant="primary" type="button" onClick={() => void handleFinalize()}>
              <Upload size={16} aria-hidden="true" /> Upload recording
            </Button>
          </>
        )}
        {recorder.state === "uploading" && <span aria-live="polite">Uploading…</span>}
        {recorder.state === "upload-failed" && (
          <>
            <span role="alert">Upload failed: {recorder.errorMessage}</span>
            <Button variant="secondary" type="button" onClick={() => { recorder.retryUpload(); void handleFinalize(); }}>
              Retry upload
            </Button>
            <Button variant="tertiary" type="button" onClick={recorder.discard}>
              Discard
            </Button>
          </>
        )}
        {recorder.state === "uploaded" && <span>Recording uploaded.</span>}
      </div>

      {recorder.markers.length > 0 && (
        <ul className={styles.markerList} aria-label="Markers">
          {recorder.markers.map((marker, index) => (
            <li key={index} className={styles.markerItem}>
              {formatElapsed(marker.timestampMs)}
              {marker.label ? ` — ${marker.label}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
