/**
 * React hook wiring real browser recording APIs (`getUserMedia`,
 * `MediaRecorder`, Web Audio `AnalyserNode` for the level meter) onto the
 * pure `recordingMachine` state transitions. Feature-detects before doing
 * anything — see `isRecordingSupported()` — and never auto-starts a
 * recording; `requestPermission()`/`start()` are both explicit user
 * actions wired to button clicks in RecordingWorkspace.
 *
 * Browser compatibility (documented, not just implemented): tested against
 * current Chrome/Edge (Chromium) and Firefox, which both record
 * `audio/webm;codecs=opus` via MediaRecorder. Safari's MediaRecorder
 * support is inconsistent across versions — `isRecordingSupported()`
 * returns false there today rather than silently producing an
 * unplayable/mislabeled file; see docs/user/recording.md.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { RecordingEvent, RecordingState } from "./recordingMachine";
import { hasUnsavedRecording, reduceRecordingState } from "./recordingMachine";

export interface Marker {
  timestampMs: number;
  label?: string;
}

export function isRecordingSupported(): boolean {
  if (typeof navigator === "undefined" || typeof window === "undefined") return false;
  const hasGetUserMedia = Boolean(navigator.mediaDevices?.getUserMedia);
  const hasMediaRecorder = typeof window.MediaRecorder !== "undefined";
  return hasGetUserMedia && hasMediaRecorder;
}

export function preferredMimeType(): string | undefined {
  if (typeof window.MediaRecorder === "undefined") return undefined;
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  return candidates.find((type) => window.MediaRecorder.isTypeSupported(type));
}

export function useRecorder() {
  const [state, setState] = useState<RecordingState>(isRecordingSupported() ? "idle" : "unsupported");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [level, setLevel] = useState(0);
  const [markers, setMarkers] = useState<Marker[]>([]);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(0);
  const pausedAccumRef = useRef<number>(0);
  const tickRef = useRef<number | null>(null);

  const dispatch = useCallback((event: RecordingEvent) => {
    setState((prev) => reduceRecordingState(prev, event));
  }, []);

  const stopLevelLoop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const runLevelLoop = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sumSquares = 0;
      for (const value of data) {
        const normalized = (value - 128) / 128;
        sumSquares += normalized * normalized;
      }
      setLevel(Math.sqrt(sumSquares / data.length));
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const requestPermission = useCallback(async () => {
    if (!isRecordingSupported()) {
      dispatch({ type: "UNSUPPORTED" });
      return;
    }
    dispatch({ type: "REQUEST_PERMISSION" });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      stream.getAudioTracks().forEach((track) => {
        track.addEventListener("ended", () => dispatch({ type: "DEVICE_DISCONNECTED" }));
      });
      dispatch({ type: "PERMISSION_GRANTED" });
    } catch {
      dispatch({ type: "PERMISSION_DENIED" });
    }
  }, [dispatch]);

  const start = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;
    chunksRef.current = [];
    setMarkers([]);
    setBlob(null);
    setErrorMessage(null);

    const mimeType = preferredMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onerror = () => {
      setErrorMessage("Recording device error — the recording has been stopped.");
      dispatch({ type: "RECORDER_ERROR" });
    };
    recorder.onstop = () => {
      const merged = new Blob(chunksRef.current, { type: mimeType ?? "audio/webm" });
      setBlob(merged);
    };
    recorderRef.current = recorder;

    const AudioContextCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (AudioContextCtor) {
      const audioContext = new AudioContextCtor();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      audioContextRef.current = audioContext;
      analyserRef.current = analyser;
      runLevelLoop();
    }

    recorder.start(1000); // 1s timeslice: bounded in-memory chunk growth, matches ondataavailable design.
    startedAtRef.current = Date.now();
    pausedAccumRef.current = 0;
    setElapsedMs(0);
    tickRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAtRef.current - pausedAccumRef.current);
    }, 250);
    dispatch({ type: "START" });
  }, [dispatch, runLevelLoop]);

  const pauseStartedAtRef = useRef<number>(0);

  const pause = useCallback(() => {
    recorderRef.current?.pause();
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    pauseStartedAtRef.current = Date.now();
    dispatch({ type: "PAUSE" });
  }, [dispatch]);

  const resume = useCallback(() => {
    recorderRef.current?.resume();
    pausedAccumRef.current += Date.now() - pauseStartedAtRef.current;
    tickRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAtRef.current - pausedAccumRef.current);
    }, 250);
    dispatch({ type: "RESUME" });
  }, [dispatch]);

  const addMarker = useCallback(
    (label?: string) => {
      setMarkers((prev) => [...prev, { timestampMs: elapsedMs, label }]);
      dispatch({ type: "MARKER" });
    },
    [dispatch, elapsedMs]
  );

  const stop = useCallback(() => {
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    stopLevelLoop();
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    audioContextRef.current?.close().catch(() => undefined);
    dispatch({ type: "STOP" });
  }, [dispatch, stopLevelLoop]);

  const discard = useCallback(() => {
    setBlob(null);
    setMarkers([]);
    dispatch({ type: "DISCARD" });
  }, [dispatch]);

  const beginUpload = useCallback(() => dispatch({ type: "UPLOAD_START" }), [dispatch]);
  const uploadSucceeded = useCallback(() => dispatch({ type: "UPLOAD_SUCCESS" }), [dispatch]);
  const uploadFailed = useCallback((message: string) => {
    setErrorMessage(message);
    dispatch({ type: "UPLOAD_FAILURE" });
  }, [dispatch]);
  const retryUpload = useCallback(() => dispatch({ type: "RETRY_UPLOAD" }), [dispatch]);

  // Navigation-away protection while there's unsaved recorded audio.
  useEffect(() => {
    function handler(event: BeforeUnloadEvent) {
      if (hasUnsavedRecording(state)) {
        event.preventDefault();
        event.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [state]);

  useEffect(() => {
    return () => {
      stopLevelLoop();
      if (tickRef.current !== null) window.clearInterval(tickRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      audioContextRef.current?.close().catch(() => undefined);
    };
  }, [stopLevelLoop]);

  return {
    state,
    elapsedMs,
    level,
    markers,
    blob,
    errorMessage,
    requestPermission,
    start,
    pause,
    resume,
    addMarker,
    stop,
    discard,
    beginUpload,
    uploadSucceeded,
    uploadFailed,
    retryUpload,
  };
}
