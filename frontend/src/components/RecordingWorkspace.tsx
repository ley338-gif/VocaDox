import { AlertTriangle, Bookmark, Circle, Pause, Play, Square, Trash2, Upload } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import { addMarker, finalizeRecording } from "../api/conversations";
import { Button } from "../design-system/Button";
import { useAuth } from "../auth/useAuth";
import { enqueueRecording, isOfflineQueueSupported } from "../recording/offlineQueue";
import { useLiveTranscript } from "../recording/useLiveTranscript";
import {
  type AudioSource,
  isCombinedAudioCaptureSupported,
  isRecordingSupported,
  isSystemAudioCaptureSupported,
  useRecorder,
} from "../recording/useRecorder";
import styles from "./RecordingWorkspace.module.css";

// Mirrors the backend's default `recording_consent_notice` setting
// (app.platform.config.Settings.recording_consent_notice). Not yet served
// from an admin-configurable endpoint — see docs/admin/recording-policy.md
// for the deferred "make this editable in the UI" follow-up.
const CONSENT_NOTICE =
  "Bestätigen Sie, dass die erforderliche Einwilligung/Genehmigung für diese Aufnahme eingeholt wurde.";

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
  const { user } = useAuth();
  const [consentGiven, setConsentGiven] = useState(false);
  const [audioSource, setAudioSource] = useState<AudioSource>("microphone");
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const recorder = useRecorder();
  const live = useLiveTranscript(
    conversationId,
    csrfToken,
    recorder.state === "recording",
    recorder.getLiveChunkBlob
  );

  if (!isRecordingSupported()) {
    return (
      <div className={styles.workspace} role="alert">
        <div className={styles.errorBanner}>
          <AlertTriangle size={16} aria-hidden="true" /> Aufnahme wird in diesem Browser nicht
          unterstützt. Verwenden Sie einen aktuellen Chrome, Edge oder Firefox — oder nutzen Sie
          stattdessen &quot;Audio hochladen&quot;.
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
            Diese Bestätigung allein macht die Aufnahme noch nicht rechtskonform. Einwilligung und
            weitere rechtliche Pflichten liegen weiterhin in der Verantwortung Ihrer Organisation.
          </p>
          {isSystemAudioCaptureSupported() && (
            <fieldset className={styles.sourcePicker}>
              <legend>Audioquelle</legend>
              <label>
                <input
                  type="radio"
                  name="audio-source"
                  checked={audioSource === "microphone"}
                  onChange={() => setAudioSource("microphone")}
                />{" "}
                Mikrofon
              </label>
              <label>
                <input
                  type="radio"
                  name="audio-source"
                  checked={audioSource === "system-audio"}
                  onChange={() => setAudioSource("system-audio")}
                />{" "}
                Ton von Tab/Bildschirm (z. B. ein bereits laufendes Video-Meeting im Browser) —
                VocaDox tritt niemals selbst einem Meeting bei; Sie wählen im Freigabedialog Ihres
                Browsers selbst, welcher Tab/Bildschirm erfasst wird.
              </label>
              {isCombinedAudioCaptureSupported() && (
                <label>
                  <input
                    type="radio"
                    name="audio-source"
                    checked={audioSource === "both"}
                    onChange={() => setAudioSource("both")}
                  />{" "}
                  Mikrofon + Ton von Tab/Bildschirm — nimmt Ihre eigene Stimme über das Mikrofon
                  und den freigegebenen Tab/Bildschirm gemeinsam auf einer Spur auf.
                </label>
              )}
            </fieldset>
          )}
          <div className={styles.controls}>
            <Button variant="secondary" type="button" onClick={() => onFinalized()}>
              Abbrechen
            </Button>
            <Button
              variant="primary"
              type="button"
              onClick={() => {
                setConsentGiven(true);
                void recorder.requestPermission(audioSource);
              }}
            >
              Aufnahme starten
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
      // Best-effort: the recording itself is the critical part and is
      // already saved at this point, so a single marker failing to save
      // must not surface as an "upload failed" error for the whole take.
      await Promise.allSettled(
        recorder.markers.map((marker) =>
          addMarker(
            conversationId,
            { timestamp_ms: Math.round(marker.timestampMs), label: marker.label },
            csrfToken
          )
        )
      );
      recorder.uploadSucceeded();
      live.reset();
      onFinalized();
    } catch (error) {
      // A network-level failure (offline, request never reached the
      // server) never surfaces as an ApiError — fetch itself throws
      // before there's a response to build one from. That's exactly the
      // case worth queuing for automatic retry rather than making the
      // user remember to manually retry once back online.
      if (!(error instanceof ApiError) && isOfflineQueueSupported() && user) {
        try {
          await enqueueRecording({
            conversationId,
            ownerUserId: user.userId,
            idempotencyKey,
            blob: recorder.blob,
            markers: recorder.markers,
          });
          live.reset();
          recorder.uploadQueuedOffline(
            "Kein Netz — die Aufnahme wurde lokal gespeichert und wird automatisch " +
              "hochgeladen, sobald wieder eine Verbindung besteht."
          );
          return;
        } catch {
          // IndexedDB itself failed (private browsing, quota, ...) — fall
          // through to the normal upload-failed/manual-retry path below.
        }
      }
      const message = error instanceof ApiError ? error.message : "Hochladen fehlgeschlagen.";
      recorder.uploadFailed(message);
    }
  }

  return (
    <div className={styles.workspace}>
      {recorder.state === "permission-denied" && (
        <div className={styles.errorBanner} role="alert">
          <AlertTriangle size={16} aria-hidden="true" />{" "}
          {recorder.errorMessage ??
            (audioSource === "system-audio"
              ? "Freigabe von Tab/Bildschirm wurde verweigert oder abgebrochen. Versuchen Sie es erneut und wählen Sie einen Tab/Bildschirm zur Freigabe."
              : audioSource === "both"
                ? "Mikrofon- oder Tab-/Bildschirm-Freigabe wurde verweigert oder abgebrochen. Versuchen Sie es erneut und erlauben Sie beides."
                : "Mikrofonzugriff wurde verweigert. Erlauben Sie den Mikrofonzugriff in Ihren Browser-Einstellungen und versuchen Sie es erneut.")}
          <div style={{ marginTop: "var(--space-2)" }}>
            <Button
              variant="secondary"
              type="button"
              onClick={() => void recorder.requestPermission(audioSource)}
            >
              Erneut versuchen
            </Button>
          </div>
        </div>
      )}

      {recorder.errorMessage && recorder.state !== "permission-denied" && (
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
            {recorder.state === "recording" ? "Aufnahme läuft" : "Pausiert"} —{" "}
            {formatElapsed(recorder.elapsedMs)}
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
            <Circle size={16} aria-hidden="true" /> Aufnehmen
          </Button>
        )}
        {recorder.state === "recording" && (
          <>
            <Button
              variant="secondary"
              type="button"
              onClick={recorder.pause}
              aria-label="Aufnahme pausieren"
            >
              <Pause size={16} aria-hidden="true" /> Pause
            </Button>
            <Button
              variant="secondary"
              type="button"
              onClick={() => recorder.addMarker()}
              aria-label="Marker hinzufügen"
            >
              <Bookmark size={16} aria-hidden="true" /> Marker
            </Button>
            <Button
              variant="destructive"
              type="button"
              onClick={recorder.stop}
              aria-label="Aufnahme stoppen"
            >
              <Square size={16} aria-hidden="true" /> Stopp
            </Button>
          </>
        )}
        {recorder.state === "paused" && (
          <>
            <Button
              variant="secondary"
              type="button"
              onClick={recorder.resume}
              aria-label="Aufnahme fortsetzen"
            >
              <Play size={16} aria-hidden="true" /> Fortsetzen
            </Button>
            <Button
              variant="destructive"
              type="button"
              onClick={recorder.stop}
              aria-label="Aufnahme stoppen"
            >
              <Square size={16} aria-hidden="true" /> Stopp
            </Button>
          </>
        )}
        {recorder.state === "stopped" && (
          <>
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                live.reset();
                recorder.discard();
              }}
              aria-label="Aufnahme verwerfen"
            >
              <Trash2 size={16} aria-hidden="true" /> Verwerfen
            </Button>
            <Button variant="primary" type="button" onClick={() => void handleFinalize()}>
              <Upload size={16} aria-hidden="true" /> Aufnahme hochladen
            </Button>
          </>
        )}
        {recorder.state === "uploading" && <span aria-live="polite">Wird hochgeladen…</span>}
        {recorder.state === "upload-failed" && (
          <>
            <span role="alert">Hochladen fehlgeschlagen: {recorder.errorMessage}</span>
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                recorder.retryUpload();
                void handleFinalize();
              }}
            >
              Hochladen wiederholen
            </Button>
            <Button variant="tertiary" type="button" onClick={recorder.discard}>
              Verwerfen
            </Button>
          </>
        )}
        {recorder.state === "uploaded" && <span>Aufnahme hochgeladen.</span>}
        {recorder.state === "queued-offline" && (
          <span role="status">{recorder.errorMessage}</span>
        )}
      </div>

      {(recorder.state === "recording" || recorder.state === "paused") && live.transcriptText && (
        <div className={styles.livePreview}>
          <p className={styles.livePreviewLabel}>
            Live-Transkript (vorläufig — wird nach dem Hochladen durch die geprüfte Version
            ersetzt)
          </p>
          <p className={styles.liveTranscriptText}>{live.transcriptText}</p>
          {live.draftText && (
            <>
              <p className={styles.livePreviewLabel}>Live-Entwurf (vorläufig, unbestätigt)</p>
              <p className={styles.liveDraftText}>{live.draftText}</p>
            </>
          )}
        </div>
      )}

      {recorder.markers.length > 0 && (
        <ul className={styles.markerList} aria-label="Marker">
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
