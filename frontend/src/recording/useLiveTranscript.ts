/**
 * Post-GA P2-1: periodically flushes the recording-so-far to the backend
 * live-transcript endpoint while actively recording, and holds the
 * latest returned transcript/draft text for display. Explicitly a
 * preview aid — cleared (never relied upon) once the real upload+
 * processing pipeline takes over at finalize.
 */
import { useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { clearLiveSession, ingestLiveChunk } from "../api/live";

const FLUSH_INTERVAL_MS = 10_000;

export function useLiveTranscript(
  conversationId: string,
  csrfToken: string,
  isRecording: boolean,
  getLiveChunkBlob: () => Blob | null
) {
  const [transcriptText, setTranscriptText] = useState("");
  const [draftText, setDraftText] = useState<string | null>(null);
  const [isFlushing, setIsFlushing] = useState(false);
  const flushingRef = useRef(false);

  useEffect(() => {
    if (!isRecording) return;

    const interval = window.setInterval(() => {
      if (flushingRef.current) return; // never overlap two in-flight flushes
      const blob = getLiveChunkBlob();
      if (!blob) return;
      flushingRef.current = true;
      setIsFlushing(true);
      void ingestLiveChunk(conversationId, blob, csrfToken)
        .then((session) => {
          setTranscriptText(session.transcript_text);
          if (session.draft_text) setDraftText(session.draft_text);
        })
        .catch((error: unknown) => {
          // A live-preview flush failing must never interrupt the real
          // recording — the actual audio is safe in the recorder's own
          // chunk buffer regardless. Silently skip this cycle and retry
          // on the next interval tick.
          if (error instanceof ApiError) {
            console.warn("live transcript flush failed", error.message);
          }
        })
        .finally(() => {
          flushingRef.current = false;
          setIsFlushing(false);
        });
    }, FLUSH_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [isRecording, conversationId, csrfToken, getLiveChunkBlob]);

  function reset() {
    setTranscriptText("");
    setDraftText(null);
    void clearLiveSession(conversationId, csrfToken);
  }

  return { transcriptText, draftText, isFlushing, reset };
}
