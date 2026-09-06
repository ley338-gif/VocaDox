/**
 * Real progress stages derived from actual ProcessingJob rows — a stage
 * indicator, not a fabricated percentage. Shared between TranscriptPanel
 * (Transkript tab) and ConversationDetailPage (Übersicht tab) so both
 * agree on what "still processing" means.
 */
import type { ProcessingJob } from "../api/transcription";

export type Stage = "idle" | "preparing" | "transcribing" | "diarizing" | "aligning" | "ready" | "failed";

export function stageFromJobs(jobs: ProcessingJob[], transcriptStatus: string | undefined): Stage {
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

export const STAGE_LABELS: Record<Stage, string> = {
  idle: "Nicht gestartet",
  preparing: "Audio wird vorbereitet…",
  transcribing: "Transkription läuft…",
  diarizing: "Sprechererkennung läuft…",
  aligning: "Transkript wird ausgerichtet…",
  ready: "Bereit",
  failed: "Fehlgeschlagen",
};
