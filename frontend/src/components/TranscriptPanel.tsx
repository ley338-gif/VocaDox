/**
 * Phase 3 Transcript tab: trigger processing, show real progress stages,
 * render speaker-attributed segments with confidence/review flags,
 * inline correction (never hides the original text), speaker
 * reassignment, audio-seek-on-click, and plain-text/JSON/Markdown export.
 *
 * "Real progress stages... a stage indicator, not a fabricated
 * percentage" (spec) — stageFromJobs() below maps the actual
 * ProcessingJob rows to one of five honest stages.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import {
  assignSpeaker,
  correctSegment,
  getProcessingStatus,
  getTranscript,
  listSpeakers,
  listTranscriptSegments,
  processTranscript,
  retryProcessing,
  transcriptExportUrl,
  type DetectedSpeaker,
  type ProcessingJob,
  type TranscriptSegment,
} from "../api/transcription";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { TextInput } from "../design-system/FormControls";
import { EmptyState, ErrorState, Skeleton } from "../design-system/States";
import { speakerColor } from "../lib/speakerColor";
import type { AudioPlayerHandle } from "./AudioPlayer";
import styles from "./TranscriptPanel.module.css";

type Stage = "idle" | "preparing" | "transcribing" | "diarizing" | "aligning" | "ready" | "failed";

function stageFromJobs(jobs: ProcessingJob[], transcriptStatus: string | undefined): Stage {
  if (transcriptStatus === "ready") return "ready";
  if (transcriptStatus === "failed") return "failed";
  const active = jobs.find((j) => j.status === "queued" || j.status === "running");
  if (!active) return jobs.length === 0 ? "idle" : "failed";
  switch (active.job_type) {
    case "normalize":
      return "preparing";
    case "transcribe":
      return "transcribing";
    case "diarize":
      return "diarizing";
    case "align":
      return "aligning";
    default:
      return "preparing";
  }
}

const STAGE_LABELS: Record<Stage, string> = {
  idle: "Nicht gestartet",
  preparing: "Audio wird vorbereitet…",
  transcribing: "Transkription läuft…",
  diarizing: "Sprechererkennung läuft…",
  aligning: "Transkript wird ausgerichtet…",
  ready: "Bereit",
  failed: "Fehlgeschlagen",
};

function formatTs(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function speakerLabel(speakers: DetectedSpeaker[], speakerId: string | null): string {
  if (!speakerId) return "Unbekannter Sprecher";
  const speaker = speakers.find((s) => s.id === speakerId);
  if (!speaker) return "Unbekannter Sprecher";
  return speaker.display_label ?? speaker.internal_label;
}

function segmentSpeakerColor(speakers: DetectedSpeaker[], speakerId: string | null): string {
  const speaker = speakers.find((s) => s.id === speakerId);
  return speakerColor(speaker?.internal_label ?? "unknown");
}

function qualityBadge(segment: TranscriptSegment) {
  if (!segment.review_flag) return null;
  return (
    <span className={styles.flag} role="img" aria-label={`Review nötig: ${segment.review_flag_reason ?? ""}`}>
      <AlertTriangle size={14} aria-hidden="true" /> prüfen
    </span>
  );
}

export function TranscriptPanel({
  conversationId,
  audioPlayerRef,
  activeMs,
}: {
  conversationId: string;
  audioPlayerRef: React.RefObject<AudioPlayerHandle | null>;
  activeMs: number;
}) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [search, setSearch] = useState("");
  // Optional hint for the diarization model — real testing showed
  // pyannote's own automatic speaker-count guess can genuinely
  // undercount on real (non-synthetic) multi-speaker recordings; telling
  // it the expected count up front measurably improves accuracy. Kept as
  // a raw string for a controlled numeric input; parsed only at submit
  // time (see expectedSpeakersAsInt below).
  const [expectedSpeakers, setExpectedSpeakers] = useState("");

  const processingQuery = useQuery({
    queryKey: ["processing-status", conversationId],
    queryFn: () => getProcessingStatus(conversationId),
    refetchInterval: (query) => {
      const jobs = query.state.data?.jobs ?? [];
      const active = jobs.some((j) => j.status === "queued" || j.status === "running");
      return active ? 2000 : false;
    },
  });

  const transcriptQuery = useQuery({
    queryKey: ["transcript", conversationId],
    queryFn: () => getTranscript(conversationId),
    retry: false,
  });

  const segmentsQuery = useQuery({
    queryKey: ["transcript-segments", conversationId, search],
    queryFn: () => listTranscriptSegments(conversationId, search || undefined),
    enabled: transcriptQuery.data?.status === "ready",
  });

  const speakersQuery = useQuery({
    queryKey: ["speakers", conversationId],
    queryFn: () => listSpeakers(conversationId),
    enabled: transcriptQuery.data?.status === "ready",
  });

  const processMutation = useMutation({
    mutationFn: (vars: { reprocess?: boolean } = {}) => {
      const n = Number.parseInt(expectedSpeakers, 10);
      const hint = Number.isInteger(n) && n > 0 ? { min_speakers: n, max_speakers: n } : {};
      return processTranscript(
        conversationId,
        { diarize: true, reprocess: vars.reprocess, ...hint },
        csrfToken ?? ""
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["processing-status", conversationId] });
      void queryClient.invalidateQueries({ queryKey: ["transcript", conversationId] });
      void queryClient.invalidateQueries({ queryKey: ["speakers", conversationId] });
      void queryClient.invalidateQueries({ queryKey: ["transcript-segments", conversationId] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: () => retryProcessing(conversationId, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["processing-status", conversationId] }),
  });

  const correctMutation = useMutation({
    mutationFn: (vars: { segmentId: string; text: string }) =>
      correctSegment(conversationId, vars.segmentId, { corrected_text: vars.text }, csrfToken ?? ""),
    onSuccess: () => {
      setEditingSegmentId(null);
      void queryClient.invalidateQueries({ queryKey: ["transcript-segments", conversationId] });
    },
  });

  const assignSpeakerMutation = useMutation({
    mutationFn: (vars: { speakerId: string; label: string }) =>
      assignSpeaker(conversationId, vars.speakerId, { display_label: vars.label || null }, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["speakers", conversationId] }),
  });

  const stage = stageFromJobs(processingQuery.data?.jobs ?? [], transcriptQuery.data?.status);
  const stages: Stage[] = ["preparing", "transcribing", "diarizing", "aligning", "ready"];

  const activeSegmentId = useMemo(() => {
    const segments = segmentsQuery.data ?? [];
    const match = segments.find((s) => activeMs >= s.start_ms && activeMs < s.end_ms);
    return match?.id ?? null;
  }, [segmentsQuery.data, activeMs]);

  if (transcriptQuery.isLoading || processingQuery.isLoading) {
    return <Skeleton height="6rem" />;
  }

  if (stage === "idle") {
    return (
      <div className={styles.empty}>
        <EmptyState title="Noch kein Transkript" />
        {hasPermission("transcript:process") && (
          <div className={styles.speakerHintRow}>
            <label htmlFor="expected-speakers" className={styles.muted}>
              Erwartete Sprecheranzahl (optional)
            </label>
            <TextInput
              id="expected-speakers"
              type="number"
              min={1}
              max={20}
              style={{ width: "5rem" }}
              value={expectedSpeakers}
              onChange={(event) => setExpectedSpeakers(event.target.value)}
              placeholder="auto"
            />
            <Button variant="primary" type="button" onClick={() => processMutation.mutate({})}>
              Transkription starten
            </Button>
          </div>
        )}
      </div>
    );
  }

  if (stage === "failed") {
    const failedJob = processingQuery.data?.jobs.find((j) => j.status === "failed");
    return (
      <ErrorState
        title={`Transkription fehlgeschlagen${failedJob?.error_code ? ` — ${failedJob.error_code}` : ""}`}
        message={failedJob?.error_message_safe ?? undefined}
        onRetry={hasPermission("processing:retry") ? () => retryMutation.mutate() : undefined}
      />
    );
  }

  if (stage !== "ready") {
    return (
      <div className={styles.progress}>
        <ol className={styles.stageList}>
          {stages.map((s) => (
            <li key={s} className={s === stage ? styles.stageActive : undefined}>
              {STAGE_LABELS[s]}
            </li>
          ))}
        </ol>
        <p className={styles.muted}>
          Die Verarbeitung läuft im Hintergrund — diese Seite aktualisiert sich automatisch.
        </p>
      </div>
    );
  }

  const segments = segmentsQuery.data ?? [];
  const speakers = speakersQuery.data ?? [];

  return (
    <div>
      <div className={styles.toolbar}>
        <TextInput
          placeholder="Transkript durchsuchen…"
          aria-label="Transkript durchsuchen"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <div className={styles.exportLinks}>
          <a href={transcriptExportUrl(conversationId, "text")} target="_blank" rel="noreferrer">
            <Download size={14} aria-hidden="true" /> .txt
          </a>
          <a href={transcriptExportUrl(conversationId, "json")} target="_blank" rel="noreferrer">
            <Download size={14} aria-hidden="true" /> .json
          </a>
          <a href={transcriptExportUrl(conversationId, "markdown")} target="_blank" rel="noreferrer">
            <Download size={14} aria-hidden="true" /> .md
          </a>
        </div>
      </div>

      {speakers.length > 0 && hasPermission("speaker:assign") && (
        <div className={styles.speakerList}>
          {speakers.map((speaker) => (
            <SpeakerChip key={speaker.id} speaker={speaker} onRename={(label) => assignSpeakerMutation.mutate({ speakerId: speaker.id, label })} />
          ))}
        </div>
      )}

      {hasPermission("transcript:process") && (
        <div className={styles.speakerHintRow}>
          <span className={styles.muted}>
            Falsche Sprecheranzahl ({speakers.length} erkannt)? Mit Hinweis neu verarbeiten:
          </span>
          <TextInput
            aria-label="Erwartete Sprecheranzahl für die erneute Verarbeitung"
            type="number"
            min={1}
            max={20}
            style={{ width: "5rem" }}
            value={expectedSpeakers}
            onChange={(event) => setExpectedSpeakers(event.target.value)}
            placeholder="auto"
          />
          <Button
            variant="secondary"
            type="button"
            disabled={processMutation.isPending}
            onClick={() => processMutation.mutate({ reprocess: true })}
          >
            <RefreshCw size={14} aria-hidden="true" /> Neu verarbeiten
          </Button>
        </div>
      )}

      <ul className={styles.segmentList}>
        {segments.map((segment) => (
          <li
            key={segment.id}
            className={`${styles.segment} ${segment.id === activeSegmentId ? styles.segmentActive : ""}`}
          >
            <button
              type="button"
              className={styles.timestamp}
              onClick={() => audioPlayerRef.current?.seekToMs(segment.start_ms)}
              aria-label={`Jump to ${formatTs(segment.start_ms)}`}
            >
              {formatTs(segment.start_ms)}
            </button>
            <div className={styles.segmentBody}>
              <div className={styles.segmentMeta}>
                <span
                  className={styles.speakerName}
                  style={{ color: segmentSpeakerColor(speakers, segment.speaker_id) }}
                >
                  {speakerLabel(speakers, segment.speaker_id)}
                </span>
                {segment.confidence !== null && (
                  <span className={styles.muted}>{Math.round(segment.confidence * 100)}%</span>
                )}
                {qualityBadge(segment)}
              </div>
              {editingSegmentId === segment.id ? (
                <div className={styles.editRow}>
                  <TextInput
                    aria-label="Korrigierter Text"
                    value={editValue}
                    onChange={(event) => setEditValue(event.target.value)}
                  />
                  <Button
                    variant="primary"
                    type="button"
                    onClick={() => correctMutation.mutate({ segmentId: segment.id, text: editValue })}
                  >
                    Speichern
                  </Button>
                  <Button variant="tertiary" type="button" onClick={() => setEditingSegmentId(null)}>
                    Abbrechen
                  </Button>
                </div>
              ) : (
                <p
                  onClick={() => {
                    if (!hasPermission("transcript:correct")) return;
                    setEditingSegmentId(segment.id);
                    setEditValue(segment.corrected_text ?? segment.original_text);
                  }}
                  className={hasPermission("transcript:correct") ? styles.editable : undefined}
                >
                  {segment.corrected_text ?? segment.original_text}
                </p>
              )}
              {segment.corrected_text && (
                <p className={styles.originalText}>Original: {segment.original_text}</p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SpeakerChip({
  speaker,
  onRename,
}: {
  speaker: DetectedSpeaker;
  onRename: (label: string) => void;
}) {
  const [value, setValue] = useState(speaker.display_label ?? "");
  return (
    <div className={styles.speakerChip}>
      <span
        className={styles.speakerDot}
        style={{ background: speakerColor(speaker.internal_label) }}
        aria-hidden="true"
      />
      <TextInput
        aria-label={`${speaker.internal_label} umbenennen`}
        placeholder={speaker.internal_label}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={() => {
          if (value !== (speaker.display_label ?? "")) onRename(value);
        }}
      />
    </div>
  );
}
